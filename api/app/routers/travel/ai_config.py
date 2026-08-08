"""
AI config endpoints (Phase 3 T2).

GET  /ai-config           → fetch config for this business (or branch if branch_id in token)
PUT  /ai-config           → update config (manager/admin/super_admin only)
POST /ai-config/seed      → create default config row if none exists (idempotent)

Config row is business-wide (branch_id NULL) unless the authed user is
branch-scoped (ts_users.branch_id set), in which case it reads/writes
the branch-scoped row and falls back to the business-wide row.

The PUT feeds directly into ai_engine.py's system-prompt construction
and escalation logic — changing escalation_rules takes effect on the
NEXT call turn (no restart required).
"""
from __future__ import annotations
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.deps import require_role
from app.database import get_supabase_admin

router = APIRouter()

_VIEWER_PLUS = require_role("viewer")
_MANAGER_PLUS = require_role("manager")


# ── Default seed values — matches Phase 2's hardcoded ai_engine.py constants ─
DEFAULT_CONFIG: dict[str, Any] = {
    "question_flow": [
        {"order": 1, "question": "Where would you like to travel?",        "field": "destination_hint"},
        {"order": 2, "question": "How many travelers will be joining?",     "field": "pax_count"},
        {"order": 3, "question": "What is your approximate budget?",         "field": "budget_inr"},
        {"order": 4, "question": "How many days are you planning to travel?","field": "duration_days"},
    ],
    "languages":        ["en", "hi"],
    "escalation_rules": {"budget_threshold": 100000, "intent_level": "hot"},
    "working_hours":    {"start": "09:00", "end": "21:00", "timezone": "Asia/Kolkata"},
    "voice_persona": {
        "name":     "Klara",
        "tone":     "warm_professional",
        "greeting": "Hello! I'm Klara, your GoGaga travel assistant. How can I help plan your perfect trip?",
    },
}


class AiConfigPatch(BaseModel):
    question_flow:    Optional[list[dict[str, Any]]] = None
    languages:        Optional[list[str]] = None
    escalation_rules: Optional[dict[str, Any]] = None
    working_hours:    Optional[dict[str, Any]] = None
    voice_persona:    Optional[dict[str, Any]] = None


def _get_config(db, business_id: str, branch_id: Optional[str]) -> dict | None:
    """Branch-scoped first, fallback to business-wide."""
    if branch_id:
        row = (
            db.table("travel_ai_config").select("*")
            .eq("business_id", business_id).eq("branch_id", branch_id)
            .limit(1).execute().data
        )
        if row:
            return row[0]
    row = (
        db.table("travel_ai_config").select("*")
        .eq("business_id", business_id).is_("branch_id", "null")
        .limit(1).execute().data
    )
    return row[0] if row else None


@router.get("")
def get_ai_config(user: dict = Depends(_VIEWER_PLUS)):
    db = get_supabase_admin()
    branch_id = user.get("branch_id")
    config = _get_config(db, user["business_id"], branch_id)
    if not config:
        # Auto-seed on first access — idempotent
        return _seed(user)
    return config


@router.put("")
def update_ai_config(body: AiConfigPatch, user: dict = Depends(_MANAGER_PLUS)):
    db = get_supabase_admin()
    branch_id = user.get("branch_id")
    config = _get_config(db, user["business_id"], branch_id)
    if not config:
        config = _seed(user)

    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if not patch:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No fields to update")

    # business_id is repeated on the UPDATE, not just on the _get_config read:
    # this row drives every future call's system prompt + escalation rules, so
    # an unscoped UPDATE would be a cross-tenant mutation of another business's
    # AI behaviour — worse than any read leak.
    updated = (
        db.table("travel_ai_config").update(patch)
        .eq("id", config["id"])
        .eq("business_id", user["business_id"]).execute().data
    )
    return updated[0] if updated else config


@router.post("/seed")
def seed_ai_config(user: dict = Depends(_MANAGER_PLUS)):
    """Idempotent — creates default config if none exists; no-ops if already set."""
    return _seed(user)


def _seed(user: dict) -> dict:
    db = get_supabase_admin()
    branch_id = user.get("branch_id")
    existing = _get_config(db, user["business_id"], branch_id)
    if existing:
        return existing
    row = db.table("travel_ai_config").insert({
        "business_id": user["business_id"],
        "branch_id":   branch_id,
        **DEFAULT_CONFIG,
    }).execute().data
    return row[0] if row else {}


def load_ai_config(business_id: str, branch_id: Optional[str] = None) -> dict:
    """Programmatic loader for ai_engine.py — returns DEFAULT_CONFIG if no DB row."""
    try:
        db = get_supabase_admin()
        config = _get_config(db, business_id, branch_id)
        return config if config else DEFAULT_CONFIG.copy()
    except Exception:
        return DEFAULT_CONFIG.copy()
