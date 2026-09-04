import uuid
from datetime import timedelta, datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models.models import (
    Visit,
    Users,
    Consultations,
    DoctorProfiles,
    DoctorAvailability,
)
from service.agora_service import AgoraService
from core.config import settings


class VisitService:

    @staticmethod
    def create_visit(db: Session, patient_id: int, request):
        # ------------------------------------------------------------------
        # 1. Resolve consultation
        #    - If consultation_id is provided, use it.
        #    - Otherwise auto-pick the patient's latest paid consultation.
        # ------------------------------------------------------------------
        consultation_query = db.query(Consultations).filter(
            Consultations.patient_id == patient_id,
            Consultations.status == "paid",
            )

        if getattr(request, "consultation_id", None) is not None:
            consultation = consultation_query.filter(
                Consultations.id == request.consultation_id
            ).first()
        else:
            consultation = consultation_query.order_by(
                Consultations.created_at.desc()
            ).first()

        if not consultation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No paid consultation found for this patient",
            )

        # ------------------------------------------------------------------
        # 2. Extract scheduling info
        # ------------------------------------------------------------------
        requested_datetime = request.scheduled_at
        requested_day = requested_datetime.weekday()
        requested_time = requested_datetime.time()

        # ------------------------------------------------------------------
        # 3. Get all active verified doctors
        # ------------------------------------------------------------------
        doctors = (
            db.query(Users)
            .join(DoctorProfiles, Users.id == DoctorProfiles.user_id)
            .filter(
                Users.role == "doctor",
                DoctorProfiles.verification_status == "active",
                )
            .all()
        )

        if not doctors:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No doctors available",
            )

        # ------------------------------------------------------------------
        # 4. Find first available doctor at requested time
        # ------------------------------------------------------------------
        selected_doctor = None

        for doctor in doctors:
            availability_slots = (
                db.query(DoctorAvailability)
                .filter(
                    DoctorAvailability.doctor_id == doctor.id,
                    DoctorAvailability.day_of_week == requested_day,
                    DoctorAvailability.is_active == True,
                    )
                .all()
            )

            if not availability_slots:
                continue

            for slot in availability_slots:
                within_range = slot.start_time <= requested_time <= slot.end_time
                if not within_range:
                    continue

                # Skip doctor if they already have a clashing scheduled visit
                clash = (
                    db.query(Visit)
                    .filter(
                        Visit.doctor_id == doctor.id,
                        Visit.scheduled_at == requested_datetime,
                        Visit.status == "scheduled",
                        )
                    .first()
                )
                if clash:
                    continue

                selected_doctor = doctor
                break

            if selected_doctor:
                break

        if not selected_doctor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No doctor available at that time",
            )

        # ------------------------------------------------------------------
        # 5. Create the visit + video channel
        # ------------------------------------------------------------------
        video_channel = f"visit-{uuid.uuid4()}"
        visit = Visit(
            consultation_id=consultation.id,
            patient_id=patient_id,
            doctor_id=selected_doctor.id,
            scheduled_at=requested_datetime,
            status="scheduled",
            channel_name=video_channel,
            video_provider="agora",
            video_status="waiting",
        )

        db.add(visit)
        db.commit()
        db.refresh(visit)

        return {
            "message": "Visit scheduled successfully",
            "visit_id": visit.id,
            "consultation_id": consultation.id,
            "assigned_doctor_id": selected_doctor.id,
            "scheduled_at": visit.scheduled_at,
            "status": visit.status,
        }

    # ----------------------------------------------------------------------
    # Get all visits for the logged-in user (patient or doctor)
    # ----------------------------------------------------------------------
    @staticmethod
    def get_my_visits(db: Session, user_id: int):
        return (
            db.query(Visit)
            .filter(
                ((Visit.patient_id == user_id) | (Visit.doctor_id == user_id))
                & (Visit.scheduled_at >= datetime.now())
            )
            .order_by(Visit.scheduled_at.desc())
            .all()
        )

    # ----------------------------------------------------------------------
    # Join a visit — returns Agora token if user is authorized & in window
    # ----------------------------------------------------------------------
    @staticmethod
    def join_visit(db: Session, user_id: int, visit_id: int):
        visit = db.query(Visit).filter(Visit.id == visit_id).first()

        if not visit:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Visit not found",
            )

        if visit.patient_id != user_id and visit.doctor_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to join this visit",
            )

        if visit.status != "scheduled":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Visit is not in a joinable state",
            )

        now = datetime.now()
        allowed_before = visit.scheduled_at - timedelta(minutes=10)
        allowed_after = visit.scheduled_at + timedelta(hours=1)

        if not (allowed_before <= now <= allowed_after):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Too early or too late to join this visit",
            )

        agora_token = AgoraService.generate_agora_token(
            channel_name=visit.channel_name,
            uid=user_id,
        )

        visit.video_status = "live"
        db.commit()

        return {
            "channel_name": visit.channel_name,
            "agora_token": agora_token,
            "app_id": settings.AGORA_APP_ID,
            "uid": user_id,
            "video_provider": visit.video_provider,
        }