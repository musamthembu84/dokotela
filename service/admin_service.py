import logging

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models.models import Users, DoctorProfiles, BankingDetails, BankingDetailsResponse, PendingDoctorResponse

logger = logging.getLogger(__name__)

class AdminService:

    @staticmethod
    def get_pending_doctors(db: Session) -> list[PendingDoctorResponse]:
        profiles = (
            db.query(DoctorProfiles)
            .filter(DoctorProfiles.verification_status.in_(["pending", "pending_review"]))
            .all()
        )

        results = []
        for profile in profiles:
            banking = (
                db.query(BankingDetails)
                .filter(BankingDetails.doctor_id == profile.user_id)
                .first()
            )
            results.append(
                PendingDoctorResponse(
                    id=profile.id,
                    user_id=profile.user_id,
                    full_legal_name=profile.full_legal_name,
                    id_number=profile.id_number,
                    practice_number=profile.practice_number,
                    speciality=profile.speciality,
                    verification_status=profile.verification_status,
                    verifynow_reference=profile.verifynow_reference,
                    banking=BankingDetailsResponse(
                        bank_name=banking.bank_name,
                        account_holder_name=banking.account_holder_name,
                        account_number_masked=f"****{banking.account_number_last4}",
                        branch_code=banking.branch_code,
                        account_type=banking.account_type,
                        proof_of_banking_path=banking.proof_of_banking_path,
                    ) if banking else None,
                )
            )
        return results


    @staticmethod
    def approve_doctor(db: Session, doctor_profile_id: int) -> type[DoctorProfiles]:
        """
        Set DoctorProfiles.verification_status = 'active' and Users.status
        = 'active' for the linked user. This is the only approval action -
        banking details submitted at finalize aren't separately reviewed.
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
