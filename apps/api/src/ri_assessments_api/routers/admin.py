"""Admin endpoints (spec §14.1). Requires Supabase JWT.
Stub router — concrete endpoints land in later phases."""

from fastapi import APIRouter, Depends

from ..auth import require_admin_jwt

router = APIRouter(tags=["admin"], dependencies=[Depends(require_admin_jwt)])


@router.get("/ping")
def admin_ping() -> dict[str, str]:
    return {"ok": "admin"}
