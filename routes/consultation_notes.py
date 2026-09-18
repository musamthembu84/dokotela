from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from core.dependency import db_dependency
from core.jwt_utils import get_current_user
from models.models import (
    ConsultationNoteResponse,
    ConsultationNotesListResponse,
    DoctorNoteCreateRequest,
)
from service.consultation_notes_service import ConsultationNotesService

router = APIRouter(prefix="/consultations", tags=["Consultation Notes"])

token_dep = Annotated[dict, Depends(get_current_user)]


@router.get(
    "/notes",
    response_model=ConsultationNotesListResponse,
    status_code=status.HTTP_200_OK,
)
async def get_my_notes(
        db: db_dependency,
        token: token_dep,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=10, ge=1, le=100),
        consultation_id: int | None = Query(
            default=None,
            description="Required for doctors — identifies which patient's "
                        "history to view. Ignored for patients (always their own).",
        ),
):
    """
    Returns paginated note history (AI + doctor authored), newest first.

    - Patient: always returns their own full note history.
    - Doctor: must pass consultation_id (one of their assigned
      consultations). Returns the FULL note history of the patient tied
      to that consultation, across all of that patient's consultations —
      not just the one passed in. The doctor must be assigned to the
      given consultation via a visit, otherwise 403.
    """
    if token["role"] == "doctor":
        if consultation_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="consultation_id is required for doctors to view a patient's history",
            )

        return ConsultationNotesService.get_patient_history_for_doctor(
            db=db,
            doctor_id=token["id"],
            consultation_id=consultation_id,
            page=page,
            page_size=page_size,
        )

    return ConsultationNotesService.get_notes_for_patient(
        db=db,
        patient_id=token["id"],
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{consultation_id}/notes",
    response_model=list[ConsultationNoteResponse],
    status_code=status.HTTP_200_OK,
)
async def get_consultation_notes(
        consultation_id: int,
        db: db_dependency,
        token: token_dep,
):
    """
    Returns every note for a single consultation (AI + doctor authored),
    newest first. Accessible only to the owning patient or the doctor
    assigned to the consultation.
    """
    return ConsultationNotesService.get_notes_for_consultation(
        db=db,
        user_id=token["id"],
        role=token["role"],
        consultation_id=consultation_id,
    )


@router.put(
    "/{consultation_id}/notes/doctor",
    response_model=ConsultationNoteResponse,
    status_code=status.HTTP_200_OK,
)
async def upsert_doctor_note(
        consultation_id: int,
        request: DoctorNoteCreateRequest,
        db: db_dependency,
        token: token_dep,
):
    """
    Lets the assigned doctor set/update their note on the consultation's
    note row, alongside the existing AI note, so the two can be compared.
    MVP model: one row per consultation carries both ai_note and doctor_note.
    """
    if token["role"] != "doctor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only doctors can create doctor notes",
        )

    return ConsultationNotesService.create_doctor_note(
        db=db,
        doctor_id=token["id"],
        consultation_id=consultation_id,
        note_type=request.type,
        note_text=request.doctor_note,
    )
