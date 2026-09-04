from typing import Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from service.auth_service import AuthService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> dict:
    # AuthService.decode_token raises HTTPException(401) for invalid,
    # expired, or revoked (signed out) tokens.
    payload = AuthService.decode_token(token)

    username: str = payload.get("sub")
    user_id: int = payload.get("id")
    role: str = payload.get("role")

    if not username or not user_id or not role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    return {
        "username": username,
        "id": int(user_id),
        "role": role,
    }


def authorize_user_access(user_id: int, token: dict):
    token_user_id = int(token["id"])

    if token_user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No permission to access the resource",
        )
