from tokenize import Double

from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Numeric, Float
from sqlalchemy.orm import relationship
from core.database import Base
from pydantic import BaseModel, ConfigDict
from datetime import datetime


# -------------------------
# SQLAlchemy Models
# -------------------------
class Users(Base):
    __tablename__ = "users"  # PostgreSQL table name should be lowercase
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=False)


class Payments(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String, default="ZAR", nullable=False)
    provider = Column(String, nullable=False)
    reference = Column(String, nullable=False)
    status = Column(String, default="paid", nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now())


class Consultations(Base):
    __tablename__ = "consultations"
    id = Column(Integer, primary_key=True, index=True)
    payment_id = Column(Integer, ForeignKey("payments.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    chief_complaint = Column(String, nullable=False)
    risk_level = Column(String, nullable=False)
    recommended_speciality = Column(String, nullable=False)
    summary = Column(String, nullable=False)
    status = Column(String, default="paid", nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now())


class Visit(Base):
    __tablename__ = "visits"
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    doctor_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    consultation_id = Column(Integer, ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False)
    scheduled_for = Column(DateTime, nullable=False)
    status = Column(String, default="scheduled", nullable=False)  # scheduled, completed, canceled
    call_provider = Column(String, nullable=True)
    call_channel = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now())

    # Relationships to Users
    patient = relationship("Users", foreign_keys=[patient_id])
    doctor = relationship("Users", foreign_keys=[doctor_id])


# -------------------------
# Pydantic Models
# -------------------------
class UserRequest(BaseModel):
    username: str
    password: str
    role: str


class UserResponse(BaseModel):
    id: int
    username: str
    role: str

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str


class VisitCreate(BaseModel):
    patient_id: int
    doctor_id: int
    scheduled_for: datetime


class VisitResponse(BaseModel):
    id: int
    patient_id: int
    doctor_id: int
    scheduled_for: datetime
    status: str

    class Config:
        orm_mode = True


class VisitStatusUpdate(BaseModel):
    status: str


class PaymentRequest(BaseModel):
    session_id: str
    amount: float
    provider: str = "mock",
    reference: str


class PaymentResponse(BaseModel):
    payment_id: int
    consultation_id: int
    status: str
