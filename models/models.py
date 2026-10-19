from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Numeric, Text, Time, Boolean
from sqlalchemy.orm import relationship
from core.database import Base
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from datetime import datetime, time
from decimal import Decimal
from typing import List


# -------------------------
# SQLAlchemy Models
# -------------------------
class Users(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "health"}

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    email = Column(String, nullable=False, unique=True)
    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    status = Column(String, nullable=False, default="pending")


class Payments(Base):
    __tablename__ = "payments"
    __table_args__ = {"schema": "health"}

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("health.users.id", ondelete="CASCADE"), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String, default="ZAR", nullable=False)
    status = Column(String, default="pending", nullable=False)
    provider = Column(String, nullable=False, default="payfast")
    payment_reference = Column(String(255), unique=True, nullable=True)
    consultation_session_id = Column(String(255), nullable=True, unique=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now)


class Consultations(Base):
    __tablename__ = "consultations"
    __table_args__ = {"schema": "health"}

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("health.users.id", ondelete="CASCADE"), nullable=False)
    payment_id = Column(Integer, ForeignKey("health.payments.id", ondelete="RESTRICT"), nullable=False)
    status = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class ConsultationNotes(Base):
    __tablename__ = "consultation_notes"
    __table_args__ = {"schema": "health"}

    id = Column(Integer, primary_key=True, index=True)
    consultation_id = Column(Integer, ForeignKey("health.consultations.id", ondelete="CASCADE"), nullable=False)
    author = Column(String(50), nullable=False)  # ai, doctor
    type = Column(String(100), nullable=False)  # SOAP_AI, SOAP_DOCTOR, diagnosis, etc.
    ai_note = Column(Text, nullable=True)
    doctor_note = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)


class Visit(Base):
    __tablename__ = "visits"
    __table_args__ = {"schema": "health"}

    id = Column(Integer, primary_key=True, index=True)
    consultation_id = Column(Integer, ForeignKey("health.consultations.id", ondelete="CASCADE"), nullable=False)
    patient_id = Column(Integer, ForeignKey("health.users.id", ondelete="CASCADE"), nullable=False)
    doctor_id = Column(Integer, ForeignKey("health.users.id", ondelete="CASCADE"), nullable=False)
    scheduled_at = Column(DateTime, nullable=False)
    status = Column(String, nullable=False, default="scheduled")
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    channel_name = Column(String(255), unique=True)
    video_provider = Column(String(50), default="agora")
    video_status = Column(String(50), default="waiting")
    patient = relationship("Users", foreign_keys=[patient_id])
    doctor = relationship("Users", foreign_keys=[doctor_id])


class DoctorProfiles(Base):
    __tablename__ = "doctor_profiles"
    __table_args__ = {"schema": "health"}
    ##ID references users(id) on delete cascade
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("health.users.id", ondelete="CASCADE"), nullable=False)
    full_legal_name = Column(String(255), nullable=False)
    # SA ID number used to verify identity with VerifyNow/Home Affairs.
    id_number = Column(String(20), nullable=False, unique=True)
    practice_number = Column(String(255), nullable=False, unique=True)
    speciality = Column(String(255), nullable=False)
    verification_status = Column(String(255), nullable=False, default="pending")
    # Reference id returned by VerifyNow for this identity check (audit trail).
    verifynow_reference = Column(String(255), nullable=True)
    # Only set once VerifyNow confirms the doctor's identity - not at row creation.
    verified_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.now)


