from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import require_role
from app.core.security import AuthUser
from app.models.schemas import AuditEntry
from app.services import audit as audit_service

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[AuditEntry])
def get_audit_log(limit: int = 200, user: AuthUser = Depends(require_role("admin"))):
    return audit_service.list_entries(limit=limit)
