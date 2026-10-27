"""FastAPI application entrypoint for Dermatology Bridge."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import CLINICAL_DISCLAIMER
from app.api.router import router as api_router
from app.auth.middleware import JWTAuthMiddleware
from app.auth.router import router as auth_router
from app.config import get_settings, verify_startup_invariants
from app.db.session import get_db


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Validate runtime invariants at startup before accepting traffic."""
    settings = get_settings()
    verify_startup_invariants(settings)
    yield


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application instance."""
    settings = get_settings()
    verify_startup_invariants(settings)

    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        description=f"Dermatology Bridge API — {CLINICAL_DISCLAIMER}",
        lifespan=lifespan,
    )

    app.add_middleware(JWTAuthMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth_router)
    app.include_router(api_router)

    @app.get("/health", tags=["health"])
    def health_check(db: Session = Depends(get_db)) -> JSONResponse:
        """Return HTTP 200 with DB connectivity check and live-call gate status."""
        current_settings = get_settings()
        try:
            db.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "status": "degraded",
                    "database": "unreachable",
                    "detail": str(exc),
                    "allow_live_calls": current_settings.ALLOW_LIVE_CALLS,
                    "disclaimer": CLINICAL_DISCLAIMER,
                },
            )

        payload: dict[str, Any] = {
            "status": "ok",
            "database": "connected",
            "allow_live_calls": current_settings.ALLOW_LIVE_CALLS,
            "disclaimer": CLINICAL_DISCLAIMER,
        }
        return JSONResponse(status_code=status.HTTP_200_OK, content=payload)

    return app


app = create_app()
