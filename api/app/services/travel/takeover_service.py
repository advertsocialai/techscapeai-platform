"""
Human takeover service (Phase 3 T1).

State machine: ai → monitoring → coaching → human → ai
Transitions write a travel_call_events row and broadcast takeover_state
on the existing /ws/calls/{call_id} feed (call_feed.publish).

Plivo MPC API calls are structurally complete but BLOCKED until:
  - Phase 2B runs (MPC migration, answer webhook returns MPC XML)
  - PLIVO_AUTH_ID/TOKEN/PHONE_NUMBER added to .env
  - PUBLIC_BASE_URL (ngrok) set
See BLOCKERS.md B-P3-01, B-P2B-01.

India media anchoring rule: supervisor leg must be on an India (+91)
Plivo account — no international bridge. Foreign supervisors get
transcript-only via /ws/calls/{id} read access (no audio fork).
"""
from __future__ import annotations
import asyncio
import logging
from typing import Optional
from uuid import UUID

import httpx

from app.core.config import settings
from app.database import get_supabase_admin

logger = logging.getLogger(__name__)

# Plivo REST base — uses service-account auth, India region account
_PLIVO_BASE = "https://api.plivo.com/v1/Account/{auth_id}"

VALID_TRANSITIONS: dict[str, list[str]] = {
    "ai":         ["monitoring", "coaching", "human"],
    "monitoring": ["coaching", "human", "ai"],
    "coaching":   ["human", "ai"],
    "human":      ["ai"],
}


class TakeoverError(Exception):
    pass


