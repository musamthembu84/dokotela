from fastapi import APIRouter, Depends
from typing import Annotated

from passlib.context import CryptContext

from core.dependency import db_dependency
from core.intake_ai import mock_summary
from models.models import Payments, Consultations, PaymentRequest, PaymentResponse
from core.jwt_utils import get_current_user, authorize_user_access
from core.session_store import get_message

router = APIRouter(prefix="/payments", tags=["payments"])
bcrypt_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

token_dep = Annotated[dict, Depends(get_current_user)]


@router.post("/", response_model=PaymentResponse)
async def create_payment(req: PaymentRequest, db: db_dependency, token: token_dep):
    user_id = int(token["id"])

    authorize_user_access(user_id, token)

    messages = get_message(req.session_id)

    summary = mock_summary(messages)

    payment = Payments(
        user_id=user_id,
        amount=req.amount,
        provider=req.provider,
        reference=req.reference,
        status="paid"
    )

    db.add(payment)
    db.commit()
    db.refresh(payment)

    consultation = Consultations(
        user_id=user_id,
        chief_complaint=summary["chief_complaint"],
        risk_level=summary["risk_level"],
        recommended_speciality=summary["recommended_speciality"],
        summary=summary["summary"],
        status="paid",
        payment_id=payment.id
    )

    db.add(consultation)
    db.commit()
    db.refresh(consultation)

    payment_response = PaymentResponse(
        payment_id=payment.id,
        consultation_id=consultation.id,
        status=consultation.status

    )
    #later we need to only return consultation_id
    return payment_response
