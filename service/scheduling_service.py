import uuid
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
SAST = ZoneInfo("Africa/Johannesburg")

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models.models import (
    Users,
    DoctorProfiles,
    DoctorAvailability,
    Visit,
    Consultations,
)
from service.email_service import EmailService

logger = logging.getLogger(__name__)


# How far ahead we search for an open slot. Doctor availability is a
# recurring weekly pattern that applies for the whole year, so we only
# need to look far enough ahead to find the next open slot.
LOOKAHEAD_DAYS = 90

# Don't offer a slot that starts in the next few minutes — gives the
# system/patient a realistic buffer before a call is joinable.
MIN_BOOKING_BUFFER_MINUTES = 15


class SchedulingService:

    @staticmethod
    def _resolve_consultation(db: Session, patient_id: int, consultation_id: int | None):
        query = db.query(Consultations).filter(
            Consultations.patient_id == patient_id,
            Consultations.status == "paid",
        )

        if consultation_id is not None:
            consultation = query.filter(Consultations.id == consultation_id).first()
        else:
            consultation = query.order_by(Consultations.created_at.desc()).first()

        if not consultation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No paid consultation found for this patient",
            )

        return consultation

    @staticmethod
    def _active_doctors(db: Session):
        return (
            db.query(Users)
            .join(DoctorProfiles, Users.id == DoctorProfiles.user_id)
            .filter(
                Users.role == "doctor",
                DoctorProfiles.verification_status == "active",
            )
            .order_by(Users.id.asc())
            .all()
        )

    @staticmethod
    def _rotation_start_index(db: Session, doctors: list) -> int:
        """
        Round-robin fairness: start looking from the doctor right after
        whoever was most recently assigned a visit, so appointments rotate
        evenly across all active doctors instead of always favouring the
        same one.
        """
        if not doctors:
            return 0

        last_visit = db.query(Visit).order_by(Visit.created_at.desc()).first()

        if not last_visit:
            return 0

        doctor_ids = [doctor.id for doctor in doctors]
        if last_visit.doctor_id in doctor_ids:
            return (doctor_ids.index(last_visit.doctor_id) + 1) % len(doctor_ids)

        return 0

    @staticmethod
    def _find_next_slot_for_doctor(db: Session, doctor_id: int, earliest_start: datetime):
        availability_slots = (
            db.query(DoctorAvailability)
            .filter(
                DoctorAvailability.doctor_id == doctor_id,
                DoctorAvailability.is_active == True,
            )
            .all()
        )

        if not availability_slots:
            return None

        window_end = earliest_start + timedelta(days=LOOKAHEAD_DAYS)

        # Pre-load this doctor's already booked slots within the lookahead
        # window so we can quickly skip times that are taken.
        booked_times = {
            visit.scheduled_at
            for visit in db.query(Visit).filter(
                Visit.doctor_id == doctor_id,
                Visit.status == "scheduled",
                Visit.scheduled_at >= earliest_start,
                Visit.scheduled_at <= window_end,
            )
        }

        slots_by_day: dict[int, list[DoctorAvailability]] = {}
        for slot in availability_slots:
            slots_by_day.setdefault(slot.day_of_week, []).append(slot)

        for day_offset in range(LOOKAHEAD_DAYS + 1):
            candidate_date = (earliest_start + timedelta(days=day_offset)).date()
            day_of_week = candidate_date.weekday()  # 0=Monday ... 6=Sunday

            for slot in slots_by_day.get(day_of_week, []):
                current_time = datetime.combine(candidate_date, slot.start_time)
                end_boundary = datetime.combine(candidate_date, slot.end_time)
                step = timedelta(minutes=slot.slot_duration_minutes)

                while current_time + step <= end_boundary:
                    if current_time >= earliest_start and current_time not in booked_times:
                        return current_time
                    current_time += step

        return None

    @staticmethod
    def _doctor_name(db: Session, doctor: Users) -> str:
        profile = (
            db.query(DoctorProfiles)
            .filter(DoctorProfiles.user_id == doctor.id)
            .first()
        )
        return profile.full_legal_name if profile else doctor.username

    @staticmethod
    def preview_next_appointment(
            db: Session,
            patient_id: int,
            limit: int = 5,
    ):
        """
        Returns up to `limit` open time slots for the patient to choose
        from, WITHOUT booking anything. This runs BEFORE payment — the
        patient only needs to be authenticated, no paid consultation is
        required yet. Each slot is pre-assigned to a specific doctor using
        round-robin fairness across all active doctors' recurring weekly
        availability, so workload is distributed evenly rather than always
        filling the same doctor's calendar first. Nothing is written to the
        database — after payment, call confirm_appointment with the slot
        the patient picked to actually create the visit.
        """
        doctors = SchedulingService._active_doctors(db)
        if not doctors:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active doctors available",
            )

        start_index = SchedulingService._rotation_start_index(db, doctors)
        base_earliest_start = (
            datetime.now(SAST).replace(tzinfo=None)
            + timedelta(minutes=MIN_BOOKING_BUFFER_MINUTES)
        )
        doctor_count = len(doctors)

        # Track each doctor's own search cursor so that if we need to loop
        # back to the same doctor for a later slot, we resume searching
        # after the slot we already offered instead of finding it again.
        search_cursors = {doctor.id: base_earliest_start for doctor in doctors}

        slots = []
        offset = 0
        max_cycles = doctor_count * (limit + 2)  # generous cap to avoid spinning if slots run out

        for cycles in range(max_cycles):
            if len(slots) >= limit:
                break

            doctor = doctors[(start_index + offset) % doctor_count]
            offset += 1

            slot_time = SchedulingService._find_next_slot_for_doctor(
                db, doctor.id, search_cursors[doctor.id]
            )
            if slot_time is None:
                continue

            slots.append({
                "doctor_id": doctor.id,
                "doctor_name": SchedulingService._doctor_name(db, doctor),
                "open_at": slot_time,
            })
            # Move this doctor's cursor past the slot just offered so the
            # next pass (if we cycle back around) finds a later time.
            search_cursors[doctor.id] = slot_time + timedelta(minutes=1)

        if not slots:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No available appointment slots found for any doctor",
            )

        slots.sort(key=lambda s: s["open_at"])

        return {
            "slots": slots,
        }

    @staticmethod
    def confirm_appointment(
            db: Session,
            patient_id: int,
            doctor_id: int,
            open_at: datetime,
            consultation_id: int | None = None,
    ):
        """
        Books the previously previewed doctor + open slot. Re-validates the
        slot is still free (another patient may have taken it in the
        meantime) before committing the visit.
        """
        consultation = SchedulingService._resolve_consultation(db, patient_id, consultation_id)

        doctor = (
            db.query(Users)
            .join(DoctorProfiles, Users.id == DoctorProfiles.user_id)
            .filter(
                Users.id == doctor_id,
                Users.role == "doctor",
                DoctorProfiles.verification_status == "active",
            )
            .first()
        )

        if not doctor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Doctor not found or not active",
            )

        clash = (
            db.query(Visit)
            .filter(
                Visit.doctor_id == doctor_id,
                Visit.scheduled_at == open_at,
                Visit.status == "scheduled",
            )
            .first()
        )
        if clash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This slot was just booked by someone else. Please request a new preview.",
            )

        video_channel = f"visit-{uuid.uuid4()}"
        visit = Visit(
            consultation_id=consultation.id,
            patient_id=patient_id,
            doctor_id=doctor.id,
            scheduled_at=open_at,
            status="scheduled",
            channel_name=video_channel,
            video_provider="agora",
            video_status="waiting",
        )

        db.add(visit)
        db.commit()
        db.refresh(visit)

        patient = db.get(Users, patient_id)
        doctor_name = SchedulingService._doctor_name(db, doctor)
        scheduled_at_display = visit.scheduled_at.strftime("%A, %d %B %Y at %H:%M") + " (SAST)"

        if patient:
            EmailService.send_booking_confirmation_emails(
                patient_email=patient.email,
                patient_name=patient.username,
                doctor_email=doctor.email,
                doctor_name=doctor_name,
                scheduled_at_display=scheduled_at_display,
            )
        else:
            logger.warning(
                "Could not send booking confirmation emails — patient_id=%s not found",
                patient_id,
            )

        return {
            "visit_id": visit.id,
            "consultation_id": consultation.id,
            "doctor_id": doctor.id,
            "doctor_name": doctor_name,
            "scheduled_at": visit.scheduled_at,
            "status": visit.status,
        }
