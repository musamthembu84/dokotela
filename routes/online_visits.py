from typing import Annotated

from fastapi import APIRouter, Depends, status

from core.dependency import db_dependency
from core.jwt_utils import get_current_user
from service.visit_service import VisitService
from models.models import CreateVisitRequest, JoinVisitResponse

token_dep = Annotated[dict, Depends(get_current_user)]

router = APIRouter(prefix="/visits", tags=["Visits"])


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_visit(
        request: CreateVisitRequest,
        db: db_dependency,
        token: token_dep,
):
    return VisitService.create_visit(
        db=db,
        patient_id=token["id"],
        request=request,
    )


@router.get("/", status_code=status.HTTP_200_OK)
async def get_my_visits(
        db: db_dependency,
        token: token_dep,
):
    return VisitService.get_my_visits(db=db, user_id=token["id"])


@router.post("/{visit_id}/join", status_code=status.HTTP_200_OK, response_model=JoinVisitResponse)
async def join_visit(
        visit_id: int,
        db: db_dependency,
        token: token_dep,
):
    response = VisitService.join_visit(db=db, user_id=token["id"], visit_id=visit_id)
    response["join_url"] = f"http://localhost:3000/call/{visit_id}"
    return response