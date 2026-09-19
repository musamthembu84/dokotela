import logging
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from core.database import SessionLocal, engine
from core.dependency import db_dependency
from core.jwt_utils import get_current_user
from core.redis_client import redis_client

from models import models

from routes.admin import router as admin
from routes.auth import router
from routes.consultation_notes import router as consultation_notes
from routes.dokotela_chat import router as consultation
from routes.doctor_onboarding import router as doctor_onboarding
from routes.doctors import router as doctors
from routes.online_visits import router as visits
from routes.payments import router as payments
from routes.scheduling import router as scheduling
from routes.users import router as users_router


logger = logging.getLogger(__name__)

logging.basicConfig(level=logging.INFO)


app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://dokotela-ai.com",
        "https://www.dokotela-ai.com",
        "http://98.95.246.110:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(
    request: Request,
    call_next,
):
    body = await request.body()

    logger.info(
        "➡️  %s %s | body=%s",
        request.method,
        request.url.path,
        body.decode("utf-8", errors="ignore"),
    )

    response = await call_next(request)

    logger.info(
        "⬅️  %s %s | status=%s",
        request.method,
        request.url.path,
        response.status_code,
    )

    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    logger.error(
        "422 on %s %s | errors=%s | body=%s",
        request.method,
        request.url.path,
        exc.errors(),
        exc.body,
    )

    return JSONResponse(
        status_code=422,
        content={
            "detail": exc.errors(),
            "body": exc.body,
        },
    )


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


user_dependency = Annotated[
    dict,
    Depends(get_current_user),
]


@app.get(
    "/health",
    status_code=status.HTTP_200_OK,
    tags=["health"],
)
async def health():
    """
    Unauthenticated health check for load balancers,
    Nginx and deployment smoke tests. all test

    Verifies that the application, database and Redis
    are reachable.
    """

    checks = {
        "app": "ok",
        "database": "unknown",
        "redis": "unknown",
    }

    healthy = True

    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))

        checks["database"] = "ok"

    except Exception as exc:
        healthy = False

        checks["database"] = f"error: {exc}"

        logger.error(
            "Health check: database unreachable | error=%s",
            exc,
        )

    try:
        redis_client.ping()

        checks["redis"] = "ok"

    except Exception as exc:
        healthy = False

        checks["redis"] = f"error: {exc}"

        logger.error(
            "Health check: redis unreachable | error=%s",
            exc,
        )

    payload = {
        "status": "ok" if healthy else "unhealthy",
        "checks": checks,
    }

    if not healthy:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=payload,
        )

    return payload


@app.get(
    "/",
    status_code=status.HTTP_200_OK,
)
async def user(
    user: user_dependency,
    db: db_dependency,
):
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication Failed",
        )

    return {
        "User": user,
    }


# uvicorn main:app --reload --port 8000
# ngrok http --domain=tranquil-promotion-research.ngrok-free.dev 8000
