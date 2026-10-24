"""JWT authentication middleware protecting /api/* routes."""

from collections.abc import Awaitable, Callable
import uuid

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, Response
import jwt
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

from app.auth.jwt import decode_access_token
from app.db.models import Clinician
from app.db.session import get_db


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """Enforce valid Bearer JWT on all /api/* routes while leaving /health and /auth/* public."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        path = request.url.path

        if request.method == "OPTIONS":
            return await call_next(request)

        # Public routes: /health, /auth/*, and OpenAPI docs
        if path == "/health" or path.startswith("/auth"):
            return await call_next(request)

        if path.startswith("/api"):
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Missing or malformed Authorization Bearer token."},
                    headers={"WWW-Authenticate": "Bearer"},
                )

            raw_token = auth_header.removeprefix("Bearer ").strip()
            if not raw_token:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Empty Bearer token."},
                    headers={"WWW-Authenticate": "Bearer"},
                )

            try:
                claims = decode_access_token(raw_token)
            except jwt.ExpiredSignatureError:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Token has expired."},
                    headers={"WWW-Authenticate": "Bearer"},
                )
            except jwt.InvalidTokenError:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Invalid authentication token."},
                    headers={"WWW-Authenticate": "Bearer"},
                )

            request.state.auth_claims = claims

        return await call_next(request)


def get_current_clinician(
    request: Request,
    db: Session = Depends(get_db),
) -> Clinician:
    """Resolve the authenticated Clinician model from request JWT claims."""
    claims = getattr(request.state, "auth_claims", None)
    if not claims or "sub" not in claims:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
        )

    try:
        clinician_id = uuid.UUID(str(claims["sub"]))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid clinician identifier in token.",
        ) from exc

    clinician = db.get(Clinician, clinician_id)
    if clinician is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Clinician account not found.",
        )
    return clinician

