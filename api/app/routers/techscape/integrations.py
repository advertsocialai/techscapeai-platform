"""External-system integration endpoints (CRM, booking, payment, etc.)."""
from __future__ import annotations
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.services.techscape.audit import write_audit
from app.services.techscape.integration_service import IntegrationService

from ._deps import require_business

router = APIRouter()


class IntegrationIn(BaseModel):
    integration_name: str
    integration_type: str  # booking_system | crm | payment_gateway | custom_api
    api_endpoint:        Optional[str] = None
    authentication_type: Optional[str] = None
    credentials:         Optional[dict[str, Any]] = None
    webhook_url:         Optional[str] = None
    event_types:         Optional[list[str]] = None
    sync_frequency:      str = "manual"


@router.get("")
def list_integrations(biz: dict = Depends(require_business)):
    return IntegrationService().list(UUID(biz["id"]))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_integration(payload: IntegrationIn, biz: dict = Depends(require_business)):
    user = biz.get("_user") or {}
    out  = IntegrationService().create(business_id=UUID(biz["id"]),
                                        **payload.model_dump(exclude_none=True))
    write_audit(business_id=biz["id"], user_id=user.get("id"),
                action="integration.created", resource_type="integration",
                resource_id=out["id"],
                details={"type": out.get("integration_type"),
                         "name": out.get("integration_name")})
    return out


@router.put("/{integration_id}")
def update_integration(integration_id: UUID, payload: IntegrationIn,
                       biz: dict = Depends(require_business)):
    out = IntegrationService().update(integration_id, UUID(biz["id"]),
                                      payload.model_dump(exclude_none=True))
    if not out:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return out


@router.delete("/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_integration(integration_id: UUID, biz: dict = Depends(require_business)):
    user = biz.get("_user") or {}
    if not IntegrationService().delete(integration_id, UUID(biz["id"])):
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    write_audit(business_id=biz["id"], user_id=user.get("id"),
                action="integration.deleted", resource_type="integration",
                resource_id=str(integration_id))


@router.post("/{integration_id}/sync")
def sync_integration(integration_id: UUID, biz: dict = Depends(require_business)):
    """
    Trigger an immediate sync. For MVP we update last_synced_at and
    last_sync_status='success'. Real implementations would dispatch a job
    that calls the external system's API using the decrypted credentials.
    """
    from datetime import datetime, timezone
    svc = IntegrationService()
    rows = svc.list(UUID(biz["id"]))
    if not any(r["id"] == str(integration_id) for r in rows):
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    patch = {
        "last_synced_at":   datetime.now(timezone.utc).isoformat(),
        "last_sync_status": "success",
        "last_sync_error":  None,
    }
    out  = svc.update(integration_id, UUID(biz["id"]), patch)
    user = biz.get("_user") or {}
    write_audit(business_id=biz["id"], user_id=user.get("id"),
                action="integration.synced", resource_type="integration",
                resource_id=str(integration_id))
    return {"ok": True, "integration": out}


@router.get("/{integration_id}/status")
def integration_status(integration_id: UUID, biz: dict = Depends(require_business)):
    """Health: is_active + last_synced_at + last_sync_status + creds present."""
    svc = IntegrationService()
    rows = svc.list(UUID(biz["id"]))
    match = next((r for r in rows if r["id"] == str(integration_id)), None)
    if not match:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    has_creds = bool(svc.get_credentials(integration_id, UUID(biz["id"])))
    return {
        "id":                match["id"],
        "name":              match.get("integration_name"),
        "type":              match.get("integration_type"),
        "is_active":         match.get("is_active"),
        "last_synced_at":    match.get("last_synced_at"),
        "last_sync_status":  match.get("last_sync_status"),
        "last_sync_error":   match.get("last_sync_error"),
        "has_credentials":   has_creds,
        "healthy":           bool(match.get("is_active") and (match.get("last_sync_status") in (None, "success"))),
    }
