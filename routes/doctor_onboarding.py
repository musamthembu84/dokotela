import logging

from fastapi import APIRouter, File, Form, UploadFile

from core.dependency import db_dependency
from models.models import (
    DoctorRegistrationStartRequest,
    DoctorRegistrationStartResponse,
    DoctorIdentityVerificationRequest,
    DoctorIdentityVerificationResponse,
    ProofOfBankingUploadResponse,
    DoctorFinalizeRequest,
    DoctorFinalizeResponse,
)
from service.doctor_onboarding_service import DoctorOnboardingService

router = APIRouter(prefix="/doctor/onboarding", tags=["doctor"])
logger = logging.getLogger(__name__)


@router.post("/start", response_model=DoctorRegistrationStartResponse)
async def start_doctor_registration(request: DoctorRegistrationStartRequest, db: db_dependency):
    """
    Step 1: username/email/password. Held only in Redis - nothing is
    written to the database until the doctor is verified and finalizes
    registration.
    """
    return DoctorOnboardingService.start(db=db, request=request)


@router.post("/verify-identity", response_model=DoctorIdentityVerificationResponse)
async def verify_doctor_identity(request: DoctorIdentityVerificationRequest):
    """
    Step 2: facial/ID verification via VerifyNow (Home Affairs-backed).
    Still no database writes - only the Redis registration is updated.
    """
    return DoctorOnboardingService.verify_identity(request=request)


@router.post("/upload-proof-of-banking", response_model=ProofOfBankingUploadResponse)
async def upload_proof_of_banking(
    registration_id: str = Form(...),
    file: UploadFile = File(...),
):
    """
    Uploads the doctor's proof-of-banking document (PDF/PNG/JPEG) to S3.
    Requires identity to already be verified (step 2 complete). Returns the
    S3 key - pass it back as `banking.proof_of_banking_path` in `finalize`.
    """
    return DoctorOnboardingService.upload_proof_of_banking(registration_id=registration_id, file=file)


@router.post("/finalize", response_model=DoctorFinalizeResponse)
async def finalize_doctor_registration(request: DoctorFinalizeRequest, db: db_dependency):
    """
    Step 3: banking details + availability schedule. Requires identity to
    already be verified. This is the only step that persists anything to
    the database, in a single transaction.
    """
    return DoctorOnboardingService.finalize(db=db, request=request)

