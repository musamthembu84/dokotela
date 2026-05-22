from sqlalchemy.orm import Session
from fastapi import HTTPException, status
import logging
from models.models import Users, DoctorProfiles, DoctorOnboardingRequest, DoctorAvailability, OnboardingTokens
logger = logging.getLogger(__name__)

class DoctorOnboardingService:
    @staticmethod
    def onboard(db: Session, token: str, request: DoctorOnboardingRequest) -> dict:

        onboarding_token = (
            db.query(OnboardingTokens).filter(OnboardingTokens.token == token).first()
        )

        logger.debug(f"Token: {onboarding_token.token}")



        if not onboarding_token:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")

        user = db.query(Users).filter(Users.id == onboarding_token.doctor_id).first()

        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        if user.role != "doctor":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only doctors can onboard")

        if user.status != "pending":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="Doctor is already onboarded or in process")

        if not request.availability:
            raise HTTPException(status_code=status.HTTP_400_NOT_FOUND, detail="Availability cannot be empty,"
                                                                              "please select at least one slot where you are available")

        for slot in request.availability:
            if slot.start_time >= slot.end_time:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Invalid availability for day {slot.day_of_week}: "
                        "start_time must be before end_time"
                    ),
                )

        try:
            profile = DoctorProfiles(
                user_id=user.id,
                full_legal_name=request.full_legal_name,
                hpcsa_number=request.hpcsa_number,
                speciality = request.speciality,
                identity_document_path=request.identity_document_path,
                qualification_path=request.qualification_path,
                verification_status="pending"
            )
            db.add(profile)

            # create availability rows
            created_slots = 0
            for slot in request.availability:
                availability = DoctorAvailability(
                    doctor_id=user.id,
                    day_of_week=slot.day_of_week,
                    start_time=slot.start_time,
                    end_time=slot.end_time,
                    slot_duration_minutes=slot.slot_duration_minutes,
                    is_active=True
                )
                db.add(availability)
                created_slots += 1
            user.status = "onboarding"
            db.add(user)



            db.commit()
            db.refresh(profile)
            db.refresh(user)

            # TODO:
            # send_email(
            #     to=admin@dokotela.com,
            #     subject="New doctor awaiting approval",
            #     body=f"Doctor {user.email} submitted onboarding."
            # )

            return {
                "message": (
                    "Doctor onboarding submitted successfully. "
                    "Your profile is pending verification."
                ),
                "user_id": user.id,
                "verification_status": "pending",
                "availability_slots_created": created_slots,
            }
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