class TakeoverService:
    def __init__(self) -> None:
        self.db = get_supabase_admin()

    # ── Internal helpers ────────────────────────────────────────────

    def _get_call(self, call_id: UUID, business_id: UUID) -> dict:
        rows = (
            self.db.table("travel_calls").select("*")
            .eq("id", str(call_id))
            .eq("business_id", str(business_id))
            .limit(1).execute().data
        )
        if not rows:
            raise TakeoverError("call_not_found")
        return rows[0]

    def _assert_transition(self, current: str, target: str) -> None:
        if target not in VALID_TRANSITIONS.get(current, []):
            raise TakeoverError(
                f"invalid_transition: {current} → {target} "
                f"(allowed from {current}: {VALID_TRANSITIONS.get(current, [])})"
            )

    def _update_takeover_state(self, call_id: UUID, business_id: UUID,
                               new_state: str, mode: str | None = None) -> dict:
        # business_id is a required predicate on the UPDATE itself, not just on
        # the _get_call() read above it: a cross-tenant mutation is worse than a
        # read leak, so the write must not depend on an earlier check staying
        # correct as this state machine grows.
        patch: dict = {"takeover_state": new_state}
        if mode is not None:
            patch["mode"] = mode
        row = (
            self.db.table("travel_calls").update(patch)
            .eq("id", str(call_id))
            .eq("business_id", str(business_id))
            .execute().data
        )
        return row[0] if row else {}

    def _log_event(
        self, call_id: UUID, event_type: str, actor_id: Optional[UUID], payload: dict
    ) -> None:
        self.db.table("travel_call_events").insert({
            "call_id":    str(call_id),
            "event_type": event_type,
            "actor_id":   str(actor_id) if actor_id else None,
            "payload":    payload,
        }).execute()

    # ── Plivo MPC API (BLOCKED until Phase 2B + creds) ─────────────

    def _plivo_configured(self) -> bool:
        return bool(settings.PLIVO_AUTH_ID and settings.PLIVO_AUTH_TOKEN)

    async def _plivo_add_supervisor(self, mpc_uuid: str, supervisor_number: str, coach: bool) -> dict:
        """Add supervisor to MPC conference.
        coach=True  → coachMode (hears all, not heard) → monitoring
        coach=False → normal participant heard by customer → coaching
        BLOCKED: needs PLIVO_AUTH_ID/TOKEN + active MPC conference (Phase 2B).
        """
        if not self._plivo_configured():
            logger.warning("Plivo not configured — cannot add supervisor to MPC (B-P3-01)")
            return {"stub": True}
        base = _PLIVO_BASE.format(auth_id=settings.PLIVO_AUTH_ID)
        async with httpx.AsyncClient(auth=(settings.PLIVO_AUTH_ID, settings.PLIVO_AUTH_TOKEN)) as c:
            r = await c.post(f"{base}/Conference/{mpc_uuid}/Member/", json={
                "from": settings.PLIVO_PHONE_NUMBER,
                "to": supervisor_number,
                "role": "agent",
                "coach_mode": coach,
            })
            r.raise_for_status()
            return r.json()

    async def _plivo_mute_participant(self, mpc_uuid: str, member_id: str) -> None:
        """Mute the AI-agent participant (takeover/full)."""
        if not self._plivo_configured():
            logger.warning("Plivo not configured — cannot mute AI participant (B-P3-01)")
            return
        base = _PLIVO_BASE.format(auth_id=settings.PLIVO_AUTH_ID)
        async with httpx.AsyncClient(auth=(settings.PLIVO_AUTH_ID, settings.PLIVO_AUTH_TOKEN)) as c:
            await c.post(f"{base}/Conference/{mpc_uuid}/Member/{member_id}/Mute/")

    async def _plivo_unmute_participant(self, mpc_uuid: str, member_id: str) -> None:
        """Unmute AI-agent participant (release)."""
        if not self._plivo_configured():
            logger.warning("Plivo not configured — cannot unmute AI participant (B-P3-01)")
            return
        base = _PLIVO_BASE.format(auth_id=settings.PLIVO_AUTH_ID)
        async with httpx.AsyncClient(auth=(settings.PLIVO_AUTH_ID, settings.PLIVO_AUTH_TOKEN)) as c:
            await c.delete(f"{base}/Conference/{mpc_uuid}/Member/{member_id}/Mute/")

    # ── State transitions ───────────────────────────────────────────

    async def monitor(
        self, call_id: UUID, business_id: UUID,
        actor_id: Optional[UUID], supervisor_number: Optional[str],
    ) -> dict:
        call = self._get_call(call_id, business_id)
        self._assert_transition(call["takeover_state"], "monitoring")

        # Plivo: add supervisor in coachMode=true — BLOCKED without creds
        mpc_result = {}
        if call.get("mpc_uuid") and supervisor_number:
            mpc_result = await self._plivo_add_supervisor(
                call["mpc_uuid"], supervisor_number, coach=True
            )

        updated = self._update_takeover_state(call_id, business_id, "monitoring")
        self._log_event(call_id, "takeover_monitor", actor_id, {
            "previous_state": call["takeover_state"],
            "supervisor_number": supervisor_number,
            "mpc_result": mpc_result,
        })
        return updated

    async def barge(
        self, call_id: UUID, business_id: UUID,
        actor_id: Optional[UUID], supervisor_number: Optional[str],
    ) -> dict:
        call = self._get_call(call_id, business_id)
        self._assert_transition(call["takeover_state"], "coaching")

        mpc_result = {}
        if call.get("mpc_uuid") and supervisor_number:
            mpc_result = await self._plivo_add_supervisor(
                call["mpc_uuid"], supervisor_number, coach=False
            )

        updated = self._update_takeover_state(call_id, business_id, "coaching")
        self._log_event(call_id, "takeover_barge", actor_id, {
            "previous_state": call["takeover_state"],
            "supervisor_number": supervisor_number,
            "mpc_result": mpc_result,
        })
        return updated

    async def full_takeover(
        self, call_id: UUID, business_id: UUID, actor_id: Optional[UUID],
    ) -> dict:
        """AI goes silent (muted in MPC); mode ai→agent. AI continues writing
        call_events + transcript rows as a silent note-taker."""
        call = self._get_call(call_id, business_id)
        self._assert_transition(call["takeover_state"], "human")

        # Mute AI participant — BLOCKED without Plivo creds (B-P3-01)
        # AI's member_id not tracked yet (Phase 2B adds it when joining MPC)
        if call.get("mpc_uuid"):
            logger.info("full takeover: would mute AI participant on MPC %s — BLOCKED (creds absent)",
                        call["mpc_uuid"])

        updated = self._update_takeover_state(call_id, business_id, "human", mode="agent")
        self._log_event(call_id, "takeover_full", actor_id, {
            "previous_state": call["takeover_state"],
            "previous_mode": call.get("mode"),
        })
        return updated

    async def release(
        self, call_id: UUID, business_id: UUID, actor_id: Optional[UUID],
    ) -> dict:
        """Return to AI mode; un-mute AI participant."""
        call = self._get_call(call_id, business_id)
        self._assert_transition(call["takeover_state"], "ai")

        if call.get("mpc_uuid"):
            logger.info("release: would unmute AI participant on MPC %s — BLOCKED (creds absent)",
                        call["mpc_uuid"])

        updated = self._update_takeover_state(call_id, business_id, "ai", mode="ai")
        self._log_event(call_id, "takeover_release", actor_id, {
            "previous_state": call["takeover_state"],
        })
        return updated

    def get_events(self, call_id: UUID) -> list[dict]:
        """CONTRACT: travel_call_events carries no business_id column (see
        migration 0005) — tenancy lives on the parent travel_calls row. The
        caller MUST have resolved the call through a business-scoped lookup
        (CallService.get_call_scoped) and turned a None result into a 404
        BEFORE calling this, or the event log leaks across tenants."""
        return (
            self.db.table("travel_call_events").select("*")
            .eq("call_id", str(call_id))
            .order("created_at").execute().data or []
        )
