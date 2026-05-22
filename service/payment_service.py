import hashlib
import logging
import urllib.parse
import requests
from sqlalchemy.orm import Session

from models.models import Payments, Consultations, ConsultationNotes
from core.config import settings
from core.session_store import get_session
from core.intake_ai import mock_summary

logger = logging.getLogger(__name__)


class PaymentService:

    @staticmethod
    def create_payment(db: Session, user_id: int, amount, consultation_session_id: str | None = None) -> Payments:
        payment = Payments(
            user_id=user_id,
            amount=amount,
            status="pending",
            consultation_session_id=consultation_session_id
        )
        db.add(payment)
        db.commit()
        db.refresh(payment)
        return payment

    @staticmethod
    def generate_signature(data: dict) -> str:
        # Remove empty/None values but preserve original key order (PayFast requirement)
        filtered = {k: v for k, v in data.items() if v not in (None, "")}

        # Build URL-encoded query string in original insertion order (do NOT sort)
        encoded = urllib.parse.urlencode(filtered)

        if settings.PAYFAST_PASSPHRASE:
            encoded += "&passphrase=" + urllib.parse.quote_plus(
                settings.PAYFAST_PASSPHRASE
            )
        return hashlib.md5(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def build_payment_url(payment: Payments) -> str:
        host = (
            "https://sandbox.payfast.co.za/eng/process"
            if settings.PAYFAST_SANDBOX
            else "https://www.payfast.co.za/eng/process"
        )

        data = {
            "merchant_id": settings.PAYFAST_MERCHANT_ID,
            "merchant_key": settings.PAYFAST_MERCHANT_KEY,
            "return_url": f"{settings.APP_BASE_URL}/payments/success?payment_id={payment.id}",
            "cancel_url": f"{settings.APP_BASE_URL}/payments/cancel?payment_id={payment.id}",
            "notify_url": f"{settings.APP_BASE_URL}/payments/webhook",
            "m_payment_id": str(payment.id),
            "amount": f"{payment.amount:.2f}",
            "item_name": "Dokotela Consultation",
            "custom_str1": payment.consultation_session_id or "",
        }

        signature = PaymentService.generate_signature(data)
        data["signature"] = signature

        return host + "?" + urllib.parse.urlencode(data)

    @staticmethod
    def _itn_signature(data: dict) -> str:
        """
        Compute signature for an incoming ITN payload.
        PayFast includes ALL fields (even empty strings) when it builds the
        ITN signature — unlike the outgoing checkout signature which strips empties.
        """
        # Keep every field except 'signature' itself; preserve order PayFast sent
        filtered = {k: v for k, v in data.items() if k != "signature" and v is not None}
        encoded = urllib.parse.urlencode(filtered)
        if settings.PAYFAST_PASSPHRASE:
            encoded += "&passphrase=" + urllib.parse.quote_plus(settings.PAYFAST_PASSPHRASE)
        return hashlib.md5(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def verify_itn(form_data: dict) -> bool:
        """
        ITN verification:
        1. Validate signature
        2. Confirm with PayFast (skipped in sandbox — sandbox endpoint is unreliable)
        """
        received_signature = form_data.get("signature")
        if not received_signature:
            logger.error("ITN: missing signature")
            return False

        data_without_signature = {k: v for k, v in form_data.items() if k != "signature"}
        expected_signature = PaymentService._itn_signature(form_data)

        logger.info("ITN received signature : %s", received_signature)
        logger.info("ITN expected signature : %s", expected_signature)
        logger.info("ITN payload (no sig)   : %s", urllib.parse.urlencode(data_without_signature))

        if expected_signature != received_signature:
            logger.error("ITN signature mismatch — rejecting")
            return False

        # Skip remote validation in sandbox (endpoint is flaky)
        if settings.PAYFAST_SANDBOX:
            logger.info("ITN sandbox mode — skipping remote validation")
            return True

        validation_url = "https://www.payfast.co.za/eng/query/validate"
        payload = urllib.parse.urlencode(form_data)

        try:
            response = requests.post(
                validation_url,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
            result = response.text.strip()
            logger.info("ITN remote validation response: %s", result)
            return result == "VALID"
        except Exception as exc:
            logger.error("ITN remote validation request failed: %s", exc)
            return False

    @staticmethod
    def mark_payment_completed(db: Session, payment_id: int,
                               provider_reference: str) -> type[Payments]:
        logger.info("mark_payment_completed: looking up payment_id=%s", payment_id)
        payment = db.get(Payments, payment_id)
        if not payment:
            logger.error("mark_payment_completed: payment_id=%s NOT FOUND", payment_id)
            raise ValueError("Payment not found.")

        logger.info("mark_payment_completed: found payment, current status=%s", payment.status)
        payment.status = "completed"
        payment.payment_reference = provider_reference
        db.flush()  # write payment changes without closing session

        # Load AI summary from Redis using the consultation_session_id stored at checkout
        summary_text = None
        session_id = payment.consultation_session_id
        if session_id:
            session_data = get_session(session_id)
            if session_data and session_data.get("messages"):
                ai_summary = mock_summary(session_data["messages"])
                summary_text = ai_summary.get("summary")
                logger.info("AI summary loaded for session %s: %s", session_id, summary_text)
            else:
                logger.warning("No session data found in Redis for session_id=%s", session_id)

        # patient_id is already on the payment record — no JWT needed in webhook
        consultation = Consultations(
            patient_id=payment.user_id,
            payment_id=payment.id,
            status="paid",
        )
        db.add(consultation)
        db.flush()  # flush so consultation.id is available for notes FK

        # Persist AI intake summary as a consultation note
        if summary_text:
            note = ConsultationNotes(
                consultation_id=consultation.id,
                author="ai",
                type="SOAP_AI",
                notes=summary_text,
            )
            db.add(note)
            logger.info("ConsultationNote created for consultation_id=%s", consultation.id)
        else:
            logger.warning("No summary available — skipping ConsultationNote for consultation_id=%s", consultation.id)

        db.commit()  # single commit for payment + consultation + notes
        db.refresh(payment)
        db.refresh(consultation)
        logger.info("mark_payment_completed: commit done, status=%s reference=%s", payment.status, payment.payment_reference)
        logger.info("Consultation created: id=%s patient_id=%s payment_id=%s", consultation.id, consultation.patient_id, consultation.payment_id)

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
