"""
Follow-up ladder (Phase 4 T6) — Day 1 / Day 3 / Day 7.

When a lead is created, three follow-ups are auto-scheduled from the
business's (or branch's) configured ladder. Agents work the queue via
GET /follow-ups; managers edit the ladder via PUT /follow-ups/rules.

DESIGN NOTE — `due` → `overdue` is a DERIVED status, not a stored one.
    Time passing must never require a database write. `derive_status()`
    computes `overdue` at read time from (stored status == 'due' AND
    due_at <= now). Every read path in this module and in the router runs
    rows through it, so the API is correct the instant a due_at passes,
    with no cron and no drift.
    `sweep_overdue()` exists as an OPTIONAL convenience that persists the
    same derivation for external SQL consumers (BI dashboards querying the
    table directly). It is not required for correctness and nothing in the
    API depends on it having run — it can never disagree with
    derive_status(), because it applies the exact same predicate.

PURITY BOUNDARY — the scheduling maths lives in module-level pure
functions that take `created_at` / `now` as arguments and do zero I/O:
    compute_ladder(created_at, rules)        -> list[dict]
    plan_rule_change(existing, rule, now)    -> list[dict]
    derive_status(status, due_at, now)       -> str
These are unit-testable without a database, which is how the acceptance
criteria for T6 are actually verified.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional
from uuid import UUID

from app.database import get_supabase_admin

logger = logging.getLogger(__name__)

# ── Vocabulary — must stay in sync with migration 0013's CHECK constraints ──
LADDER_DAYS: tuple[int, ...] = (1, 3, 7)
FOLLOW_UP_TYPES: frozenset[str] = frozenset(
    {"nudge", "summary", "personal_call", "price_alert"}
)
CHANNELS: frozenset[str] = frozenset(
    {"whatsapp", "sms", "email", "call", "in_app"}
)
STATUSES: frozenset[str] = frozenset({"due", "overdue", "in_progress", "done"})

#: Statuses that mean "an agent has already engaged with this row".
#: A ladder rule edit must NEVER rewrite these.
ACTIONED_STATUSES: frozenset[str] = frozenset({"in_progress", "done"})

HOURS_PER_LADDER_DAY = 24

#: Used when a business has configured no ladder of its own. Mirrors the
#: product spec: gentle nudge, then a written summary, then a human call.
DEFAULT_LADDER: tuple[dict[str, Any], ...] = (
    {"ladder_day": 1, "type": "nudge",         "channel": "whatsapp", "due_offset_hours": None},
    {"ladder_day": 3, "type": "summary",       "channel": "email",    "due_offset_hours": None},
    {"ladder_day": 7, "type": "personal_call", "channel": "call",     "due_offset_hours": None},
)


# ══════════════════════════════════════════════════════════════════════
# PURE FUNCTIONS — no I/O, no now(), fully unit-testable
# ══════════════════════════════════════════════════════════════════════

def _as_utc(value: Any) -> datetime:
    """Coerce a datetime or ISO-8601 string to an aware UTC datetime.

    Naive datetimes are assumed to be UTC (Supabase returns timestamptz as
    ISO strings with an offset, so naive input only shows up in tests).
    """
    if isinstance(value, str):
        raw = value.replace("Z", "+00:00")
        value = datetime.fromisoformat(raw)
    if not isinstance(value, datetime):
        raise TypeError(f"expected datetime or ISO string, got {type(value).__name__}")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _offset_hours(rule: dict) -> int:
    """Hours after lead creation that this rule's follow-up is due.

    NULL/absent `due_offset_hours` derives from the ladder day, which is the
    normal case: Day 1 = +24h, Day 3 = +72h, Day 7 = +168h.
    """
    explicit = rule.get("due_offset_hours")
    if explicit is not None:
        return int(explicit)
    return int(rule["ladder_day"]) * HOURS_PER_LADDER_DAY


def _validate_rule(rule: dict) -> None:
    day = rule.get("ladder_day")
    if day not in LADDER_DAYS:
        raise ValueError(f"ladder_day must be one of {LADDER_DAYS}, got {day!r}")
    if rule.get("type") not in FOLLOW_UP_TYPES:
        raise ValueError(
            f"type must be one of {sorted(FOLLOW_UP_TYPES)}, got {rule.get('type')!r}"
        )
    channel = rule.get("channel")
    if channel is not None and channel not in CHANNELS:
        raise ValueError(
            f"channel must be one of {sorted(CHANNELS)}, got {channel!r}"
        )
    offset = rule.get("due_offset_hours")
    if offset is not None and int(offset) < 0:
        raise ValueError(f"due_offset_hours must be >= 0, got {offset!r}")


def resolve_rules(rules: Iterable[dict]) -> list[dict]:
    """PURE. Collapse a mixed rule set into one active rule per ladder day.

    A branch-scoped rule (branch_id set) OVERRIDES the business-wide rule
    (branch_id NULL) for the same ladder_day. Inactive rules are dropped.
    Result is sorted by ladder_day so output order is deterministic.
    """
    winner: dict[int, dict] = {}
    for rule in rules:
        if not rule.get("is_active", True):
            continue
        _validate_rule(rule)
        day = int(rule["ladder_day"])
        current = winner.get(day)
        if current is None:
            winner[day] = rule
            continue
        # Branch-scoped beats business-wide. Same scope => last one wins,
        # which the partial unique indexes in 0013 make unreachable in practice.
        if rule.get("branch_id") is not None and current.get("branch_id") is None:
            winner[day] = rule
    return [winner[day] for day in sorted(winner)]


def compute_ladder(created_at: Any, rules: Optional[Iterable[dict]] = None) -> list[dict]:
    """PURE. The Day 1 / Day 3 / Day 7 schedule for one lead.

    Args:
        created_at: when the lead was created (datetime or ISO-8601 string).
        rules:      follow_up_rules rows. Empty/None => DEFAULT_LADDER.

    Returns:
        One dict per ladder rung, sorted by ladder_day, each carrying
        ladder_day, type, channel, due_at (aware UTC datetime), rule_id and
        status='due'. No database, no clock — same input, same output,
        forever.
    """
    base = _as_utc(created_at)
    resolved = resolve_rules(rules) if rules else list(DEFAULT_LADDER)
    if not resolved:
        resolved = list(DEFAULT_LADDER)

    schedule: list[dict] = []
    for rule in resolved:
        schedule.append({
            "ladder_day": int(rule["ladder_day"]),
            "type":       rule["type"],
            "channel":    rule.get("channel") or "whatsapp",
            "due_at":     base + timedelta(hours=_offset_hours(rule)),
            "rule_id":    rule.get("id"),
            "status":     "due",
        })
    return schedule


def derive_status(status: Optional[str], due_at: Any, now: Any) -> str:
    """PURE. The status a caller should SEE, given the clock.

    Only a still-open ('due') row can drift into 'overdue'. 'in_progress'
    and 'done' are terminal with respect to time. A row already persisted as
    'overdue' stays 'overdue' unless its due_at was pushed into the future,
    in which case it correctly reverts to 'due'.
    """
    if status in ACTIONED_STATUSES:
        return status  # type: ignore[return-value]
    return "overdue" if _as_utc(due_at) <= _as_utc(now) else "due"


def is_future_scheduled(row: dict, now: Any) -> bool:
    """PURE. True iff a ladder-rule edit is allowed to rewrite this row.

    "Future-scheduled" means: nobody has touched it (status is not
    in_progress/done) AND its due_at has not yet arrived. Anything already
    actioned, or already due/overdue, is HISTORY — a rule change must leave
    it exactly as it is, or the audit trail lies about what was sent when.
    """
    if row.get("status") in ACTIONED_STATUSES:
        return False
    return _as_utc(row["due_at"]) > _as_utc(now)


def plan_rule_change(existing: Iterable[dict], rule: dict, now: Any) -> list[dict]:
    """PURE. Which already-scheduled follow-ups a rule edit should rewrite.

    Args:
        existing: follow_ups rows for the affected scope. Each must carry
                  id, ladder_day, status, due_at and lead_created_at (the
                  parent lead's created_at — the anchor due_at is derived
                  from, so a changed offset re-anchors correctly instead of
                  drifting off the old due_at).
        rule:     the edited follow_up_rules row.
        now:      current time (injected — this function never calls now()).

    Returns:
        A list of {"id": ..., "patch": {...}} for FUTURE-scheduled rows of
        the same ladder_day only. Past and actioned rows are omitted
        entirely, so the caller cannot accidentally rewrite history.
    """
    _validate_rule(rule)
    day = int(rule["ladder_day"])
    hours = _offset_hours(rule)
    plans: list[dict] = []

    for row in existing:
        if int(row["ladder_day"]) != day:
            continue
        if not is_future_scheduled(row, now):
            continue
        patch: dict[str, Any] = {
            "type":    rule["type"],
            "channel": rule.get("channel") or "whatsapp",
            "due_at":  (_as_utc(row["lead_created_at"]) + timedelta(hours=hours)),
        }
        if rule.get("id") is not None:
            patch["rule_id"] = rule["id"]
        plans.append({"id": row["id"], "patch": patch})

    return plans


def _serialise(schedule_row: dict) -> dict:
    """Convert a pure-function row into a Supabase-insertable dict."""
    out = dict(schedule_row)
    if isinstance(out.get("due_at"), datetime):
        out["due_at"] = out["due_at"].isoformat()
    return out


# ══════════════════════════════════════════════════════════════════════
# SERVICE — I/O lives here and nowhere else
# ══════════════════════════════════════════════════════════════════════

class FollowUpService:
    """Service-role Supabase access for the follow-up ladder."""

    def __init__(self) -> None:
        self.db = get_supabase_admin()

    # ── rules ────────────────────────────────────────────────────────
    def list_rules(
        self, business_id: UUID, *, branch_id: Optional[UUID] = None,
        include_inactive: bool = False,
    ) -> list[dict]:
        """Business-wide rules plus this branch's overrides (unresolved)."""
        q = (
            self.db.table("follow_up_rules").select("*")
            .eq("business_id", str(business_id))
        )
        if not include_inactive:
            q = q.eq("is_active", True)
        rows = q.execute().data or []
        if branch_id is None:
            return [r for r in rows if r.get("branch_id") is None]
        return [
            r for r in rows
            if r.get("branch_id") is None or r.get("branch_id") == str(branch_id)
        ]

    def effective_ladder(
        self, business_id: UUID, *, branch_id: Optional[UUID] = None
    ) -> list[dict]:
        """The resolved ladder for a scope — falls back to DEFAULT_LADDER."""
        resolved = resolve_rules(self.list_rules(business_id, branch_id=branch_id))
        return resolved or [dict(r) for r in DEFAULT_LADDER]

    def upsert_rule(
        self, business_id: UUID, *, ladder_day: int, type: str,
        channel: str = "whatsapp", due_offset_hours: Optional[int] = None,
        is_active: bool = True, branch_id: Optional[UUID] = None,
        cascade_to_future: bool = True, now: Optional[datetime] = None,
    ) -> dict:
        """Create/replace one ladder rung, then re-plan FUTURE follow-ups.

        Returns {"rule": <row>, "rescheduled": <int>}. `rescheduled` counts
        only rows that plan_rule_change() deemed future-scheduled — past and
        in-progress/done follow-ups are provably untouched.
        """
        payload = {
            "business_id":      str(business_id),
            "branch_id":        str(branch_id) if branch_id else None,
            "ladder_day":       int(ladder_day),
            "type":             type,
            "channel":          channel,
            "due_offset_hours": due_offset_hours,
            "is_active":        is_active,
        }
        _validate_rule(payload)

        existing = (
            self.db.table("follow_up_rules").select("id")
            .eq("business_id", str(business_id))
            .eq("ladder_day", int(ladder_day))
        )
        existing = (
            existing.eq("branch_id", str(branch_id)) if branch_id
            else existing.is_("branch_id", "null")
        ).limit(1).execute().data or []

        if existing:
            rule_rows = (
                self.db.table("follow_up_rules").update(payload)
                .eq("id", existing[0]["id"]).execute().data or []
            )
        else:
            rule_rows = self.db.table("follow_up_rules").insert(payload).execute().data or []

        rule = rule_rows[0] if rule_rows else payload
        rescheduled = 0
        if cascade_to_future and is_active:
            rescheduled = self.apply_rule_to_future(
                business_id, rule, branch_id=branch_id, now=now
            )
        return {"rule": rule, "rescheduled": rescheduled}

    def apply_rule_to_future(
        self, business_id: UUID, rule: dict, *,
        branch_id: Optional[UUID] = None, now: Optional[datetime] = None,
    ) -> int:
        """Push an edited rule onto FUTURE-scheduled follow-ups only."""
        moment = _as_utc(now or datetime.now(timezone.utc))

        q = (
            self.db.table("follow_ups")
            .select("id, ladder_day, status, due_at, lead_id, travel_leads(created_at)")
            .eq("business_id", str(business_id))
            .eq("ladder_day", int(rule["ladder_day"]))
            .in_("status", ["due", "overdue"])
        )
        if branch_id is not None:
            q = q.eq("branch_id", str(branch_id))
        rows = q.execute().data or []

        existing: list[dict] = []
        for row in rows:
            lead = row.get("travel_leads") or {}
            lead_created = lead.get("created_at") if isinstance(lead, dict) else None
            existing.append({
                "id":              row["id"],
                "ladder_day":      row["ladder_day"],
                "status":          row["status"],
                "due_at":          row["due_at"],
                # Fall back to the row's own due_at anchor if the join is
                # unavailable — never guess a lead creation time.
                "lead_created_at": lead_created or row["due_at"],
            })

        plans = plan_rule_change(existing, rule, moment)
        for plan in plans:
            patch = dict(plan["patch"])
            if isinstance(patch.get("due_at"), datetime):
                patch["due_at"] = patch["due_at"].isoformat()
            self.db.table("follow_ups").update(patch).eq("id", plan["id"]).execute()
        return len(plans)

    # ── scheduling ───────────────────────────────────────────────────
    def schedule_for_lead(
        self, lead_id: UUID, business_id: UUID, *,
        branch_id: Optional[UUID] = None, created_at: Optional[Any] = None,
        assigned_to: Optional[UUID] = None,
    ) -> list[dict]:
        """Auto-schedule the ladder for a newly created lead.

        IDEMPOTENT — the unique index on (lead_id, ladder_day) plus the
        pre-read below mean calling this twice for the same lead still
        leaves exactly len(ladder) rows.

        Wire this into lead creation (services/travel/lead_service.py
        LeadService.ingest, right after the travel_leads insert).
        """
        if created_at is None:
            lead = (
                self.db.table("travel_leads").select("created_at, business_id")
                .eq("id", str(lead_id)).limit(1).execute().data or []
            )
            if not lead:
                return []
            created_at = lead[0]["created_at"]

        rules = self.list_rules(business_id, branch_id=branch_id)
        schedule = compute_ladder(created_at, rules)

        already = {
            r["ladder_day"] for r in (
                self.db.table("follow_ups").select("ladder_day")
                .eq("lead_id", str(lead_id)).execute().data or []
            )
        }

        payload = [
            {
                **_serialise(row),
                "business_id": str(business_id),
                "lead_id":     str(lead_id),
                "branch_id":   str(branch_id) if branch_id else None,
                "assigned_to": str(assigned_to) if assigned_to else None,
            }
            for row in schedule if row["ladder_day"] not in already
        ]
        if not payload:
            return []
        return self.db.table("follow_ups").insert(payload).execute().data or []

    # ── reads / writes ───────────────────────────────────────────────
    def list(
        self, business_id: UUID, *, status: Optional[str] = None,
        lead_id: Optional[UUID] = None, branch_id: Optional[UUID] = None,
        assigned_to: Optional[UUID] = None, limit: int = 100,
        now: Optional[datetime] = None,
    ) -> list[dict]:
        """List follow-ups with `status` DERIVED (see module docstring).

        The `status` filter is applied AFTER derivation, so
        `?status=overdue` returns rows whose due_at has merely passed —
        no sweep job required.
        """
        moment = _as_utc(now or datetime.now(timezone.utc))
        q = (
            self.db.table("follow_ups").select("*")
            .eq("business_id", str(business_id))
        )
        if lead_id is not None:
            q = q.eq("lead_id", str(lead_id))
        if branch_id is not None:
            q = q.eq("branch_id", str(branch_id))
        if assigned_to is not None:
            q = q.eq("assigned_to", str(assigned_to))
        # 'due'/'overdue' share one stored state, so both must be fetched
        # before derivation can tell them apart.
        if status in ("in_progress", "done"):
            q = q.eq("status", status)
        elif status in ("due", "overdue"):
            q = q.in_("status", ["due", "overdue"])

        rows = q.order("due_at").limit(max(limit, 1) * 2).execute().data or []

        out: list[dict] = []
        for row in rows:
            row = dict(row)
            row["stored_status"] = row.get("status")
            row["status"] = derive_status(row.get("status"), row["due_at"], moment)
            if status and row["status"] != status:
                continue
            out.append(row)
        return out[:limit]

    def get(
        self, follow_up_id: UUID, business_id: UUID, *,
        assigned_to: Optional[UUID] = None, now: Optional[datetime] = None,
    ) -> Optional[dict]:
        """Out-of-scope reads return None so the router can 404, never 403."""
        moment = _as_utc(now or datetime.now(timezone.utc))
        rows = (
            self.db.table("follow_ups").select("*")
            .eq("id", str(follow_up_id))
            .eq("business_id", str(business_id))
            .limit(1).execute().data or []
        )
        if not rows:
            return None
        row = dict(rows[0])
        if assigned_to is not None and row.get("assigned_to") != str(assigned_to):
            return None
        row["stored_status"] = row.get("status")
        row["status"] = derive_status(row.get("status"), row["due_at"], moment)
        return row

    def update(
        self, follow_up_id: UUID, business_id: UUID, patch: dict, *,
        assigned_to: Optional[UUID] = None, now: Optional[datetime] = None,
    ) -> Optional[dict]:
        """Patch status / assigned_to / channel / due_at on one follow-up."""
        moment = _as_utc(now or datetime.now(timezone.utc))
        current = self.get(follow_up_id, business_id, assigned_to=assigned_to, now=moment)
        if current is None:
            return None

        clean = {k: v for k, v in patch.items() if v is not None}
        if not clean:
            return current

        if "status" in clean:
            if clean["status"] not in STATUSES:
                raise ValueError(f"status must be one of {sorted(STATUSES)}")
            if clean["status"] == "done" and not clean.get("completed_at"):
                clean["completed_at"] = moment.isoformat()
        if "channel" in clean and clean["channel"] not in CHANNELS:
            raise ValueError(f"channel must be one of {sorted(CHANNELS)}")
        if isinstance(clean.get("due_at"), datetime):
            clean["due_at"] = _as_utc(clean["due_at"]).isoformat()
        if isinstance(clean.get("assigned_to"), UUID):
            clean["assigned_to"] = str(clean["assigned_to"])

        rows = (
            self.db.table("follow_ups").update(clean)
            .eq("id", str(follow_up_id))
            .eq("business_id", str(business_id))
            .execute().data or []
        )
        if not rows:
            return None
        row = dict(rows[0])
        row["stored_status"] = row.get("status")
        row["status"] = derive_status(row.get("status"), row["due_at"], moment)
        return row

    def sweep_overdue(
        self, business_id: Optional[UUID] = None, *, now: Optional[datetime] = None
    ) -> int:
        """OPTIONAL. Persist the derived 'overdue' state for SQL consumers.

        Not required for API correctness — list()/get() already derive it.
        This exists so BI tools reading the table directly see the same
        thing the API does. Applies the identical predicate as
        derive_status(), so it can never disagree with the API.
        """
        moment = _as_utc(now or datetime.now(timezone.utc))
        q = (
            self.db.table("follow_ups").select("id")
            .eq("status", "due").lte("due_at", moment.isoformat())
        )
        if business_id is not None:
            q = q.eq("business_id", str(business_id))
        ids = [r["id"] for r in (q.execute().data or [])]
        for row_id in ids:
            self.db.table("follow_ups").update({"status": "overdue"}).eq("id", row_id).execute()
        return len(ids)
