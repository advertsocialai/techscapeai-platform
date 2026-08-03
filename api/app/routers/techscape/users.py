"""
Users management (Phase 1) — branch-scoped CRUD on ts_users.

Role gating uses app/core/deps.py's hierarchy (super_admin/admin == rank 4,
manager == rank 3 == spec's "admin" tier, user/agent == rank 2, viewer ==
rank 1 — see that file's docstring for the full legacy<->spec mapping).

Scoping: super_admin/admin (rank 4) see the whole business; manager
(rank 3, branch-admin) is restricted to their own branch_id. Role
elevation is blocked for branch-admins — they cannot create/promote to
manager/admin/super_admin. Out-of-scope resources return 404, never 403
(don't leak existence — see api-conventions.md).
"""
from __future__ import annotations
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.deps import get_current_user, require_role
from app.schemas.techscape import (
    UserCreateIn, UserDeleteOut, UserListOut, UserOut, UserUpdateIn,
)
from app.services.techscape import BusinessService

router = APIRouter()

# rank >= manager (3): branch-admin and above may list/read/write users.
_manager_plus   = require_role("manager")
# rank >= admin/super_admin (4) only: hard delete gate.
_super_admin    = require_role("super_admin")

_ELEVATED_ROLES = {"manager", "admin", "super_admin"}


def _is_super(user: dict) -> bool:
    return user.get("role") in ("admin", "super_admin")


@router.get("", response_model=UserListOut)
def list_users(
    role: str | None = Query(default=None),
    status_: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(_manager_plus),
):
    svc = BusinessService()
    branch_scope = None if _is_super(user) else user.get("branch_id")
    items, total = svc.list_users(
        business_id=UUID(user["business_id"]),
        branch_id=UUID(branch_scope) if branch_scope else None,
        role=role, status=status_, limit=limit, offset=offset,
    )
    return UserListOut(items=items, total=total)


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: UUID, user: dict = Depends(_manager_plus)):
    svc = BusinessService()
    branch_scope = None if _is_super(user) else user.get("branch_id")
    row = svc.get_user_scoped(
        user_id, business_id=UUID(user["business_id"]),
        branch_id=UUID(branch_scope) if branch_scope else None,
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return row


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreateIn, user: dict = Depends(_manager_plus)):
    svc = BusinessService()
    if not _is_super(user):
        # branch-admin: cannot create manager/admin/super_admin, and can only
        # create within their own branch.
        if payload.role in ("manager", "admin", "super_admin"):
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                 "Cannot create a user at or above your own role")
        if payload.branch_id and str(payload.branch_id) != str(user.get("branch_id")):
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                 "Cannot create a user outside your branch")
        payload = payload.model_copy(update={"branch_id": user.get("branch_id")})

    if svc.find_user_by_email(payload.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "User already exists")

    created = svc.create_user_scoped(
        business_id=UUID(user["business_id"]), payload=payload.model_dump()
    )
    return created


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: UUID, payload: UserUpdateIn, user: dict = Depends(_manager_plus)):
    svc = BusinessService()
    branch_scope = None if _is_super(user) else user.get("branch_id")
    target = svc.get_user_scoped(
        user_id, business_id=UUID(user["business_id"]),
        branch_id=UUID(branch_scope) if branch_scope else None,
    )
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    fields = payload.model_dump(exclude_unset=True)
    if not _is_super(user):
        # No role elevation by a branch-admin, at all — even to their own tier.
        if "role" in fields and fields["role"] is not None:
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                 "Branch admins cannot change roles")
        if "branch_id" in fields and str(fields["branch_id"]) != str(user.get("branch_id")):
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                 "Cannot move a user outside your branch")

    updated = svc.update_user(user_id, fields)
    return updated


@router.delete("/{user_id}", response_model=UserDeleteOut)
def delete_user(user_id: UUID, user: dict = Depends(_super_admin)):
    if str(user_id) == str(user["id"]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot delete your own account")
    svc = BusinessService()
    target = svc.get_user_scoped(user_id, business_id=UUID(user["business_id"]))
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    svc.deactivate_user(user_id)
    return UserDeleteOut(id=user_id, status="inactive")
