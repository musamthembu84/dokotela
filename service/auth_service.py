"""
AuthService centralises all authentication business logic:
- verifying credentials
- issuing JWT access tokens
- decoding/validating JWT access tokens
- revoking ("signing out") a token before its natural expiry

Routes (routes/auth.py) stay thin controllers that only translate
HTTP <-> service calls.
"""
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import HTTPException
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_404_NOT_FOUND

from core.config import settings
from core.token_revocation import is_token_revoked, revoke_token
from core.refresh_token_store import (
    issue_refresh_token,
    rotate_refresh_token,
    revoke_refresh_token,
)
from models.models import Users

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES


class AuthService:

    @staticmethod
    def authenticate_user(username: str, password: str, db: Session) -> Users:
        """
        Verifies the username and password against stored hashed password.
        Raises HTTPException if the user cannot be authenticated.
        """
        user = db.query(Users).filter(Users.username == username).first()
        if not user:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="No user found")
        if not bcrypt.checkpw(password.encode("utf-8"), user.hashed_password.encode("utf-8")):
            raise HTTPException(
                status_code=HTTP_401_UNAUTHORIZED,
                detail="Could not validate user",
            )
        if user.status != "active":
            raise HTTPException(
                status_code=400,
                detail="Inactive account please check email to activate account",
            )
        return user

    @staticmethod
    def create_access_token(
        username: str,
        user_id: int,
        role: str,
        email: str,
        expires_delta: timedelta | None = None,
    ) -> str:
        """
        Generates a JWT token with an expiration time and a unique `jti`
        claim (needed so a single token can be individually revoked).
        """
        expires_delta = expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        expires_at = datetime.now(timezone.utc) + expires_delta
        claims = {
            "sub": username,
            "id": user_id,
            "role": role,
            "email": email,
            "jti": str(uuid.uuid4()),
            "exp": expires_at,
        }
        return jwt.encode(claims, SECRET_KEY, algorithm=ALGORITHM)

    @staticmethod
    def decode_token(token: str) -> dict:
        """
        Decodes and validates a JWT, raising HTTPException(401) if the
        token is malformed/expired or has been revoked (signed out).
        """
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        except JWTError:
            raise HTTPException(
                status_code=HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
            )

        if is_token_revoked(payload.get("jti")):
            raise HTTPException(
                status_code=HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
            )

        return payload

    @staticmethod
    def revoke_token(token: str) -> None:
        """
        Signs a token out immediately by blacklisting its `jti` until the
        token's original expiry time.
        """
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        except JWTError:
            # Already invalid/expired - nothing to revoke.
            return

        jti = payload.get("jti")
        exp = payload.get("exp")
        if not jti or not exp:
            return

        revoke_token(jti, datetime.fromtimestamp(exp, tz=timezone.utc))

    # ------------------------------------------------------------------
    # Refresh tokens - implement the "session stays alive while active,
    # idle timeout after REFRESH_TOKEN_EXPIRE_MINUTES" behaviour.
    # ------------------------------------------------------------------
    @staticmethod
    def create_refresh_token(user_id: int) -> str:
        return issue_refresh_token(user_id)

    @staticmethod
    def refresh_access_token(refresh_token: str, db: Session) -> tuple[str, str]:
        """
        Validates + rotates the refresh token, then mints a brand-new short
        -lived access token for the associated user.

        Returns (new_access_token, new_refresh_token).
        Raises HTTPException(401) if the refresh token is invalid, expired,
        or the user no longer exists/is inactive.
        """
        rotated = rotate_refresh_token(refresh_token)
        if not rotated:
            raise HTTPException(
                status_code=HTTP_401_UNAUTHORIZED,
                detail="Session expired, please sign in again",
            )

        new_refresh_token, user_id = rotated

        user = db.query(Users).filter(Users.id == user_id).first()
        if not user or user.status != "active":
            revoke_refresh_token(new_refresh_token)
            raise HTTPException(
                status_code=HTTP_401_UNAUTHORIZED,
                detail="Session expired, please sign in again",
            )

        new_access_token = AuthService.create_access_token(
            user.username, user.id, user.role, user.email
        )
        return new_access_token, new_refresh_token

    @staticmethod
    def revoke_refresh_token(refresh_token: str) -> None:
        revoke_refresh_token(refresh_token)
