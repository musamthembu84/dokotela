import logging

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models.models import ConsultationNotes, Consultations, Visit

logger = logging.getLogger(__name__)


class ConsultationNotesService:

    # ----------------------------------------------------------------------
    # Patient: get all notes (AI + doctor) belonging to the logged-in
    # patient, newest first, paginated.
    # ----------------------------------------------------------------------
    @staticmethod
    def get_notes_for_patient(db: Session, patient_id: int, page: int, page_size: int):
        return ConsultationNotesService._paginate_notes_for_patient(
            db=db, patient_id=patient_id, page=page, page_size=page_size
        )

    # ----------------------------------------------------------------------
    # Doctor: get the full note history (AI + doctor) for the patient
    # attached to a given consultation, newest first, paginated. The
    # consultation_id is only used to resolve + authorize which patient's
    # history the doctor is allowed to see (they must be assigned via a
    # visit) — the returned notes span ALL of that patient's consultations,
    # not just the one passed in.
    # ----------------------------------------------------------------------
    @staticmethod
    def get_patient_history_for_doctor(
        db: Session, doctor_id: int, consultation_id: int, page: int, page_size: int
    ):
        consultation = db.get(Consultations, consultation_id)
        if not consultation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Consultation not found",
            )

        is_assigned = (
            db.query(Visit)
            .filter(
                Visit.consultation_id == consultation_id,
                Visit.doctor_id == doctor_id,
            )
            .first()
        )

        if not is_assigned:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not assigned to this consultation",
            )

        return ConsultationNotesService._paginate_notes_for_patient(
            db=db, patient_id=consultation.patient_id, page=page, page_size=page_size
        )

    # ----------------------------------------------------------------------
    # Shared pagination logic for a patient's full note history.
    # ----------------------------------------------------------------------
    @staticmethod
    def _paginate_notes_for_patient(db: Session, patient_id: int, page: int, page_size: int):
        base_query = (
            db.query(ConsultationNotes)
            .join(Consultations, ConsultationNotes.consultation_id == Consultations.id)
            .filter(Consultations.patient_id == patient_id)
        )

        total = base_query.count()

        notes = (
            base_query.order_by(ConsultationNotes.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        has_more = page * page_size < total

        return {
            "notes": notes,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_more": has_more,
        }

    # ----------------------------------------------------------------------
    # Get all notes for a single consultation, restricted to the owning
    # patient or the doctor assigned to it via a visit.
    # ----------------------------------------------------------------------
    @staticmethod
    def get_notes_for_consultation(db: Session, user_id: int, role: str, consultation_id: int):
        consultation = db.get(Consultations, consultation_id)
        if not consultation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Consultation not found",
            )

        ConsultationNotesService._authorize_consultation_access(
            db=db, user_id=user_id, role=role, consultation=consultation
        )

        notes = (
            db.query(ConsultationNotes)
            .filter(ConsultationNotes.consultation_id == consultation_id)
            .order_by(ConsultationNotes.created_at.desc())
            .all()
        )

        return notes

    # ----------------------------------------------------------------------
    # Doctor: attach their note to the consultation's note row (the row
    # created for the AI note at payment time). MVP model — one row per
    # consultation holding both ai_note and doctor_note side by side.
    # ----------------------------------------------------------------------
    @staticmethod
    def create_doctor_note(
        db: Session, doctor_id: int, consultation_id: int, note_type: str | None, note_text: str
    ) -> ConsultationNotes:
        consultation = db.get(Consultations, consultation_id)
        if not consultation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Consultation not found",
            )

        is_assigned = (
            db.query(Visit)
            .filter(
                Visit.consultation_id == consultation_id,
                Visit.doctor_id == doctor_id,
            )
            .first()
        )

        if not is_assigned:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not assigned to this consultation",
            )

        note = (
            db.query(ConsultationNotes)
            .filter(ConsultationNotes.consultation_id == consultation_id)
            .order_by(ConsultationNotes.created_at.desc())
            .first()
        )

        if note:
            note.doctor_note = note_text
            if note_type:
                note.type = note_type
        else:
            # No AI note exists yet for this consultation — create the row.
            note = ConsultationNotes(
                consultation_id=consultation_id,
                author="doctor",
                type=note_type or "SOAP_DOCTOR",
                doctor_note=note_text,
            )
            db.add(note)

        db.commit()
        db.refresh(note)

        logger.info(
            "Doctor note saved: consultation_id=%s doctor_id=%s note_id=%s",
            consultation_id,
            doctor_id,
            note.id,
        )

        return note

    # ----------------------------------------------------------------------
    # Internal helper: only the owning patient or the assigned doctor may
    # view notes for a consultation.
    # ----------------------------------------------------------------------
    @staticmethod
    def _authorize_consultation_access(db: Session, user_id: int, role: str, consultation: Consultations):
        if role == "patient" and consultation.patient_id == user_id:
            return

        if role == "doctor":
            is_assigned = (
                db.query(Visit)
                .filter(
                    Visit.consultation_id == consultation.id,
                    Visit.doctor_id == user_id,
                )
                .first()
            )
            if is_assigned:
                return

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access notes for this consultation",
        )