class BankingDetails(Base):
    """
    Bank account the doctor is paid out to, submitted in one shot at the
    end of onboarding (finalize) alongside the proof-of-banking document.
    Admin approval is a single action (see AdminService.approve_doctor) -
    there's no separate banking review step. Account number is encrypted
    at rest (see core/crypto.py); only a last-4 mask is ever returned by
    the API.
    """
    __tablename__ = "doctor_banking_details"
    __table_args__ = {"schema": "health"}
    id = Column(Integer, primary_key=True, index=True)
    doctor_id = Column(Integer, ForeignKey("health.users.id", ondelete="CASCADE"), nullable=False, unique=True)
    bank_name = Column(String(255), nullable=False)
    account_holder_name = Column(String(255), nullable=False)
    account_number_encrypted = Column(Text, nullable=False)
    account_number_last4 = Column(String(4), nullable=False)
    branch_code = Column(String(20), nullable=False)
    account_type = Column(String(50), nullable=False)
    # Path/key of the uploaded proof of banking (bank-issued confirmation
    # letter/statement), uploaded client-side.
    proof_of_banking_path = Column(String(255), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class DoctorAvailability(Base):
    __tablename__ = "doctor_availability"
    __table_args__ = {"schema": "health"}
    id = Column(Integer, primary_key=True, index=True)
    doctor_id = Column(Integer, ForeignKey("health.users.id", ondelete="CASCADE"), nullable=False)
    day_of_week = Column(Integer, nullable=False)  # 0=Monday, 6=Sunday
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    slot_duration_minutes = Column(Integer, nullable=False, default=30)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


# DEPRECATED: doctor registration is now a 3-step flow held entirely in
# Redis (see core/doctor_registration_store.py) until it is verified and
# finalized, so a DB-linked onboarding token is no longer needed to gate
# onboarding. Model kept only so any pre-existing rows/table aren't
# orphaned by the ORM; safe to drop once confirmed unused in production.
class OnboardingTokens(Base):
    __tablename__ = "doctor_onboarding_tokens"
    __table_args__ = {"schema": "health"}
    id = Column(Integer, primary_key=True, index=True)
    doctor_id = Column(Integer, ForeignKey("health.users.id", ondelete="CASCADE"))
    token = Column(String(255), nullable=False, unique=True)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


# -------------------------
# Pydantic Models
# -------------------------
class UserRequest(BaseModel):
    username: str
    password: str
    role: str
    email: str


class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    email: str

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str
    refresh_token: str


class RefreshRequest(BaseModel):
    refresh_token: str


class VisitCreate(BaseModel):
    patient_id: int
    doctor_id: int
    scheduled_at: datetime


class VisitResponse(BaseModel):
    id: int
    patient_id: int
    doctor_id: int
    scheduled_at: datetime
    status: str

    model_config = ConfigDict(from_attributes=True)


class VisitStatusUpdate(BaseModel):
    status: str


class PaymentRequest(BaseModel):
    session_id: str
    amount: float
    provider: str = "mock"
    reference: str


class PaymentResponse(BaseModel):
    payment_id: int
    consultation_id: int
    status: str


class CheckoutRequest(BaseModel):
    amount: Decimal
    consultation_id: str | None = None


class CheckoutResponse(BaseModel):
    payment_id: int
    payment_url: str


class AvailabilityRequest(BaseModel):
    day_of_week: int = Field(..., ge=0, le=6)  # 0=Monday, 6=Sunday
    start_time: time
    end_time: time
    slot_duration_minutes: int = Field(default=30, ge=15, le=120)


# -------------------------
# Doctor registration (3-step: start -> verify-identity -> finalize)
# -------------------------
class DoctorRegistrationStartRequest(BaseModel):
    username: str
    email: EmailStr
    password: str


class DoctorRegistrationStartResponse(BaseModel):
    registration_id: str
    message: str
    expires_in_minutes: int


def _is_valid_sa_id_number(id_number: str) -> bool:
    """Luhn checksum used by SA ID numbers (13 digits, last digit is the check digit)."""
    if not id_number.isdigit() or len(id_number) != 13:
        return False
    total = 0
    for i, ch in enumerate(reversed(id_number)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


class DoctorIdentityVerificationRequest(BaseModel):
    registration_id: str
    # Full legal name exactly as it appears on the Home Affairs record.
    # Not sent to VerifyNow (their Face Match bundle only needs the ID
    # number + selfie); stored for the doctor's profile once verified.
    full_legal_name: str
    id_number: str
    # Base64-encoded live selfie captured client-side (JPG/PNG/WEBP/TIFF,
    # max 5MB decoded), sent to VerifyNow's Face Match (Home Affairs)
    # bundle to compare against the official Home Affairs ID photo.
    selfie_image_base64: str

    @field_validator("id_number")
    @classmethod
    def validate_id_number(cls, value: str) -> str:
        value = value.strip()
        if not _is_valid_sa_id_number(value):
            raise ValueError("id_number must be a valid 13-digit South African ID number")
        return value

    @field_validator("selfie_image_base64")
    @classmethod
    def validate_selfie(cls, value: str) -> str:
        import base64

        value = value.strip()
        if not value:
            raise ValueError("selfie_image_base64 is required")
        # Browser webcam capture (canvas.toDataURL()) produces a data URI
        # like "data:image/jpeg;base64,/9j/...". Strip the prefix so we
        # always store/send VerifyNow raw base64.
        if value.startswith("data:") and ";base64," in value:
            value = value.split(";base64,", 1)[1]
        try:
            decoded = base64.b64decode(value, validate=True)
        except Exception as exc:
            raise ValueError("selfie_image_base64 must be valid base64") from exc
        if len(decoded) > 5 * 1024 * 1024:
            raise ValueError("selfie image must be 5MB or smaller once decoded")
        return value


class DoctorIdentityVerificationResponse(BaseModel):
    registration_id: str
    verification_status: str  # "verified" | "rejected" | "error"
    message: str
    attempts_remaining: int


# Bank account details submitted at finalize, alongside the proof of
# banking document. One step, no separate post-approval verification -
# admin approval (AdminService.approve_doctor) covers everything at once.
ACCOUNT_TYPES = {"savings", "cheque", "current", "transmission"}


class BankingDetailsRequest(BaseModel):
    bank_name: str
    account_holder_name: str
    account_number: str = Field(..., min_length=6, max_length=11)
    branch_code: str = Field(..., min_length=6, max_length=6)
    account_type: str
    # Path/key of the uploaded proof of banking document (bank-issued
    # confirmation letter/statement).
    proof_of_banking_path: str

    @field_validator("account_number")
    @classmethod
    def account_number_must_be_digits(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("account_number must contain digits only")
        return v

    @field_validator("branch_code")
    @classmethod
    def branch_code_must_be_digits(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("branch_code must be a 6-digit universal branch code")
        return v

    @field_validator("account_type")
    @classmethod
    def account_type_must_be_known(cls, v: str) -> str:
        normalized = v.strip().lower()
        if normalized not in ACCOUNT_TYPES:
            raise ValueError(f"account_type must be one of {sorted(ACCOUNT_TYPES)}")
        return normalized


class BankingDetailsResponse(BaseModel):
    bank_name: str
    account_holder_name: str
    account_number_masked: str
    branch_code: str
    account_type: str
    proof_of_banking_path: str

    model_config = ConfigDict(from_attributes=True)


class ProofOfBankingUploadResponse(BaseModel):
    proof_of_banking_path: str


class DoctorFinalizeRequest(BaseModel):
    registration_id: str
    practice_number: str
    banking: BankingDetailsRequest
    availability: List[AvailabilityRequest]


class DoctorFinalizeResponse(BaseModel):
    message: str
    user_id: int
    verification_status: str
    availability_slots_created: int


class PendingDoctorResponse(BaseModel):
    id: int
    user_id: int
    full_legal_name: str
    id_number: str
    practice_number: str
    speciality: str
    verification_status: str
    verifynow_reference: str | None = None
    banking: BankingDetailsResponse | None = None

    model_config = ConfigDict(from_attributes=True)


class ApproveDoctorRequest(BaseModel):
    verification_status: str = "active"


class ApproveDoctorResponse(BaseModel):
    id: int
    user_id: int
    full_legal_name: str
    practice_number: str
    verification_status: str

    model_config = ConfigDict(from_attributes=True)


class PendingDoctorsResponse(BaseModel):
    id: int
    full_legal_name: str
    speciality: str
    practice_number: str
    verification_status: str
    created_at: datetime


class CreateVisitRequest(BaseModel):
    scheduled_at: datetime


class VisitResponse(BaseModel):
    id: int
    consultation_id: int
    patient_id: int
    doctor_id: int
    doctor_name: str | None = None
    scheduled_at: datetime
    status: str
    created_at: datetime | None = None
    video_provider: str | None = None
    channel_name: str | None = None
    video_status: str | None = None

    model_config = ConfigDict(from_attributes=True)


class JoinVisitResponse(BaseModel):
    channel_name: str
    agora_token: str
    app_id: str
    uid: int
    video_provider: str
    join_url: str


# -------------------------
# Doctor Appointments API Models
# -------------------------
class PatientInfoResponse(BaseModel):
    id: int
    username: str
    email: str

    model_config = ConfigDict(from_attributes=True)


class DoctorAppointmentResponse(BaseModel):
    id: int
    consultation_id: int
    patient_id: int
    patient: PatientInfoResponse
    scheduled_at: datetime
    status: str
    channel_name: str | None = None
    video_provider: str | None = None
    video_status: str | None = None

    model_config = ConfigDict(from_attributes=True)


class DoctorAppointmentsListResponse(BaseModel):
    appointments: List[DoctorAppointmentResponse]
    total: int


# -------------------------
# Scheduling API Models
# -------------------------
class ScheduleAppointmentRequest(BaseModel):
    limit: int = Field(default=5, ge=1, le=20)


class AvailableAppointmentSlot(BaseModel):
    doctor_id: int
    doctor_name: str
    open_at: datetime


class SchedulePreviewResponse(BaseModel):
    slots: List[AvailableAppointmentSlot]


class ScheduleConfirmRequest(BaseModel):
    consultation_id: int | None = None
    doctor_id: int
    open_at: datetime


class ScheduleAppointmentResponse(BaseModel):
    visit_id: int
    consultation_id: int
    doctor_id: int
    doctor_name: str
    scheduled_at: datetime
    status: str


# -------------------------
# Consultation Notes API Models
# -------------------------
class ConsultationNoteResponse(BaseModel):
    id: int
    consultation_id: int
    author: str
    type: str
    ai_note: str | None = None
    doctor_note: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConsultationNotesListResponse(BaseModel):
    notes: List[ConsultationNoteResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


class DoctorNoteCreateRequest(BaseModel):
    type: str | None = Field(default=None, max_length=100)
    doctor_note: str = Field(..., min_length=1)
