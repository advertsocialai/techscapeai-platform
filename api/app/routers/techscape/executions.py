"""Workflow executions + communication logs."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.techscape import ExecutionTrigger, ExecutionOut, CommunicationLogOut
from app.services.techscape import ExecutionService

from ._deps import require_business

router = APIRouter()


@router.post("/workflows/{workflow_id}/trigger",
             response_model=ExecutionOut, status_code=status.HTTP_202_ACCEPTED)
async def trigger_execution(workflow_id: UUID, payload: ExecutionTrigger,
                            biz: dict = Depends(require_business)):
    svc = ExecutionService()
    try:
        return await svc.trigger(
            workflow_id=workflow_id,
            business_id=UUID(biz["id"]),
            trigger_data=payload.trigger_data,
            client_email=payload.client_email,
            client_phone=payload.client_phone,
            client_name=payload.client_name,
            client_identifier=payload.client_identifier,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


@router.get("/executions", response_model=list[ExecutionOut])
def list_executions(biz: dict = Depends(require_business),
                    workflow_id: UUID | None = None, limit: int = 50):
    return ExecutionService().list_executions(UUID(biz["id"]),
                                              workflow_id=workflow_id, limit=limit)


@router.get("/executions/{execution_id}", response_model=ExecutionOut)
def get_execution(execution_id: UUID, biz: dict = Depends(require_business)):
    row = ExecutionService().get_execution(execution_id, UUID(biz["id"]))
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return row


@router.post("/executions/{execution_id}/cancel", response_model=ExecutionOut)
def cancel_execution(execution_id: UUID, biz: dict = Depends(require_business)):
    """Mark an in-progress execution as cancelled. No-op for already-terminal runs."""
    svc = ExecutionService()
    row = svc.get_execution(execution_id, UUID(biz["id"]))
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if row["execution_status"] in ("completed", "failed", "cancelled"):
        return row  # idempotent
    from datetime import datetime, timezone
    svc.db.table("ts_workflow_executions").update({
        "execution_status": "cancelled",
        "completed_at":      datetime.now(timezone.utc).isoformat(),
    }).eq("id", str(execution_id)).eq("business_id", str(biz["id"])).execute()
    return svc.get_execution(execution_id, UUID(biz["id"])) or row


@router.post("/executions/{execution_id}/retry", response_model=ExecutionOut,
             status_code=status.HTTP_202_ACCEPTED)
async def retry_execution(execution_id: UUID, biz: dict = Depends(require_business)):
    """Re-trigger the workflow with the original execution's trigger_data + client info."""
    svc = ExecutionService()
    src = svc.get_execution(execution_id, UUID(biz["id"]))
    if not src:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    try:
        return await svc.trigger(
            workflow_id=UUID(src["workflow_id"]),
            business_id=UUID(biz["id"]),
            trigger_data=src.get("trigger_data") or {},
            client_email=src.get("client_email"),
            client_phone=src.get("client_phone"),
            client_name=src.get("client_name"),
            client_identifier=src.get("client_identifier"),
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


@router.get("/communications", response_model=list[CommunicationLogOut])
def list_communications(biz: dict = Depends(require_business),
                        execution_id: UUID | None = None, limit: int = 100):
    return ExecutionService().list_communications(
        UUID(biz["id"]), execution_id=execution_id, limit=limit
    )


@router.get("/communications/{log_id}", response_model=CommunicationLogOut)
def get_communication(log_id: UUID, biz: dict = Depends(require_business)):
    db = ExecutionService().db
    r = (
        db.table("ts_communication_logs").select("*")
        .eq("id", str(log_id)).eq("business_id", str(biz["id"]))
        .limit(1).execute().data
    )
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return r[0]
