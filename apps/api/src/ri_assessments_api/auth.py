"""Auth primitives: Supabase JWT for admins (spec §14.1) and signed
magic-link tokens for candidates (spec §13, §14.2)."""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Header, HTTPException, status
from jose import JWTError, jwt

from .config import get_settings

ALGORITHM = "HS256"
CANDIDATE_TOKEN_AUDIENCE = "ri-assessments-candidate"


def issue_candidate_token(
    assignment_id: str,
    subject_id: str,
    expires_at: datetime,
) -> str:
    settings = get_settings()
    if not settings.jwt_signing_secret:
        raise RuntimeError("JWT_SIGNING_SECRET is not configured.")
    claims = {
        "sub": subject_id,
        "assignment_id": assignment_id,
        "aud": CANDIDATE_TOKEN_AUDIENCE,
        "iat": int(datetime.now(UTC).timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(claims, settings.jwt_signing_secret, algorithm=ALGORITHM)


def decode_candidate_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(
            token,
            settings.jwt_signing_secret,
            algorithms=[ALGORITHM],
            audience=CANDIDATE_TOKEN_AUDIENCE,
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired magic-link token.",
        ) from exc


def default_token_expiry() -> datetime:
    """Spec §18: 7-day default magic-link expiry."""
    return datetime.now(UTC) + timedelta(days=7)


async def require_admin_jwt(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Verifies a Supabase-issued JWT on the Authorization header.
    Placeholder: production should fetch the JWKS from Supabase. For local
    development we accept any JWT signed with JWT_SIGNING_SECRET and trust the
    sub/role claims."""

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token.")
    token = authorization.split(" ", 1)[1]
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_signing_secret, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin token.",
        ) from exc
