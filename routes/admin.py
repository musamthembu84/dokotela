import logging
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException
from starlette import status

from core.dependency import db_dependency
from core.jwt_utils import get_current_user
from models.models import PendingDoctorResponse, ApproveDoctorRequest, ApproveDoctorResponse, UserResponse, Users
from service.admin_service import AdminService

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)

token_dep = Annotated[dict, Depends(get_current_user)]


@router.get("/doctors/pending", response_model=List[PendingDoctorResponse])
def get_pending_doctors(db: db_dependency, token: token_dep):
    """Return all doctor profiles awaiting verification. Admin only."""
    if token.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    profiles = AdminService.get_pending_doctors(db)
    return [PendingDoctorResponse.model_validate(p) for p in profiles]


@router.post("/doctors/{doctor_profile_id}/approve", response_model=ApproveDoctorResponse)
def approve_doctor(
        doctor_profile_id: int,
        body: ApproveDoctorRequest,
        db: db_dependency,
        token: token_dep,
):
    """Approve a pending doctor — sets verification_status and user status to 'active'. Admin only."""
    if token.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    if body.verification_status != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="verification_status must be 'active'")

    profile = AdminService.approve_doctor(db, doctor_profile_id)
    return ApproveDoctorResponse.model_validate(profile)


@router.get("/users", response_model=List[UserResponse])
async def get_all_users(db: db_dependency, token: token_dep):
    """
    Fetch all users from the database
    """

    if token.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    users = db.query(Users).all()

    if not users:
        raise HTTPException(status_code=404, detail="No users found")

    return [UserResponse.model_validate(user) for user in users]
