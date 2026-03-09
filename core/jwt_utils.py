from typing import Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError

SECRET_KEY = "YmM4NzY0ZDVjZGI3MmRmZjRhOTk5ZWMyNjliMWE5MDViMjZlMTBhYWQzYWJkMTlhYzQ5MGI3NTVhYWQ2NDY4Ng=="
ALGORITHM = "HS256"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> dict:

    print("RAW TOKEN:", token)
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        print("PAYLOAD", payload)

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

    except JWTError as e:
        print("JWT Error", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )


def authorize_user_access(user_id: int, token: dict):
    token_user_id = int(token["id"])

    if token_user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No permission to access the resource",
        )
