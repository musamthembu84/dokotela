from typing import Annotated

from fastapi import APIRouter, Depends, status

from core.dependency import db_dependency
from core.jwt_utils import get_current_user
from models.models import (
    ScheduleAppointmentRequest,
    SchedulePreviewResponse,
    ScheduleConfirmRequest,
    ScheduleAppointmentResponse,
)
from service.scheduling_service import SchedulingService

router = APIRouter(prefix="/scheduling", tags=["Scheduling"])

token_dep = Annotated[dict, Depends(get_current_user)]


@router.post("/preview", response_model=SchedulePreviewResponse, status_code=status.HTTP_200_OK)
async def preview_next_appointment(
        request: ScheduleAppointmentRequest,
        db: db_dependency,
        token: token_dep,
):
    """
    Returns open appointment slots that any authenticated patient can view
    — this runs BEFORE payment, so no paid consultation is required yet.
    It only shows which times are open, with each open slot pre-assigned
    to a doctor using round-robin so availability rotates fairly across
    all active doctors instead of always favouring the same one. The
    patient does not choose the doctor — the system decides automatically.
    Call /scheduling/confirm (after payment) to actually book one of the
    returned open slots.
    """
    result = SchedulingService.preview_next_appointment(
        db=db,
        patient_id=token["id"],
        limit=request.limit,
    )
    return SchedulePreviewResponse(**result)


@router.post("/confirm", response_model=ScheduleAppointmentResponse, status_code=status.HTTP_201_CREATED)
async def confirm_appointment(
        request: ScheduleConfirmRequest,
        db: db_dependency,
        token: token_dep,
):
    """
    Books the doctor + slot previously returned by /scheduling/preview.
    Re-checks the slot is still free before committing, in case another
    patient booked it in the meantime.
    """
    result = SchedulingService.confirm_appointment(
        db=db,
        patient_id=token["id"],
        doctor_id=request.doctor_id,
        open_at=request.open_at,
        consultation_id=request.consultation_id,
    )
    return ScheduleAppointmentResponse(**result)
