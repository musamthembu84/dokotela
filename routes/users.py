from typing import List, Annotated

from fastapi import APIRouter, HTTPException, Response
from fastapi.params import Depends
from starlette.status import HTTP_201_CREATED, HTTP_204_NO_CONTENT

from core.dependency import db_dependency
from core.jwt_utils import get_current_user, authorize_user_access
from core.security import hash_password
from models.models import Users, UserRequest, UserResponse
from service.email_service import EmailService

router = APIRouter(prefix="/users", tags=["users"])


token_dep = Annotated[dict, Depends(get_current_user)]


@router.post("/", status_code=HTTP_201_CREATED)
async def create_user(db: db_dependency, create_user_request: UserRequest):
    """
    Creates a new user (patient/admin) with a hashed password and stores it
    in the database.

    Doctors do NOT use this endpoint - they go through the 3-step identity
    verification flow starting at POST /doctor/onboarding/start, since
    nothing about a doctor is persisted until VerifyNow confirms their
    identity and they submit banking details + schedule.
    """
    try:
        password = create_user_request.password
        type_of_user = create_user_request.role
        verify_user_type(type_of_user)
        # Only patient/admin ever reach here (doctors are rejected above),
        # and both start out "active" - no pending onboarding state needed.
        user_status = "active"
        # Create user model
        create_user_model = Users(
            username=create_user_request.username,
            hashed_password=hash_password(password),
            role=type_of_user,
            status=user_status,
            email=create_user_request.email
        )

        db.add(create_user_model)
        db.commit()
        db.refresh(create_user_model)

        print(f"User created: {create_user_model.username}")

        EmailService.send_welcome_email(
            create_user_model.email, create_user_model.username
        )

        return UserResponse.model_validate(create_user_model)
    except ValueError as e:
        print(f"ValueError in password hashing: {e}")
        raise HTTPException(status_code=400, detail=f"Password processing error: {str(e)}")
    except Exception as e:
        print(f"Unexpected error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create user: {str(e)}")



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
    if role == "doctor":
        raise HTTPException(
            status_code=400,
            detail="Doctors must register via POST /doctor/onboarding/start",
        )
    if role not in ("patient", "admin"):
        raise HTTPException(status_code=400,
                            detail="Role must be 'patient' or 'admin'")
    return role


def authorize_doctors_to_see_patients(user_id: int, token: dict):
    token_user_id = int(token["id"])
    role = token["role"]
    if role != "doctor" or token_user_id != user_id:
        raise HTTPException(status_code=403, detail="No permission to access patients")
