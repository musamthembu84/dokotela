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

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from models import models
import logging

logger = logging.getLogger(__name__)

logging.basicConfig(level=logging.INFO)

app = FastAPI()

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000","http://23.20.254.20:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.middleware("http")
async def log_requests(request: Request, call_next):
    body = await request.body()
    logger.info(f"➡️  {request.method} {request.url.path} | body={body.decode('utf-8', errors='ignore')}")
    response = await call_next(request)
    logger.info(f"⬅️  {request.method} {request.url.path} | status={response.status_code}")
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f" 422 on {request.method} {request.url.path} | errors={exc.errors()} | body={exc.body}")
    return JSONResponse(status_code=422, content={"detail": exc.errors(), "body": exc.body})

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


#uvicorn main:app --reload --port 8000
#ngrok http --domain=tranquil-promotion-research.ngrok-free.dev 8000
#phrase -> jt7NOE43FZPn