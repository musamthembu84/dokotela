from typing import List, Annotated

from fastapi import APIRouter, Depends, HTTPException
from passlib.context import CryptContext

from core.dependency import db_dependency
from core.jwt_utils import get_current_user, authorize_user_access
from models.models import Users, Visit, Consultations, VisitCreate, VisitResponse, VisitStatusUpdate

router = APIRouter(prefix="/visits", tags=["visits"])
bcrypt_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

token_dep = Annotated[dict, Depends(get_current_user)]


@router.post("/", response_model=VisitResponse)
async def create_visit(visit_in: VisitCreate, db: db_dependency, token: token_dep):
    patient = db.query(Users).filter(Users.id == visit_in.patient_id).first()
    doctor = db.query(Users).filter(Users.id == visit_in.doctor_id).first()
    consultation = (db.query(Consultations).filter(
        Consultations.user_id == visit_in.patient_id,
        Consultations.status == "paid"
    )
                    .order_by(Consultations.created_at.desc())
                    .first())

    if not patient or not doctor:
        raise HTTPException(status_code=404, detail="Patient or doctor not found")

    ## authorize_user_access()
    authorize_user_access(visit_in.patient_id, token)

    visit = Visit(
        patient_id=visit_in.patient_id,
        doctor_id=visit_in.doctor_id,
        consultation_id=consultation.id,
        scheduled_for=visit_in.scheduled_for,
        status="scheduled"
    )

    db.add(visit)
    db.commit()
    db.refresh(visit)

    return visit


@router.get("/", response_model=List[VisitResponse])
async def list_visits(db: db_dependency, token: token_dep):
    role = token["role"]
    user_id = token["id"]

    if role == "patient":
        visits = db.query(Visit).filter(Visit.patient_id == user_id).all()
        authorize_user_access(user_id, token)
    elif role == "doctor":
        visits = db.query(Visit).filter(Visit.doctor_id == user_id).all()
        authorize_user_access(user_id, token)
    else:
        visits = db.query(Visit).all()

    return visits


@router.patch("/{visit_id}/confirmBooking", response_model=VisitResponse)
async def update_visit_status(db: db_dependency, visit_id: int, payload: VisitStatusUpdate, token: token_dep):
    visit = db.query(Visit).filter(Visit.id == visit_id).first()

    if not visit:
        raise HTTPException(status_code=404, detail="Booking not found")

    authorize_user_access(visit.doctor_id, token)

    if token["id"] not in [visit.patient_id, visit.doctor_id]:
        raise HTTPException(status_code=403, detail="Not authorized to update booking")

    visit.status = payload.status
    db.commit()
    db.refresh(visit)
    return visit


import uuid
from datetime import datetime, timedelta

@router.post("/{visit_id}/join")
def join_visit(visit_id: int, db: db_dependency, token: token_dep):
    user_id = int(token["id"])

    visit = db.query(Visit).filter(Visit.id == visit_id).first()
    if not visit:
        raise HTTPException(404, "Visit not found")

    if user_id not in [visit.patient_id, visit.doctor_id]:
        raise HTTPException(403, "Not allowed")

    if datetime.utcnow() < visit.scheduled_at - timedelta(minutes=10):
        raise HTTPException(400, "Too early to join")

    if not visit.call_channel:
        visit.call_provider = "agora"
        visit.call_channel = f"visit_{visit.id}_{uuid.uuid4().hex[:6]}"
        visit.status = "in_call"
        db.commit()

    return {
        "provider": visit.call_provider,
        "channel": visit.call_channel,
        "join_url": f"agora://{visit.call_channel}"
    }
