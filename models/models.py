from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Numeric, Text, Time, Boolean
from sqlalchemy.orm import relationship
from core.database import Base
from pydantic import BaseModel, ConfigDict, EmailStr, Field
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
    notes = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


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
    hpcsa_number = Column(String(255), nullable=False, unique=True)
    speciality = Column(String(255), nullable=False)
    identity_document_path = Column(String(255), nullable=False)
    qualification_path = Column(String(255), nullable=False)
    verification_status = Column(String(255), nullable=False, default="pending")
    verified_at = Column(DateTime, nullable=False, default=datetime.now)

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
    consultation_id: str


class CheckoutResponse(BaseModel):
    payment_id: int
    payment_url: str


class AvailabilityRequest(BaseModel):
    day_of_week: int = Field(..., ge=0, le=6)  # 0=Monday, 6=Sunday
    start_time: time
    end_time: time
    slot_duration_minutes: int = Field(default=30, ge=15, le=120)


class DoctorOnboardingRequest(BaseModel):
    full_legal_name: str
    hpcsa_number: str
    speciality: str
    identity_document_path: str
    qualification_path: str
    availability: List[AvailabilityRequest]


class DoctorOnboardingResponse(BaseModel):
    message: str
    user_id: int
    verification_status: str
    availability_slots_created: int


class PendingDoctorResponse(BaseModel):
    id: int
    user_id: int
    full_legal_name: str
    hpcsa_number: str
    speciality: str
    identity_document_path: str
    qualification_path: str
    verification_status: str

    model_config = ConfigDict(from_attributes=True)


class ApproveDoctorRequest(BaseModel):
    verification_status: str = "active"


class ApproveDoctorResponse(BaseModel):
    id: int
    user_id: int
    full_legal_name: str
    hpcsa_number: str
    verification_status: str

    model_config = ConfigDict(from_attributes=True)


class PendingDoctorsResponse(BaseModel):
    id: int
    full_legal_name: str
    speciality: str
    hpcsa_number: str
    verification_status: str
    created_at: datetime


class CreateVisitRequest(BaseModel):
    scheduled_at: datetime


class VisitResponse(BaseModel):
    id: int
    consultation_id: int
    patient_id: int
    doctor_id: int
    scheduled_at: datetime
    status: str


class JoinVisitResponse(BaseModel):
    channel_name: str
    agora_token: str
    app_id: str
    uid: int
    video_provider: str
    join_url: str
