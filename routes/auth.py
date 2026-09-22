from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from fastapi.security import OAuth2PasswordRequestForm
from starlette.status import HTTP_204_NO_CONTENT

from core.dependency import db_dependency
from core.jwt_utils import oauth2_scheme
from models.models import Token, RefreshRequest
from service.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token", response_model=Token)
async def login_for_access_token(
        form_data: Annotated[OAuth2PasswordRequestForm, Depends()], db: db_dependency
):
    """
    Authenticates user credentials and returns a short-lived JWT access
    token plus a refresh token. The refresh token's idle-timeout TTL slides
    forward on every use via /auth/refresh, so an active session never
    expires - only a genuinely idle one does.
    """
    user = AuthService.authenticate_user(form_data.username, form_data.password, db)

    token = AuthService.create_access_token(
        user.username, user.id, user.role, user.email
    )
    refresh_token = AuthService.create_refresh_token(user.id)

    return {"access_token": token, "token_type": "bearer", "refresh_token": refresh_token}


@router.post("/refresh", response_model=Token)
async def refresh_access_token(request: RefreshRequest, db: db_dependency):
    """
    Exchanges a valid (non-idle-expired) refresh token for a new access
    token + rotated refresh token, keeping an active session alive without
    requiring the user to log in again.
    """
    new_access_token, new_refresh_token = AuthService.refresh_access_token(
        request.refresh_token, db
    )
    return {
        "access_token": new_access_token,
        "token_type": "bearer",
        "refresh_token": new_refresh_token,
    }


@router.post("/signout", status_code=HTTP_204_NO_CONTENT)
async def signout(token: Annotated[str, Depends(oauth2_scheme)], request: RefreshRequest | None = None):
    """
    Signs the caller out by revoking (blacklisting) their current access
    token so it can no longer be used, even before it naturally expires,
    and invalidating their refresh token so the session can't be silently
    renewed either.
    """
    AuthService.revoke_token(token)
    if request is not None:
        AuthService.revoke_refresh_token(request.refresh_token)
    return Response(status_code=HTTP_204_NO_CONTENT)
