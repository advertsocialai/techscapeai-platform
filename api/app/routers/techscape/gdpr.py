"""GDPR / CCPA endpoints: data export + right-to-erasure."""
from __future__ import annotations
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.services.techscape.gdpr_service import GDPRService
from app.services.techscape.audit import write_audit

from ._deps import require_business

router = APIRouter()


@router.get("/export")
def export_my_data(biz: dict = Depends(require_business)):
    """Return a full snapshot of every row tied to the calling business."""
    write_audit(business_id=biz["id"], action="gdpr.export",
                resource_type="business", resource_id=biz["id"])
    return GDPRService().export_business(UUID(biz["id"]))


@router.delete("/erase", status_code=status.HTTP_200_OK)
def erase_business(biz: dict = Depends(require_business)):
    """Hard-delete all rows tied to the business and tombstone the business row."""
    user = biz.get("_user") or {}
    if user and user.get("role") not in ("admin", None):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin role required")
    deleted = GDPRService().erase_business(UUID(biz["id"]))
    write_audit(business_id=biz["id"], user_id=user.get("id"),
                action="gdpr.erase_business", details=deleted)
    return {"ok": True, "deleted": deleted}


@router.delete("/contacts/{contact_id}")
def erase_contact(contact_id: UUID, biz: dict = Depends(require_business)):
    """Right-to-be-forgotten on a single contact."""
    ok = GDPRService().erase_contact(contact_id=contact_id, business_id=UUID(biz["id"]))
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    write_audit(business_id=biz["id"],
                action="gdpr.erase_contact",
                resource_type="business_contact",
                resource_id=str(contact_id))
    return {"ok": True}
