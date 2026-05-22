import logging

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models.models import Users, DoctorProfiles

logger = logging.getLogger(__name__)

class AdminService:

    @staticmethod
    def get_pending_doctors(db: Session) -> list[type[DoctorProfiles]]:

        pending_doctors = (
            db.query(DoctorProfiles)
            .filter(DoctorProfiles.verification_status == "pending")
            .all()
        )

        return pending_doctors


    @staticmethod
    def approve_doctor(db: Session, doctor_profile_id: int) -> type[DoctorProfiles]:
        """
        Set DoctorProfiles.verification_status = 'active'
        and Users.status = 'active' for the linked user.
        """
        profile = db.get(DoctorProfiles, doctor_profile_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Doctor profile with id {doctor_profile_id} not found",
            )

        if profile.verification_status == "active":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Doctor is already approved",
            )

        user = db.get(Users, profile.user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User linked to doctor profile {doctor_profile_id} not found",
            )

        try:
            profile.verification_status = "active"
            user.status = "active"
            db.commit()
            db.refresh(profile)
            db.refresh(user)
            logger.info(
                "Doctor approved: profile_id=%s user_id=%s username=%s",
                profile.id, user.id, user.username,
            )
            return profile
        except Exception as e:
            db.rollback()
            logger.error("Failed to approve doctor profile_id=%s: %s", doctor_profile_id, e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e),
            )
