import secrets
from datetime import datetime, timedelta
from typing import List, Annotated

import bcrypt
from fastapi import APIRouter, HTTPException, Response
from fastapi.params import Depends
from starlette.status import HTTP_201_CREATED, HTTP_204_NO_CONTENT

from core.dependency import db_dependency
from core.jwt_utils import get_current_user, authorize_user_access
from models.models import Users, UserRequest, UserResponse, OnboardingTokens

router = APIRouter(prefix="/users", tags=["users"])


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


token_dep = Annotated[dict, Depends(get_current_user)]


@router.post("/", status_code=HTTP_201_CREATED)
async def create_user(db: db_dependency, create_user_request: UserRequest):
    """
    Creates a new user with a hashed password and stores it in the database
    """
    try:
        password = create_user_request.password
        type_of_user = create_user_request.role
        verify_user_type(type_of_user)
        user_status = await get_type_of_user(type_of_user)
        # Create user model
        create_user_model = Users(
            username=create_user_request.username,
            hashed_password=hash_password(password),
            role=type_of_user,
            status=user_status,
            email=create_user_request.email
        )

        db.add(create_user_model)
        db.flush()  # Flush to assign an ID before commit

        tokens = None
        if type_of_user == "doctor":
            doctor_token = secrets.token_urlsafe(32)

            tokens = OnboardingTokens(
                doctor_id=create_user_model.id,
                token=doctor_token,
                expires_at=datetime.now() + timedelta(days=14),
                used=False
            )
            db.add(tokens)
            print(f"Onboarding token: {tokens.token}")

        db.commit()
        db.refresh(create_user_model)
        if tokens is not None:
            db.refresh(tokens)

        print(f"User created: {create_user_model.username}")

        return UserResponse.model_validate(create_user_model)
    except ValueError as e:
        print(f"ValueError in password hashing: {e}")
        raise HTTPException(status_code=400, detail=f"Password processing error: {str(e)}")
    except Exception as e:
        print(f"Unexpected error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create user: {str(e)}")


async def get_type_of_user(type_of_user: str) -> str:
    user_status = ""
    if type_of_user == "doctor":
        user_status = "pending"
    elif type_of_user == "patient" or type_of_user == "admin":
        user_status = "active"
    return user_status



@router.get("/{doctor_id}/patients", response_model=List[UserResponse])
async def get_patients(doctor_id: int, db: db_dependency, token: token_dep):
    """
    Only fetch patients that will be used by doctors
    """
    doctor = db.query(Users).filter(Users.id == doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="No user found")

    authorize_doctors_to_see_patients(doctor_id, token)

    patients = db.query(Users).filter(Users.role == "patient").all()

    if not patients:
        raise HTTPException(status_code=404, detail="No patients present")

    return [UserResponse.model_validate(patient) for patient in patients]


@router.get("/{user_id}", response_model=UserResponse)
async def get_user_by_id(user_id: int, db: db_dependency, token: token_dep):
    """
    Get user by their id

    """
    authorize_user_access(user_id, token)

    user = db.query(Users).filter(Users.id == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="No user found")

    return UserResponse.model_validate(user)


@router.delete("/{id}", status_code=HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, db: db_dependency):
    """
    Delete a specific user from database
    """

    user = db.query(Users).filter(Users.id == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="No users found")

    db.delete(user)
    db.commit()

    return Response(status_code=HTTP_204_NO_CONTENT)


def verify_user_type(role: str):
    if role not in ("doctor", "patient", "admin"):
        raise HTTPException(status_code=400,
                            detail=" Role must be 'doctor' or 'patient'")
    return role


def authorize_doctors_to_see_patients(user_id: int, token: dict):
    token_user_id = int(token["id"])
    role = token["role"]
    if role != "doctor" or token_user_id != user_id:
        raise HTTPException(status_code=403, detail="No permission to access patients")
