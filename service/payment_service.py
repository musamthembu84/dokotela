import base64
import hashlib
import hmac
import logging
import time
import urllib.parse
from decimal import Decimal

import requests
from sqlalchemy.orm import Session

from models.models import Payments, Consultations, ConsultationNotes, Users
from core.config import settings
from core.session_store import get_session
from core.llm_service import generate_llm_summary
from service.email_service import EmailService

logger = logging.getLogger(__name__)

STITCH_BASE_URL = "https://express.stitch.money"

# Module-level cache for the client-credentials token. Stitch tokens expire
# after 15 minutes, so we refresh a couple of minutes early rather than
# caching for the full lifetime.
_token_cache = {"access_token": None, "expires_at": 0.0}


class PaymentService:
    CONSULTATION_PRICE_ZAR = Decimal("600.00")

    @staticmethod
    def create_payment(db: Session, user_id: int, amount, consultation_session_id: str | None = None) -> Payments:
        logger.info("Incoming create_payment request: user_id=%s amount=%s consultation_session_id=%s", user_id, amount, consultation_session_id)
        payment = Payments(
            user_id=user_id,
            amount=amount,
            status="pending",
            provider="stitch",
            consultation_session_id=consultation_session_id
        )
        db.add(payment)
        db.commit()
        db.refresh(payment)
        return payment

    @staticmethod
    def _get_access_token() -> str:
        now = time.time()
        if _token_cache["access_token"] and _token_cache["expires_at"] > now:
            return _token_cache["access_token"]

        response = requests.post(
            f"{STITCH_BASE_URL}/api/v1/token",
            json={
                "clientId": settings.STITCH_CLIENT_ID,
                "clientSecret": settings.STITCH_CLIENT_SECRET,
                "scope": "client_paymentrequest",
            },
            timeout=15,
        )
        response.raise_for_status()
        body = response.json()
        if not body.get("success"):
            raise RuntimeError(f"Stitch token request failed: {body}")

        access_token = body["data"]["accessToken"]
        _token_cache["access_token"] = access_token
        # Tokens are valid for 15 minutes; refresh 2 minutes early.
        _token_cache["expires_at"] = now + 13 * 60
        return access_token

    @staticmethod
    def build_payment_url(payment: Payments, payer_name: str) -> str:
        """
        Create a Stitch payment link for this payment and return the URL the
        payer should be sent to. The redirect-back URL is appended as
        `redirect_url` and must exactly match a URL already registered in
        the Stitch dashboard (Developers > Redirect URLs).
        """
        token = PaymentService._get_access_token()
        amount_cents = int((payment.amount * 100).to_integral_value())

        response = requests.post(
            f"{STITCH_BASE_URL}/api/v1/payment-links",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "amount": amount_cents,
                "payerName": (payer_name or "Dokotela Patient")[:40],
                "merchantReference": str(payment.id),
            },
            timeout=15,
        )
        response.raise_for_status()
        body = response.json()
        if not body.get("success"):
            raise RuntimeError(f"Stitch payment-link creation failed: {body}")

        link = body["data"]["payment"]["link"]
        separator = "&" if "?" in link else "?"
        return f"{link}{separator}redirect_url={urllib.parse.quote(settings.STITCH_REDIRECT_URL, safe='')}"

    @staticmethod
    def verify_webhook_signature(svix_id: str, svix_timestamp: str, svix_signature: str, raw_body: bytes) -> bool:
        """
        Verify a Stitch webhook delivery, signed by Svix.
        Signed content: "{svix_id}.{svix_timestamp}.{body}", HMAC-SHA256
        using the base64-decoded key portion of the whsec_ secret.
        """
        secret = settings.STITCH_WEBHOOK_SECRET
        if not secret.startswith("whsec_"):
            logger.error("STITCH_WEBHOOK_SECRET is missing or malformed (expected whsec_ prefix)")
            return False

        key = base64.b64decode(secret.split("_", 1)[1])
        signed_content = f"{svix_id}.{svix_timestamp}.{raw_body.decode('utf-8')}".encode("utf-8")
        expected_signature = base64.b64encode(
            hmac.new(key, signed_content, hashlib.sha256).digest()
        ).decode("utf-8")

        for part in svix_signature.split(" "):
            if "," not in part:
                continue
            _, provided_signature = part.split(",", 1)
            if hmac.compare_digest(provided_signature, expected_signature):
                return True

        logger.error("Stitch webhook signature mismatch")
        return False

    @staticmethod
    def verify_payment_link(link_id: str) -> dict | None:
        """
        Re-confirm a payment link's status directly with Stitch — mirrors
        the old PayFast remote ITN validation step (don't trust the webhook
        body alone; confirm with the provider before crediting a payment).
        """
        token = PaymentService._get_access_token()
        response = requests.get(
            f"{STITCH_BASE_URL}/api/v1/payment-links/{link_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        if response.status_code != 200:
            logger.error("Stitch payment-link lookup failed: status=%s body=%s", response.status_code, response.text)
            return None

        body = response.json()
        if not body.get("success"):
            logger.error("Stitch payment-link lookup returned success=false: %s", body)
            return None

        return body["data"]["payment"]

    @staticmethod
    def mark_payment_completed(db: Session, payment_id: int,
                               provider_reference: str) -> type[Payments]:
        logger.info("mark_payment_completed: looking up payment_id=%s", payment_id)
        payment = db.get(Payments, payment_id)
        if not payment:
            logger.error("mark_payment_completed: payment_id=%s NOT FOUND", payment_id)
            raise ValueError("Payment not found.")

        if payment.status == "completed":
            logger.info("mark_payment_completed: payment_id=%s already completed — ignoring duplicate webhook delivery", payment_id)
            return payment

        logger.info("mark_payment_completed: found payment, current status=%s", payment.status)
        payment.status = "completed"
        payment.payment_reference = provider_reference

        # patient_id is already on the payment record — no JWT needed in webhook
        consultation = Consultations(
            patient_id=payment.user_id,
            payment_id=payment.id,
            status="paid",
        )
        db.add(consultation)

        # Commit payment + consultation now, before touching the AI summary
        # below. The LLM call can take minutes on a cold start - the visit
        # must be bookable (and visible to the frontend's status polling)
        # immediately, not held hostage by a slow/best-effort AI note.
        db.commit()
        db.refresh(payment)
        db.refresh(consultation)
        logger.info("mark_payment_completed: commit done, status=%s reference=%s", payment.status, payment.payment_reference)
        logger.info("Consultation created: id=%s patient_id=%s payment_id=%s", consultation.id, consultation.patient_id, consultation.payment_id)

        # Load AI summary from Redis using the consultation_session_id stored
        # at checkout, and persist it as a separate commit. Best-effort: a
        # failure here must not undo the payment/consultation committed above.
        session_id = payment.consultation_session_id
        if session_id:
            session_data = get_session(session_id)
            if session_data and session_data.get("messages"):
                try:
                    ai_summary = generate_llm_summary(session_data["messages"])
                    summary_text = ai_summary.get("summary")
                    logger.info("AI summary loaded for session %s: %s", session_id, summary_text)
                except Exception as exc:
                    logger.error("AI summary generation failed for session %s: %s", session_id, exc, exc_info=True)
                    summary_text = None

                if summary_text:
                    note = ConsultationNotes(
                        consultation_id=consultation.id,
                        author="ai",
                        type="SOAP_AI",
                        ai_note=summary_text,
                    )
                    db.add(note)
                    db.commit()
                    logger.info("ConsultationNote created for consultation_id=%s", consultation.id)
                else:
                    logger.warning("No summary available — skipping ConsultationNote for consultation_id=%s", consultation.id)
            else:
                logger.warning("No session data found in Redis for session_id=%s", session_id)

        patient = db.get(Users, payment.user_id)
        if patient:
            EmailService.send_payment_success_email(
                to_email=patient.email,
                username=patient.username,
                amount=f"{payment.amount:.2f}",
                currency=payment.currency,
                payment_reference=payment.payment_reference,
            )
        else:
            logger.warning(
                "Could not send payment success email — user_id=%s not found",
                payment.user_id,
            )

        return payment

    @staticmethod
    def mark_payment_failed(db: Session, payment_id: int) -> type[Payments]:
        payment = db.get(Payments, payment_id)
        if not payment:
            raise ValueError("Payment not found.")
        payment.status = "failed"
        db.commit()
        db.refresh(payment)
        return payment
