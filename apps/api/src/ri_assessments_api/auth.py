"""Auth primitives: Supabase JWT for admins (spec §14.1) and signed
magic-link tokens for candidates (spec §13, §14.2)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import Depends, Header, HTTPException, status
from jose import JWTError, jwt

from .config import get_settings
from .db import get_supabase

ALGORITHM = "HS256"
CANDIDATE_TOKEN_AUDIENCE = "ri-assessments-candidate"
SUPABASE_TOKEN_AUDIENCE = "authenticated"


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


@dataclass(slots=True, frozen=True)
class AdminPrincipal:
    """Authenticated internal user (rows in public.users)."""

    user_id: str
    email: str
    full_name: str | None
    role: Literal["admin", "reviewer", "viewer"]


def _decode_supabase_jwt(token: str) -> dict[str, Any]:
    """Verify a Supabase access token and return its claims.

    Supports both legacy HS256 (shared SUPABASE_JWT_SECRET) and the
    ES256 / asymmetric keys that newer Supabase projects issue. For
    asymmetric tokens we delegate to Supabase's auth.get_user() so the
    JWKS rotation is handled by the SDK rather than reinvented here."""

    settings = get_settings()

    # Inspect the header to pick a verification path. Falls back to
    # auth.get_user() for any algorithm we don't natively understand.
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired admin token.",
        ) from exc

    alg = header.get("alg")

    if alg == ALGORITHM:
        if not settings.supabase_jwt_secret:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Server is missing SUPABASE_JWT_SECRET.",
            )
        try:
            return jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=[ALGORITHM],
                audience=SUPABASE_TOKEN_AUDIENCE,
            )
        except JWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired admin token.",
            ) from exc

    # Asymmetric (ES256 / RS256), let the Supabase SDK validate it.
    try:
        from supabase import create_client

        if not settings.supabase_url or not settings.supabase_anon_key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Supabase URL/anon key not configured.",
            )
        sb = create_client(settings.supabase_url, settings.supabase_anon_key)
        user_res = sb.auth.get_user(token)
        user = getattr(user_res, "user", None)
        if user is None or not getattr(user, "id", None):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired admin token.",
            )
        return {
            "sub": user.id,
            "email": getattr(user, "email", None),
            "aud": getattr(user, "aud", SUPABASE_TOKEN_AUDIENCE),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired admin token.",
        ) from exc


def _principal_for_user(user_id: str, email_fallback: str | None) -> AdminPrincipal:
    supabase = get_supabase()
    res = (
        supabase.table("users")
        .select("id, email, full_name, role")
        .eq("id", user_id)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authenticated user is not provisioned in RI Assessments.",
        )
    row = rows[0]
    role = row.get("role")
    if role not in ("admin", "reviewer", "viewer"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Unrecognized role '{role}'.",
        )
    return AdminPrincipal(
        user_id=row["id"],
        email=row.get("email") or email_fallback or "",
        full_name=row.get("full_name"),
        role=role,
    )


async def require_admin_jwt(
    authorization: Annotated[str | None, Header()] = None,
) -> AdminPrincipal:
    """Verifies a Supabase access token and resolves the linked
    public.users row. Any registered user passes; per-endpoint role checks
    sit on top via require_role()."""

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
        )
    token = authorization.split(" ", 1)[1]
    claims = _decode_supabase_jwt(token)
    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is missing the sub claim.",
        )
    return _principal_for_user(user_id, claims.get("email"))


def require_role(*allowed: str):
    """Dependency factory: pass through if principal.role is in `allowed`,
    else 403."""

    async def checker(
        principal: Annotated[AdminPrincipal, Depends(require_admin_jwt)],
    ) -> AdminPrincipal:
        if principal.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Role '{principal.role}' is not permitted for this action."
                ),
            )
        return principal

    return checker
