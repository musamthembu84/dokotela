import logging
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core import doctor_registration_store as reg_store
from core import storage
from models.models import (
    Users,
    DoctorProfiles,
    DoctorAvailability,
    BankingDetails,
    DoctorRegistrationStartRequest,
    DoctorIdentityVerificationRequest,
    DoctorFinalizeRequest,
)
from core.security import hash_password
from core.crypto import encrypt
from service.email_service import EmailService
from service.verifynow_client import VerifyNowClient

logger = logging.getLogger(__name__)

# Speciality isn't collected during registration yet - default it for now
# and let doctors update it later (e.g. via admin or a future profile edit).
DEFAULT_SPECIALITY = "General Practice"


class DoctorOnboardingService:

    # ---------------------------------------------------------------
    # Step 1: username/email/password - held only in Redis, nothing
    # written to Postgres yet.
    # ---------------------------------------------------------------
    @staticmethod
    def start(db: Session, request: DoctorRegistrationStartRequest) -> dict:
        existing = (
            db.query(Users)
            .filter((Users.email == request.email) | (Users.username == request.username))
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username or email is already registered",
            )

        registration_id = reg_store.create_registration(
            username=request.username,
            email=request.email,
            hashed_password=hash_password(request.password),
        )

        return {
            "registration_id": registration_id,
            "message": "Registration started. Please complete identity verification next.",
            "expires_in_minutes": reg_store.REGISTRATION_TTL_MINUTES,
        }

    # ---------------------------------------------------------------
    # Step 2: VerifyNow ID + Photo check against Home Affairs. Still no
    # DB writes - only the Redis registration blob is updated.
    # ---------------------------------------------------------------
    @staticmethod
    def verify_identity(request: DoctorIdentityVerificationRequest) -> dict:
        reg = reg_store.get_registration(request.registration_id)
        if reg is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Registration not found or has expired, please start again",
            )

        if reg.get("status") == "verified":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Identity already verified")

        result = VerifyNowClient.verify_face_match(
            id_number=request.id_number,
            selfie_image_base64=request.selfie_image_base64,
        )
        outcome = result["outcome"]

        if outcome == "verified":
            reg = reg_store.update_registration(
                request.registration_id,
                status="verified",
                full_legal_name=request.full_legal_name,
                id_number=request.id_number,
                verifynow_reference=result["reference"],
            )
            logger.info("VerifyNow: identity verified for registration_id=%s", request.registration_id)
            return {
                "registration_id": request.registration_id,
                "verification_status": "verified",
                "message": "Identity verified successfully. You can now submit banking details and your schedule.",
                "attempts_remaining": reg_store.MAX_VERIFICATION_ATTEMPTS - reg.get("verification_attempts", 0),
            }

        if outcome == "error":
            # VerifyNow itself failed/timed out - not the doctor's fault, so
            # this does NOT count against their attempts. Keep the
            # registration alive so they can simply retry this step.
            logger.error(
                "VerifyNow: service error for registration_id=%s detail=%s",
                request.registration_id, result.get("detail"),
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Identity verification service is temporarily unavailable, please try again shortly",
            )

        if outcome == "review":
            # VerifyNow could not confirm a clear match/no-match - doesn't
            # count against attempts (not a clean rejection). Let the
            # doctor retry with a clearer selfie.
            logger.warning(
                "VerifyNow: registration_id=%s flagged for manual review, score=%s",
                request.registration_id, result.get("score"),
            )
            return {
                "registration_id": request.registration_id,
                "verification_status": "review",
                "message": "We couldn't get a clear match, please retry with a clearer, well-lit selfie.",
                "attempts_remaining": reg_store.MAX_VERIFICATION_ATTEMPTS - reg.get("verification_attempts", 0),
            }

        # outcome == "rejected": a genuine mismatch against Home Affairs.
        attempts = reg.get("verification_attempts", 0) + 1
        if attempts >= reg_store.MAX_VERIFICATION_ATTEMPTS:
            reg_store.delete_registration(request.registration_id)
            logger.warning(
                "VerifyNow: registration_id=%s rejected %s times, discarding registration",
                request.registration_id, attempts,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Identity could not be verified after multiple attempts. Please start registration again.",
            )

        reg_store.update_registration(request.registration_id, verification_attempts=attempts)
        return {
            "registration_id": request.registration_id,
            "verification_status": "rejected",
            "message": result.get("detail") or "Identity could not be verified, please check your details and try again.",
            "attempts_remaining": reg_store.MAX_VERIFICATION_ATTEMPTS - attempts,
        }

    # ---------------------------------------------------------------
    # Between step 2 and 3: proof-of-banking upload. Requires identity to
    # already be verified. Uploads straight to S3 (no DB write) and hands
    # back the S3 key for the doctor's client to include in `finalize`'s
    # banking payload.
    # ---------------------------------------------------------------
    @staticmethod
    def upload_proof_of_banking(registration_id: str, file) -> dict:
        reg = reg_store.get_registration(registration_id)
        if reg is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Registration not found or has expired, please start again",
            )
        if reg.get("status") != "verified":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Please complete identity verification before uploading proof of banking",
            )

        path = storage.upload_proof_of_banking(registration_id, file)
        return {"proof_of_banking_path": path}

    # ---------------------------------------------------------------
    # Step 3: banking details + schedule. Only now do we persist
    # everything to Postgres, in a single transaction, and only if
    # identity was verified in step 2.
    # ---------------------------------------------------------------
    @staticmethod
    def finalize(db: Session, request: DoctorFinalizeRequest) -> dict:
        reg = reg_store.get_registration(request.registration_id)
        if reg is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Registration not found or has expired, please start again",
            )

        if reg.get("status") != "verified":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Identity verification must be completed before finalizing registration",
            )

        if not request.availability:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Availability cannot be empty, please select at least one slot where you are available",
            )

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
            user = Users(
                username=reg["username"],
                email=reg["email"],
                hashed_password=reg["hashed_password"],
                role="doctor",
                status="onboarding",
            )
            db.add(user)
            db.flush()  # assign user.id

            profile = DoctorProfiles(
                user_id=user.id,
                full_legal_name=reg["full_legal_name"],
                id_number=reg["id_number"],
                practice_number=request.practice_number,
                speciality=DEFAULT_SPECIALITY,
                verification_status="pending_review",
                verifynow_reference=reg.get("verifynow_reference"),
                # "updated_at" was last stamped when verify_identity marked
                # this registration as verified - i.e. the moment VerifyNow
                # actually confirmed identity, not "now" at finalize time.
                verified_at=datetime.fromisoformat(reg["updated_at"]),
            )
            db.add(profile)

            banking = BankingDetails(
                doctor_id=user.id,
                bank_name=request.banking.bank_name,
                account_holder_name=request.banking.account_holder_name,
                account_number_encrypted=encrypt(request.banking.account_number),
                account_number_last4=request.banking.account_number[-4:],
                branch_code=request.banking.branch_code,
                account_type=request.banking.account_type,
                proof_of_banking_path=request.banking.proof_of_banking_path,
            )
            db.add(banking)

            created_slots = 0
            for slot in request.availability:
                db.add(DoctorAvailability(
                    doctor_id=user.id,
                    day_of_week=slot.day_of_week,
                    start_time=slot.start_time,
                    end_time=slot.end_time,
                    slot_duration_minutes=slot.slot_duration_minutes,
                    is_active=True,
                ))
                created_slots += 1

            db.commit()
            db.refresh(user)
            db.refresh(profile)
        except IntegrityError as e:
            db.rollback()
            logger.warning("Doctor finalize IntegrityError for registration_id=%s: %s", request.registration_id, e)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Username, email, or practice number is already registered. "
                    "Please start registration again."
                ),
            )
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

        reg_store.delete_registration(request.registration_id)

        EmailService.send_welcome_email(user.email, user.username)

        return {
            "message": (
                "Doctor registration submitted successfully. "
                "Your identity is verified; your profile and banking details "
                "are now pending admin review."
            ),
            "user_id": user.id,
            "verification_status": profile.verification_status,
            "availability_slots_created": created_slots,
        }
