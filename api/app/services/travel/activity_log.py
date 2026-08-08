"""
Activity log (Phase 4 T7) — one helper, append-only.

THE GUARDRAIL
    Adding audit logging must not change the behaviour of the endpoint it
    is wired into. `record()` therefore NEVER raises into its caller: every
    exception — a dead database, a bad UUID, a CHECK violation on an
    unknown entity_type, a network timeout — is caught, logged at WARNING,
    and swallowed. It returns the inserted row's id on success and None on
    any failure, so a caller may check the result but is never forced to.

    Concretely: if this module is broken, POST /calls/{id}/takeover/full
    still returns 200 with the same body. An audit trail is worth having,
    but it is worth strictly less than the endpoint working.

WRITE PATH
    `record()` is the ONLY write path to public.activity_log in this
    codebase, and it only ever INSERTs. There is no update() and no
    delete() — deliberately. That is what makes the table's append-only
    guarantee checkable by inspection (see migration 0014's header).

USAGE
    from app.services.travel.activity_log import record

    record(
        actor_id=user["id"],
        action="call.takeover.full",
        entity_type="call",
        entity_id=str(call_id),
        business_id=user["business_id"],
        branch_id=user.get("branch_id"),
        metadata={"from_state": "monitor", "to_state": "full"},
    )
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from app.database import get_supabase_admin

logger = logging.getLogger(__name__)

#: Mirrors migration 0014's entity_type CHECK constraint. Anything outside
#: this set is coerced to 'other' rather than being allowed to fail the
#: INSERT — an audit row with a slightly vague entity_type beats no audit
#: row at all, and the real value is preserved in metadata.
ENTITY_TYPES: frozenset[str] = frozenset({
    "call", "lead", "follow_up", "package", "booking", "payment_link",
    "ai_config", "user", "branch", "whatsapp_message", "report",
    "business", "other",
})

_MAX_ACTION_LEN = 100


def _coerce_json(value: Any) -> Any:
    """Make metadata JSON-serialisable without ever raising."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _coerce_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_coerce_json(v) for v in value]
    return str(value)


def _opt_str(value: Any) -> Optional[str]:
    return None if value is None else str(value)


def record(
    actor_id: Optional[Any],
    action: str,
    entity_type: str,
    entity_id: Optional[Any],
    business_id: Any,
    branch_id: Optional[Any] = None,
    metadata: Optional[dict] = None,
) -> Optional[str]:
    """Append one audit row. NEVER raises. Returns the new row id or None.

    Args:
        actor_id:    ts_users.id of whoever did it, or None for system
                     actions (webhooks, schedulers, the AI engine itself).
        action:      dotted verb, e.g. 'call.takeover.full'. Truncated to
                     100 chars to match the column.
        entity_type: one of ENTITY_TYPES; anything else becomes 'other'
                     with the original preserved in metadata.
        entity_id:   the affected row's id, or None for non-row actions.
        business_id: tenant scope — required; without it the row could not
                     be read back safely, so a missing value aborts (still
                     without raising).
        branch_id:   optional branch scope for the ?branch= filter.
        metadata:    any extra JSON-able context (before/after values, etc).
    """
    try:
        if not business_id:
            logger.warning("activity_log.record skipped: missing business_id (action=%s)", action)
            return None

        extra = dict(metadata or {})
        clean_type = entity_type if entity_type in ENTITY_TYPES else "other"
        if clean_type != entity_type:
            extra["_raw_entity_type"] = entity_type

        row = {
            "business_id": str(business_id),
            "actor_id":    _opt_str(actor_id),
            "action":      str(action)[:_MAX_ACTION_LEN],
            "entity_type": clean_type,
            "entity_id":   _opt_str(entity_id),
            "branch_id":   _opt_str(branch_id),
            "metadata":    _coerce_json(extra) or {},
        }

        inserted = get_supabase_admin().table("activity_log").insert(row).execute().data
        return inserted[0]["id"] if inserted else None

    except Exception as exc:  # noqa: BLE001 — swallowing is the entire point
        logger.warning(
            "activity_log.record failed (action=%s entity=%s/%s): %s",
            action, entity_type, entity_id, exc, exc_info=True,
        )
        return None


def query(
    business_id: Any,
    *,
    actor: Optional[Any] = None,
    entity: Optional[str] = None,
    entity_id: Optional[Any] = None,
    branch: Optional[Any] = None,
    action: Optional[str] = None,
    limit: int = 100,
) -> list[dict]:
    """Read the audit trail, always scoped to one business. Newest first.

    Unlike record(), this DOES propagate errors — a read endpoint that
    silently returns [] when the database is down would be lying to a
    manager about what happened.
    """
    q = (
        get_supabase_admin().table("activity_log").select("*")
        .eq("business_id", str(business_id))
    )
    if actor is not None:
        q = q.eq("actor_id", str(actor))
    if entity is not None:
        q = q.eq("entity_type", entity)
    if entity_id is not None:
        q = q.eq("entity_id", str(entity_id))
    if branch is not None:
        q = q.eq("branch_id", str(branch))
    if action is not None:
        q = q.eq("action", action)
    return q.order("at", desc=True).limit(limit).execute().data or []
