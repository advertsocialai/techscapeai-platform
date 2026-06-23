"""Workflow + step management."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.schemas.techscape import (
    ExecutionTrigger, ExecutionOut,
    WorkflowIn, WorkflowUpdate, WorkflowOut, WorkflowStepIn, WorkflowStepOut,
)
from app.services.techscape import WorkflowService, ExecutionService, AnalyticsService
from app.services.techscape.audit import write_audit

from ._deps import require_business

router = APIRouter()


class ReorderStepsIn(BaseModel):
    ordered_step_ids: list[UUID]


@router.get("", response_model=list[WorkflowOut])
def list_workflows(biz: dict = Depends(require_business),
                   include_archived: bool = False):
    svc = WorkflowService()
    rows = svc.list_workflows(UUID(biz["id"]), include_archived=include_archived)
    return [{**r, "steps": []} for r in rows]


@router.post("", response_model=WorkflowOut, status_code=status.HTTP_201_CREATED)
def create_workflow(payload: WorkflowIn, biz: dict = Depends(require_business)):
    """Create a new workflow. Enforces the per-tier max_workflows cap."""
    svc = WorkflowService()
    biz_id = UUID(biz["id"])
    user   = biz.get("_user") or {}

    # Enforce subscription cap (max_workflows). 0/None = unlimited.
    cap = int(biz.get("max_workflows") or 0)
    if cap:
        active = (
            svc.db.table("ts_workflows").select("id", count="exact")
            .eq("business_id", str(biz_id))
            .eq("is_archived", False).execute()
        ).count or 0
        if active >= cap:
            raise HTTPException(
                status.HTTP_402_PAYMENT_REQUIRED,
                f"max_workflows cap reached ({active}/{cap}). "
                "Upgrade your subscription to add more workflows.",
            )

    wf = svc.create_workflow(biz_id, payload.model_dump())
    write_audit(business_id=biz["id"], user_id=user.get("id"),
                action="workflow.created", resource_type="workflow",
                resource_id=wf["id"], details={"name": wf["name"]})
    return wf


@router.get("/{workflow_id}", response_model=WorkflowOut)
def get_workflow(workflow_id: UUID, biz: dict = Depends(require_business)):
    svc = WorkflowService()
    wf = svc.get_workflow(workflow_id, UUID(biz["id"]))
    if not wf:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return wf


@router.put("/{workflow_id}", response_model=WorkflowOut)
def update_workflow(workflow_id: UUID, payload: WorkflowUpdate,
                    biz: dict = Depends(require_business)):
    svc = WorkflowService()
    user = biz.get("_user") or {}
    patch = payload.model_dump(exclude_none=True)
    wf = svc.update_workflow(workflow_id, UUID(biz["id"]), patch)
    if not wf:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    write_audit(business_id=biz["id"], user_id=user.get("id"),
                action="workflow.updated", resource_type="workflow",
                resource_id=str(workflow_id), details={"fields": list(patch.keys())})
    return wf


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_workflow(workflow_id: UUID, biz: dict = Depends(require_business)):
    svc = WorkflowService()
    user = biz.get("_user") or {}
    if not svc.delete_workflow(workflow_id, UUID(biz["id"])):
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    write_audit(business_id=biz["id"], user_id=user.get("id"),
                action="workflow.archived", resource_type="workflow",
                resource_id=str(workflow_id))


@router.post("/{workflow_id}/activate", response_model=WorkflowOut)
def activate(workflow_id: UUID, biz: dict = Depends(require_business)):
    svc  = WorkflowService()
    user = biz.get("_user") or {}
    wf   = svc.set_active(workflow_id, UUID(biz["id"]), True) or _404()
    write_audit(business_id=biz["id"], user_id=user.get("id"),
                action="workflow.activated", resource_type="workflow",
                resource_id=str(workflow_id))
    return wf


@router.post("/{workflow_id}/deactivate", response_model=WorkflowOut)
def deactivate(workflow_id: UUID, biz: dict = Depends(require_business)):
    svc  = WorkflowService()
    user = biz.get("_user") or {}
    wf   = svc.set_active(workflow_id, UUID(biz["id"]), False) or _404()
    write_audit(business_id=biz["id"], user_id=user.get("id"),
                action="workflow.deactivated", resource_type="workflow",
                resource_id=str(workflow_id))
    return wf


# ── Steps ─────────────────────────────────────────────────────
from typing import Any  # noqa: E402  (kept for backwards-compat)


@router.post("/{workflow_id}/steps", response_model=WorkflowStepOut,
             status_code=status.HTTP_201_CREATED)
def add_step(workflow_id: UUID, payload: WorkflowStepIn,
             biz: dict = Depends(require_business)):
    svc = WorkflowService()
    if not svc.get_workflow(workflow_id, UUID(biz["id"])):
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return svc.add_step(workflow_id, payload.model_dump())


@router.put("/{workflow_id}/steps/{step_id}", response_model=WorkflowStepOut)
def update_step(workflow_id: UUID, step_id: UUID, payload: WorkflowStepIn,
                biz: dict = Depends(require_business)):
    svc = WorkflowService()
    if not svc.get_workflow(workflow_id, UUID(biz["id"])):
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    step = svc.update_step(step_id, payload.model_dump())
    if not step:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return step


@router.delete("/{workflow_id}/steps/{step_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_step(workflow_id: UUID, step_id: UUID,
                biz: dict = Depends(require_business)):
    svc = WorkflowService()
    if not svc.get_workflow(workflow_id, UUID(biz["id"])):
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    svc.delete_step(step_id)


@router.post("/{workflow_id}/steps/reorder", response_model=list[WorkflowStepOut])
def reorder_steps(workflow_id: UUID, payload: ReorderStepsIn,
                  biz: dict = Depends(require_business)):
    svc = WorkflowService()
    wf = svc.get_workflow(workflow_id, UUID(biz["id"]))
    if not wf:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    existing_ids = {UUID(s["id"]) for s in (wf.get("steps") or [])}
    if set(payload.ordered_step_ids) != existing_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "ordered_step_ids must contain exactly the workflow's step ids")
    return svc.reorder_steps(workflow_id, payload.ordered_step_ids)


@router.post("/{workflow_id}/duplicate", response_model=WorkflowOut,
             status_code=status.HTTP_201_CREATED)
def duplicate(workflow_id: UUID, biz: dict = Depends(require_business)):
    out = WorkflowService().duplicate(workflow_id, UUID(biz["id"]))
    if not out:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return out


@router.post("/{workflow_id}/test", response_model=ExecutionOut,
             status_code=status.HTTP_202_ACCEPTED)
async def test_workflow(workflow_id: UUID, payload: ExecutionTrigger,
                        biz: dict = Depends(require_business)):
    """
    Run the workflow against sample data. Identical to /trigger but
    isolated semantically — same execution + log rows are written so the
    user can inspect them in the dashboard.
    """
    if not WorkflowService().get_workflow(workflow_id, UUID(biz["id"])):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "workflow not found")
    try:
        return await ExecutionService().trigger(
            workflow_id=workflow_id, business_id=UUID(biz["id"]),
            trigger_data=payload.trigger_data,
            client_email=payload.client_email,
            client_phone=payload.client_phone,
            client_name=payload.client_name,
            client_identifier=payload.client_identifier,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


@router.get("/{workflow_id}/analytics")
def workflow_analytics(workflow_id: UUID, biz: dict = Depends(require_business)):
    """Per-workflow stats: execution counts, last run, total cost, channel mix."""
    if not WorkflowService().get_workflow(workflow_id, UUID(biz["id"])):
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return AnalyticsService().workflow_stats(business_id=UUID(biz["id"]),
                                              workflow_id=workflow_id)


def _404():
    raise HTTPException(status.HTTP_404_NOT_FOUND)
