from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt
from passlib.context import CryptContext
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_404_NOT_FOUND

from core.database import SessionLocal
from core.dependency import db_dependency
from models.models import Users, Token

router = APIRouter(prefix="/auth", tags=["auth"])

SECRET_KEY = "YmM4NzY0ZDVjZGI3MmRmZjRhOTk5ZWMyNjliMWE5MDViMjZlMTBhYWQzYWJkMTlhYzQ5MGI3NTVhYWQ2NDY4Ng=="
ALGORITHM = "HS256"

bcrypt_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
# oauth2_bearer = OAuth2PasswordBearer(tokenUrl="auth/token")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/token", response_model=Token)
async def login_for_access_token(
        form_data: Annotated[OAuth2PasswordRequestForm, Depends()], db: db_dependency
):
    """
    Authenticates user credentials and returns JWT token if valid
    """
    user = authenticate_user(form_data.username, form_data.password, db)

    if not user:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Could not validate user"
        )
    username = user.username
    user_id = user.id
    token = create_user_token(username, user_id, user.role, timedelta(minutes=20))

    return {"access_token": token, "token_type": "bearer"}


def authenticate_user(username: str, password: str, db):
    """
    Verifies the username and password against stored hashed password
    Returns the user if the authentication is successful, otherwise returns False
    """

    user = db.query(Users).filter(Users.username == username).first()
    if not user:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="No user found")
    if not bcrypt_context.verify(password, user.hashed_password):
        return False
    return user


def create_user_token(username: str, user_id: int, role: str, expires_delta: timedelta):
    """
    Generates a JWT token with an expiration time.
    """
    encode = {"sub": username, "id": user_id, "role": role}
    expires = datetime.now() + expires_delta
    encode.update({"exp": expires})
    return jwt.encode(encode, SECRET_KEY, algorithm=ALGORITHM)