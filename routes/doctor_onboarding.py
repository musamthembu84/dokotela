from fastapi import APIRouter, Depends
from core.dependency import db_dependency
from models.models import DoctorOnboardingRequest, DoctorOnboardingResponse
import logging
from typing import Annotated
from core.jwt_utils import get_current_user, authorize_user_access
from service.doctor_onboarding_service import DoctorOnboardingService

router = APIRouter(prefix="/doctor", tags=["doctor"])
logger = logging.getLogger(__name__)

token_dep = Annotated[dict, Depends(get_current_user)]


@router.post("/onboarding", response_model=DoctorOnboardingResponse)
async def doctor_onboarding(
        request: DoctorOnboardingRequest,
        db: db_dependency,
        token: str = None):
    if not token:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Onboarding token is required")
    return DoctorOnboardingService.onboard(db=db, token=token, request=request)
