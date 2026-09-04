from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from fastapi.security import OAuth2PasswordRequestForm
from starlette.status import HTTP_204_NO_CONTENT

from core.dependency import db_dependency
from core.jwt_utils import oauth2_scheme
from models.models import Token
from service.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token", response_model=Token)
async def login_for_access_token(
        form_data: Annotated[OAuth2PasswordRequestForm, Depends()], db: db_dependency
):
    """
    Authenticates user credentials and returns JWT token if valid
    """
    user = AuthService.authenticate_user(form_data.username, form_data.password, db)

    token = AuthService.create_access_token(
        user.username, user.id, user.role, user.email, timedelta(minutes=20)
    )

    return {"access_token": token, "token_type": "bearer"}


@router.post("/signout", status_code=HTTP_204_NO_CONTENT)
async def signout(token: Annotated[str, Depends(oauth2_scheme)]):
    """
    Signs the caller out by revoking (blacklisting) their current access
    token so it can no longer be used, even before it naturally expires.
    """
    AuthService.revoke_token(token)
    return Response(status_code=HTTP_204_NO_CONTENT)
