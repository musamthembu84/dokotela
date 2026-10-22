from fastapi import APIRouter, BackgroundTasks, Depends, Request, HTTPException
from typing import Annotated
import json
import logging

from core.dependency import db_dependency
from models.models import Payments, Users, CheckoutResponse, CheckoutRequest
from core.jwt_utils import get_current_user, authorize_user_access
from service.payment_service import PaymentService

router = APIRouter(prefix="/payments", tags=["payments"])
logger = logging.getLogger(__name__)

token_dep = Annotated[dict, Depends(get_current_user)]


def get_current_user(db: db_dependency, token: token_dep):
    user_id = int(token["id"])
    authorize_user_access(user_id, token)
    return user_id


@router.post("/checkout", response_model=CheckoutResponse)
def checkout(request: CheckoutRequest,
             db: db_dependency,
             background_tasks: BackgroundTasks,
             current_user: int = Depends(get_current_user)):

    logger.info("Incoming checkout request: %s", request)
    user = db.get(Users, current_user)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    payment = PaymentService.create_payment(
        db=db,
        user_id=current_user,
        amount=PaymentService.CONSULTATION_PRICE_ZAR,
        consultation_session_id=request.consultation_id
    )

    # The chat is already finished at this point - generate the doctor's AI
    # SOAP note now, in the background, fully decoupled from payment. The
    # payment webhook must never depend on the LLM being fast or reachable.
    if request.consultation_id:
        background_tasks.add_task(PaymentService.generate_and_store_summary, request.consultation_id)

    payment_url = PaymentService.build_payment_url(payment, payer_name=user.username)

    return CheckoutResponse(
        payment_id=payment.id,
        payment_url=payment_url,
    )


@router.get("/{payment_id}/status")
def get_payment_status(payment_id: int, db: db_dependency):
    payment = db.get(Payments, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return {
        "payment_id": payment.id,
        "status": payment.status,
        "amount": float(payment.amount),
        "currency": payment.currency,
        "payment_reference": payment.payment_reference,
        "consultation_session_id": payment.consultation_session_id,
        "created_at": payment.created_at,
        "updated_at": payment.updated_at,
    }


@router.get("/success")
def payment_success(payment_id: int, db: db_dependency):
    """Return URL handler — Stitch redirects the user here after payment."""
    payment = db.get(Payments, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return {
        "message": "Payment received. Awaiting confirmation from Stitch.",
        "payment_id": payment.id,
        "status": payment.status,
        "amount": float(payment.amount),
    }


@router.get("/cancel")
def payment_cancel(payment_id: int, db: db_dependency):
    """Cancel URL handler — Stitch redirects here when the user cancels."""
    payment = db.get(Payments, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    PaymentService.mark_payment_failed(db=db, payment_id=payment_id)
    return {
        "message": "Payment was cancelled.",
        "payment_id": payment.id,
        "status": "failed",
    }


@router.post("/webhook")
async def stitch_webhook(request: Request, db: db_dependency):
    raw_body = await request.body()
    svix_id = request.headers.get("svix-id")
    svix_timestamp = request.headers.get("svix-timestamp")
    svix_signature = request.headers.get("svix-signature")

    if not (svix_id and svix_timestamp and svix_signature):
        logger.error("Stitch webhook missing svix headers")
        raise HTTPException(status_code=400, detail="Missing webhook signature headers")

    if not PaymentService.verify_webhook_signature(svix_id, svix_timestamp, svix_signature, raw_body):
        logger.error("Stitch webhook signature verification failed (svix_id=%s)", svix_id)
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    payload = json.loads(raw_body)
    logger.info("Stitch webhook received (svix_id=%s): %s", svix_id, payload)

    if payload.get("type") != "LINK" or not payload.get("linkId"):
        # Only payment links are used by this app (not card consents,
        # subscriptions, or terminal sessions) — ack and ignore the rest.
        logger.info("Stitch webhook: ignoring non-LINK payment type=%s", payload.get("type"))
        return {"status": "ignored"}

    # Don't trust the webhook body alone — re-confirm status directly with
    # Stitch before crediting the payment (mirrors the old PayFast remote
    # ITN validation step).
    link = PaymentService.verify_payment_link(payload["linkId"])
    if not link or link.get("status") != "PAID":
        logger.error("Stitch webhook: payment link not confirmed PAID. payload=%s link=%s", payload, link)
        raise HTTPException(status_code=400, detail="Payment not confirmed as paid")

    try:
        payment_id = int(link["merchantReference"])
    except (TypeError, ValueError):
        logger.error("Stitch webhook: invalid merchantReference=%s", link.get("merchantReference"))
        raise HTTPException(status_code=400, detail="Invalid merchant reference")

    try:
        payment = PaymentService.mark_payment_completed(
            db=db,
            payment_id=payment_id,
            provider_reference=payload["id"],
        )
        logger.info("Payment %s marked completed. DB status=%s reference=%s", payment_id, payment.status,
                    payment.payment_reference)
    except Exception as e:
        logger.error("Error updating payment %s: %s", payment_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Payment update failed: {str(e)}")

    return {"status": "ok"}
