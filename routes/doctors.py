from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from core.dependency import db_dependency
from core.jwt_utils import get_current_user
from models.models import (
    DoctorAppointmentResponse,
    DoctorAppointmentsListResponse,
    PatientInfoResponse,
)
from service.visit_service import VisitService

router = APIRouter(prefix="/doctors", tags=["Doctors"])

token_dep = Annotated[dict, Depends(get_current_user)]


def _authorize_doctor(token: dict):
    if token.get("role") != "doctor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only doctors can access this endpoint",
        )


def _to_appointment_response(visit) -> DoctorAppointmentResponse:
    return DoctorAppointmentResponse(
        id=visit.id,
        consultation_id=visit.consultation_id,
        patient_id=visit.patient_id,
        patient=PatientInfoResponse.model_validate(visit.patient),
        scheduled_at=visit.scheduled_at,
        status=visit.status,
        channel_name=visit.channel_name,
        video_provider=visit.video_provider,
        video_status=visit.video_status,
    )


@router.get(
    "/appointments",
    response_model=DoctorAppointmentsListResponse,
    status_code=status.HTTP_200_OK,
)
async def get_doctor_appointments(
        db: db_dependency,
        token: token_dep,
):
    """
    Returns all upcoming appointments for the logged-in doctor,
    including which patient each appointment is with.
    """
    _authorize_doctor(token)

    visits = VisitService.get_doctor_appointments(db=db, doctor_id=token["id"])

    appointments = [_to_appointment_response(visit) for visit in visits]

    return DoctorAppointmentsListResponse(
        appointments=appointments,
        total=len(appointments),
    )


@router.get(
    "/appointments/{visit_id}",
    response_model=DoctorAppointmentResponse,
    status_code=status.HTTP_200_OK,
)
async def get_doctor_appointment(
        visit_id: int,
        db: db_dependency,
        token: token_dep,
):
    """
    Returns a single appointment belonging to the logged-in doctor,
    including the patient it is with.
    """
    _authorize_doctor(token)

    visit = VisitService.get_doctor_appointment(
        db=db, doctor_id=token["id"], visit_id=visit_id
    )

    return _to_appointment_response(visit)
