"""Communication templates."""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.techscape import TemplateIn, TemplateOut, TemplateUpdate, TemplatePreviewIn
from app.services.techscape import TemplateService
from app.services.techscape.audit import write_audit

from ._deps import require_business

router = APIRouter()


@router.get("", response_model=list[TemplateOut])
def list_templates(biz: dict = Depends(require_business), channel: str | None = None):
    return TemplateService().list(UUID(biz["id"]), channel=channel)


@router.post("", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
def create_template(payload: TemplateIn, biz: dict = Depends(require_business)):
    user = biz.get("_user") or {}
    out  = TemplateService().create(UUID(biz["id"]), payload.model_dump())
    write_audit(business_id=biz["id"], user_id=user.get("id"),
                action="template.created", resource_type="template",
                resource_id=out["id"], details={"channel": out["channel"]})
    return out


@router.get("/{template_id}", response_model=TemplateOut)
def get_template(template_id: UUID, biz: dict = Depends(require_business)):
    tpl = TemplateService().get(template_id, UUID(biz["id"]))
    if not tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return tpl


@router.put("/{template_id}", response_model=TemplateOut)
def update_template(template_id: UUID, payload: TemplateUpdate,
                    biz: dict = Depends(require_business)):
    user  = biz.get("_user") or {}
    patch = payload.model_dump(exclude_none=True)
    tpl   = TemplateService().update(template_id, UUID(biz["id"]), patch)
    if not tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    write_audit(business_id=biz["id"], user_id=user.get("id"),
                action="template.updated", resource_type="template",
                resource_id=str(template_id),
                details={"fields": list(patch.keys())})
    return tpl


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(template_id: UUID, biz: dict = Depends(require_business)):
    user = biz.get("_user") or {}
    if not TemplateService().delete(template_id, UUID(biz["id"])):
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    write_audit(business_id=biz["id"], user_id=user.get("id"),
                action="template.deleted", resource_type="template",
                resource_id=str(template_id))


@router.post("/{template_id}/preview")
def preview_template(template_id: UUID, payload: TemplatePreviewIn,
                     biz: dict = Depends(require_business)):
    svc = TemplateService()
    tpl = svc.get(template_id, UUID(biz["id"]))
    if not tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    rendered = svc.render(tpl["content"], payload.sample_data)
    return {"channel": tpl["channel"], "subject": tpl.get("subject_line"),
            "rendered": rendered}


@router.post("/{template_id}/approve", response_model=TemplateOut)
def approve_template(template_id: UUID, biz: dict = Depends(require_business)):
    """Mark a template as approved. Admin or manager only."""
    user = biz.get("_user") or {}
    if user and user.get("role") not in ("admin", "manager"):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "admin or manager role required")
    patch = {
        "approval_status":     "approved",
        "approved_at":         datetime.now(timezone.utc).isoformat(),
        "approved_by_user_id": user.get("id"),
    }
    out = TemplateService().update(template_id, UUID(biz["id"]), patch)
    if not out:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    write_audit(business_id=biz["id"], user_id=user.get("id"),
                action="template.approved", resource_type="template",
                resource_id=str(template_id))
    return out
