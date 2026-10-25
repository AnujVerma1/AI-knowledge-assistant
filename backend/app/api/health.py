import logging
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import get_engine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    environment: str


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    database: Literal["ok", "unavailable"]
    schema_version: str | None


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness check for the hosting platform.

    Deliberately touches no database or model: a slow or sleeping dependency must not make the
    platform restart a healthy process, and frequent pings must not keep a paid database awake.
    """
    return HealthResponse(status="ok", environment=get_settings().app_env)


@router.get("/health/ready", response_model=ReadinessResponse, responses={503: {"model": ReadinessResponse}})
def readiness():
    """Checks the database connection and reports the applied migration version."""
    try:
        with get_engine().connect() as connection:
            version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    except Exception as exc:
        logger.warning("Readiness check failed: %s", type(exc).__name__)
        body = ReadinessResponse(status="not_ready", database="unavailable", schema_version=None)
        return JSONResponse(status_code=503, content=body.model_dump())
    return ReadinessResponse(status="ready", database="ok", schema_version=version)
