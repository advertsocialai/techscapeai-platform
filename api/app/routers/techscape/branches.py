"""Branches (Phase 1) — dedicated `branches` table, business-scoped only
(no further sub-scoping: branches ARE the scope unit for users/leads)."""
from __future__ import annotations
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.deps import get_current_user, require_role
from app.schemas.techscape import BranchCreateIn, BranchListOut, BranchOut, BranchStatsOut
from app.services.techscape import BranchService

router = APIRouter()

_read  = require_role("viewer")       # any authenticated user
_write = require_role("super_admin")  # only the top rank creates branches


@router.get("", response_model=BranchListOut)
def list_branches(
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(_read),
):
    items, total = BranchService().list(
        business_id=UUID(user["business_id"]), limit=limit, offset=offset
    )
    return BranchListOut(items=items, total=total)


@router.post("", response_model=BranchOut, status_code=status.HTTP_201_CREATED)
def create_branch(payload: BranchCreateIn, user: dict = Depends(_write)):
    return BranchService().create(
        business_id=UUID(user["business_id"]), payload=payload.model_dump()
    )


@router.get("/{branch_id}", response_model=BranchStatsOut)
def get_branch(branch_id: UUID, user: dict = Depends(_read)):
    row = BranchService().get(branch_id, business_id=UUID(user["business_id"]))
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Branch not found")
    return BranchStatsOut(**row, stats=BranchService.stats_stub())
