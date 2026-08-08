"""
Activity log endpoint (Phase 4 T7).

GET /activity-log?actor=&entity=&branch=   → manager+ , business-scoped

READ-ONLY BY DESIGN. There is deliberately no POST/PATCH/DELETE here: the
only write path to public.activity_log in this codebase is
services/travel/activity_log.py record(), which endpoints call internally.
Exposing a write endpoint would let a caller forge or edit audit rows,
which defeats the point of an audit trail (see migration 0014's header for
the full enforcement story).

Filters:
    actor      → activity_log.actor_id  (a ts_users.id)
    entity     → activity_log.entity_type ('call', 'lead', 'package', ...)
    entity_id  → narrow to one specific row's history
    branch     → activity_log.branch_id
    action     → exact dotted verb, e.g. 'call.takeover.full'
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.deps import require_role
from app.services.travel import activity_log

router = APIRouter()

_MANAGER_PLUS = require_role("manager")

# Branch-scoped managers see only their own branch, regardless of ?branch=.
_UNSCOPED_ROLES = {"admin", "super_admin"}


@router.get("")
def list_activity(
    actor:     Optional[UUID] = Query(default=None),
    entity:    Optional[str]  = Query(default=None, description="entity_type, e.g. 'call'"),
    entity_id: Optional[UUID] = Query(default=None),
    branch:    Optional[UUID] = Query(default=None),
    action:    Optional[str]  = Query(default=None),
    limit:     int            = Query(default=100, ge=1, le=500),
    user: dict = Depends(_MANAGER_PLUS),
):
    # A manager pinned to one branch cannot widen their view by passing a
    # different ?branch= — their own branch always wins.
    own_branch = user.get("branch_id")
    if own_branch and user.get("role") not in _UNSCOPED_ROLES:
        branch = UUID(own_branch)

    return activity_log.query(
        user["business_id"],
        actor=actor,
        entity=entity,
        entity_id=entity_id,
        branch=branch,
        action=action,
        limit=limit,
    )
