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
from routes.doctors import router as doctors
from routes.scheduling import router as scheduling
from routes.consultation_notes import router as consultation_notes
from core.database import SessionLocal, engine
from core.dependency import db_dependency as db_dependency
from core.llm_service import load_llm
from core.redis_client import redis_client

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from models import models
from sqlalchemy import text
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
app.include_router(doctors)
app.include_router(scheduling)
app.include_router(consultation_notes)

models.Base.metadata.create_all(bind=engine)


@app.on_event("startup")
def warm_up_llm():
    # Loads the LLM once at startup so the first chat request isn't slow.
    logger.info("Warming up LLM...")
    load_llm()
    logger.info("LLM ready")

user_dependency = Annotated[dict, Depends(get_current_user)]


@app.get("/health", status_code=status.HTTP_200_OK, tags=["health"])
async def health():
    """
    Unauthenticated health check for load balancers, Nginx and deployment
    smoke tests. Verifies the process is up and its critical dependencies
    (database, Redis) are reachable, so connectivity problems are caught
    immediately instead of being discovered manually after the fact.
    """
    # Reaching this line at all proves the app process is running and
    # serving requests - "app" is set unconditionally, before any
    # dependency is checked, so it can't be masked by a DB/Redis outage.
    checks = {"app": "ok", "database": "unknown", "redis": "unknown"}
    healthy = True

    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        healthy = False
        checks["database"] = f"error: {exc}"
        logger.error(f"Health check: database unreachable | error={exc}")

    try:
        redis_client.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        healthy = False
        checks["redis"] = f"error: {exc}"
        logger.error(f"Health check: redis unreachable | error={exc}")

    payload = {"status": "ok" if healthy else "unhealthy", "checks": checks}

    if not healthy:
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=payload)

    return payload


@app.get("/", status_code=status.HTTP_200_OK)
async def user(user: user_dependency, db: db_dependency):
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication Failed")
    return {"User": user}


#uvicorn main:app --reload --port 8000
#ngrok http --domain=tranquil-promotion-research.ngrok-free.dev 8000
#phrase -> jt7NOE43FZPn