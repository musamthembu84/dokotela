from fastapi import APIRouter, Depends, Request, HTTPException
from typing import Annotated
import logging

from core.dependency import db_dependency
from models.models import Payments, CheckoutResponse, CheckoutRequest
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
             current_user: int = Depends(get_current_user)):

    logger.info("Incoming checkout request: %s", request)
    payment = PaymentService.create_payment(
        db=db,
        user_id=current_user,
        amount=int(request.amount),
        consultation_session_id=request.consultation_id
    )

    payment_url = PaymentService.build_payment_url(payment)

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
    """Return URL handler — PayFast redirects the user here after payment."""
    payment = db.get(Payments, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return {
        "message": "Payment received. Awaiting confirmation from PayFast.",
        "payment_id": payment.id,
        "status": payment.status,
        "amount": float(payment.amount),
    }


@router.get("/cancel")
def payment_cancel(payment_id: int, db: db_dependency):
    """Cancel URL handler — PayFast redirects here when the user cancels."""
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
async def payfast_webhook(request: Request, db: db_dependency):
    form = await request.form()
    data = dict(form)

    logger.info("ITN received from PayFast: %s", data)

    is_valid = PaymentService.verify_itn(data)

    if not is_valid:
        logger.error("ITN validation failed for data: %s", data)
        raise HTTPException(
            status_code=400,
            detail="Invalid PayFast notification",
        )

    payment_id = int(data["m_payment_id"])
    provider_reference = data.get("pf_payment_id")
    payment_status = data.get("payment_status")

    logger.info("ITN payment_id=%s status=%s reference=%s", payment_id, payment_status, provider_reference)

    try:
        if payment_status == "COMPLETE":
            logger.info("Calling mark_payment_completed for payment_id=%s", payment_id)
            payment = PaymentService.mark_payment_completed(
                db=db,
                payment_id=payment_id,
                provider_reference=provider_reference,
            )
            logger.info("Payment %s marked completed. DB status=%s reference=%s", payment_id, payment.status,
                        payment.payment_reference)
        else:
            logger.info("Calling mark_payment_failed for payment_id=%s", payment_id)
            PaymentService.mark_payment_failed(db=db, payment_id=payment_id)
            logger.info("Payment %s marked failed.", payment_id)
    except Exception as e:
        logger.error("Error updating payment %s: %s", payment_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Payment update failed: {str(e)}")

    return {"status": "ok"}
