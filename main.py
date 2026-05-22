import logging
from typing import Annotated
from fastapi import Depends, FastAPI, HTTPException, status
from routes.auth import router
from core.jwt_utils import get_current_user
from routes.users import router as users_router
from routes.online_visits import router as visits
from routes.dokotela_chat import router as consultation
from routes.payments import router as payments
from routes.doctor_onboarding import router as doctor_onboarding
from routes.admin import router as admin
from core.database import SessionLocal, engine
from core.dependency import db_dependency as db_dependency

from models import models

logging.basicConfig(level=logging.INFO)

app = FastAPI()
app.include_router(router)
app.include_router(users_router)
app.include_router(visits)

app.include_router(consultation)
app.include_router(payments)
app.include_router(doctor_onboarding)
app.include_router(admin)

models.Base.metadata.create_all(bind=engine)

user_dependency = Annotated[dict, Depends(get_current_user)]


@app.get("/", status_code=status.HTTP_200_OK)
async def user(user: user_dependency, db: db_dependency):
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication Failed")
    return {"User": user}
