"""
WhatsApp provider abstraction (Phase 4 T3).

WHY AN ABC AT ALL — the provider decision is reversible by design
------------------------------------------------------------------
We ship direct **Meta Cloud API** (see meta_cloud.py's header for the full
BSP-vs-Meta tradeoff). The realistic reasons to switch later are commercial and
operational, not technical: an Indian BSP (Gupshup / Interakt) gives faster
template hand-holding, Embedded-Signup concierge for non-technical agencies, and
local invoicing — at the cost of a per-message markup.

So the seam is drawn where a swap is a ONE-CLASS change:
  * every caller depends on this ABC, never on a concrete provider;
  * the only construction site is `get_whatsapp_provider()` in __init__.py;
  * the outbox row shape (provider-agnostic columns + an opaque `payload` JSONB)
    is identical regardless of who transmits it;
  * `provider` is a VARCHAR column, not an enum, so adding 'gupshup' is a code
    change with zero migration.
Adding a BSP = write `gupshup.py` subclassing WhatsAppProvider + one branch in
the factory. Nothing else in the codebase moves.

THE 24-HOUR SESSION WINDOW IS ENFORCED HERE, NOT IN SUBCLASSES
---------------------------------------------------------------
WhatsApp only permits free-form ("session") messages within 24 hours of the
customer's most recent inbound message. Outside that window the ONLY legal
send is a pre-approved template. Meta rejects violations server-side, but we
must not rely on that: a rejection is a billable round-trip, a user-visible
failure, and — repeated — a quality-rating hit against the number.

`__init_subclass__` therefore wraps every subclass's `send_freeform` with a
mandatory pre-flight `check_session_window()` call. A provider author CANNOT
forget the check and CANNOT opt out: refusing to route through the guard would
require deleting the method. The public contract stays exactly three methods.
"""
from __future__ import annotations

import inspect
import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any, Optional

logger = logging.getLogger(__name__)

# WhatsApp's customer-service window. Not configurable — it is Meta policy.
SESSION_WINDOW_HOURS = 24

OUTBOX_TABLE = "whatsapp_outbox"


# ── Errors ──────────────────────────────────────────────────────────────────
class WhatsAppError(RuntimeError):
    """Base class for every failure raised out of this package."""


class SessionWindowClosed(WhatsAppError):
    """
    Raised when free-form text is attempted outside the 24-hour window.

    Callers must recover by sending an approved template instead — the router
    surfaces this as HTTP 409 with that instruction, never as a 500.
    """

    def __init__(self, to: str, last_inbound: Optional[datetime] = None) -> None:
        self.to = to
        self.last_inbound = last_inbound
        when = last_inbound.isoformat() if last_inbound else "never"
        super().__init__(
            f"WhatsApp 24h session window is closed for {to} "
            f"(last inbound: {when}). Free-form text is not permitted — "
            f"send an approved template instead."
        )


class WhatsAppSendError(WhatsAppError):
    """Provider rejected or failed the send. `outbox_id` points at the row."""

    def __init__(self, message: str, *, outbox_id: Optional[str] = None) -> None:
        self.outbox_id = outbox_id
        super().__init__(message)


# ── Recipient normalisation ─────────────────────────────────────────────────
# E.164: leading '+', country code starting 1-9, 8-15 digits total.
_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")
_STRIP_RE = re.compile(r"[\s\-().]")


def normalize_msisdn(to: str) -> str:
    """
    Normalise a phone number to E.164 (`+919876543210`).

    India-focused product: a bare 10-digit number beginning 6/7/8/9 is a
    domestic mobile and is promoted to +91. Everything else must already carry
    its country code — we never guess beyond India.

    Raises ValueError on anything that cannot be a WhatsApp recipient. Doing
    this once, here, means the outbox never accumulates two spellings of the
    same customer (which would silently break session-window lookups).
    """
    raw = _STRIP_RE.sub("", (to or "").strip())
    if raw.startswith("00"):
        raw = "+" + raw[2:]
    if not raw.startswith("+"):
        if len(raw) == 10 and raw[0] in "6789":
            raw = "+91" + raw
        else:
            raw = "+" + raw
    if not _E164_RE.match(raw):
        raise ValueError(f"Not a valid E.164 WhatsApp recipient: {to!r}")
    return raw


# ── Session-window state ────────────────────────────────────────────────────
# The window opens on the CUSTOMER's inbound message. The authoritative source
# is the whatsapp_sessions table (migration 0023), so the check is consistent
# across multiple uvicorn workers.
#
# FAIL-CLOSED IS DELIBERATE: an unknown recipient has no recorded inbound, so
# the window reads CLOSED and free-form is refused. Being wrong in that
# direction costs one unnecessary template; being wrong the other way costs a
# policy violation against the business's WhatsApp number.
#
# TENANT-KEYED (Phase 5 P1 isolation audit): the lookup is (business_id, msisdn),
# never the msisdn alone. The 24-hour window is a property of ONE business's
# conversation with a customer — if agency A's customer messages A, that must
# not authorise agency B to send that same number free-form text on B's own
# WABA. Keying by number alone would make one tenant's inbound traffic unlock
# another's outbound policy gate. business_id is therefore part of the
# key, and an unknown/omitted business_id simply reads as a distinct namespace
# that has never seen an inbound — i.e. closed, per the fail-closed rule above.


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _get_db() -> Any:
    """Lazy-load service-role Supabase client for session state lookups."""
    from app.database import get_supabase_admin
    return get_supabase_admin()


def record_inbound(
    to: str,
    at: Optional[datetime] = None,
    *,
    business_id: Optional[str] = None,
) -> datetime:
    """Record a customer's inbound message — this is what opens the window.

    `business_id` scopes the window to the tenant whose WhatsApp number
    received the message. The inbound-webhook handler (a separate task) MUST
    pass it; omitting it records into an unowned namespace that no provider
    reads, which fails closed rather than opening the window for everyone.
    """
    ts = at or _utcnow()
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    to_normalized = normalize_msisdn(to)
    bus_id = str(business_id or "")
    db = _get_db()

    db.table("whatsapp_sessions").upsert({
        "business_id": bus_id,
        "to_number": to_normalized,
        "last_inbound_at": ts.isoformat(),
    }).eq("business_id", bus_id).eq("to_number", to_normalized).execute()

    return ts


def last_inbound_at(to: str, *, business_id: Optional[str] = None) -> Optional[datetime]:
    """Query the last inbound message timestamp from persistent storage."""
    to_normalized = normalize_msisdn(to)
    bus_id = str(business_id or "")
    db = _get_db()

    try:
        rows = db.table("whatsapp_sessions").select("last_inbound_at").eq(
            "business_id", bus_id
        ).eq("to_number", to_normalized).limit(1).execute().data
        if rows:
            ts_str = rows[0]["last_inbound_at"]
            return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except Exception:
        logger.exception("Failed to query last_inbound_at for business=%s to=%s", bus_id, to)

    return None


def session_window_open(
    to: str, *, now: Optional[datetime] = None, business_id: Optional[str] = None
) -> bool:
    """True iff THIS BUSINESS's customer messaged it within SESSION_WINDOW_HOURS."""
    last = last_inbound_at(to, business_id=business_id)
    if last is None:
        return False
    return (now or _utcnow()) - last < timedelta(hours=SESSION_WINDOW_HOURS)


def clear_inbound_registry() -> None:
    """Test helper — resets window state by deleting all rows."""
    db = _get_db()
    try:
        db.table("whatsapp_sessions").delete().neq("id", "").execute()
    except Exception:
        logger.exception("Failed to clear inbound registry")


async def _maybe_await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


# ── The provider contract ───────────────────────────────────────────────────
class WhatsAppProvider(ABC):
    """
    Three methods, one rule.

        send_template(to, template_name, language, components) -> dict
        send_freeform(to, text)                                -> dict
        check_session_window(to)                               -> bool

    Every send returns the persisted `whatsapp_outbox` row (a dict), never a
    raw provider response — so callers, tests and the dashboard all read one
    provider-independent shape.

    `send_freeform` is auto-wrapped (see __init_subclass__) so that
    `check_session_window` runs first and SessionWindowClosed is raised before
    any network call. Subclasses implement the send; they do not implement the
    policy.
    """

    #: Written verbatim into whatsapp_outbox.provider (VARCHAR(20)).
    name: str = "base"

    def __init__(self, business_id: str, *, db: Any = None) -> None:
        self.business_id = str(business_id)
        self._db = db  # injectable for tests; resolved lazily otherwise

    # -- session-window enforcement, installed on every subclass --------------
    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        fn = cls.__dict__.get("send_freeform")
        if fn is None or getattr(fn, "__wa_window_guarded__", False):
            return  # inherited (already guarded) or not overridden here

        @wraps(fn)
        async def _guarded(self: "WhatsAppProvider", to: str, text: str,
                           *args: Any, **kw: Any) -> dict:
            if not await _maybe_await(self.check_session_window(to)):
                raise SessionWindowClosed(
                    to, last_inbound_at(to, business_id=self.business_id)
                )
            return await _maybe_await(fn(self, to, text, *args, **kw))

        _guarded.__wa_window_guarded__ = True  # type: ignore[attr-defined]
        cls.send_freeform = _guarded  # type: ignore[assignment]

    # -- the contract ---------------------------------------------------------
    @abstractmethod
    async def send_template(
        self,
        to: str,
        template_name: str,
        language: str = "en",
        components: Optional[list[dict[str, Any]]] = None,
    ) -> dict:
        """
        Send a pre-approved Meta message template.

        The only send permitted OUTSIDE the 24-hour window, and therefore the
        only way to initiate a conversation. `components` is Meta's component
        array (header/body/button parameter substitutions), passed through
        unchanged so template variables stay provider-native.
        """

    @abstractmethod
    async def send_freeform(self, to: str, text: str) -> dict:
        """
        Send plain session text.

        LEGAL ONLY INSIDE THE 24-HOUR WINDOW. Implementations must not
        re-check the window — the ABC has already refused the call if it was
        closed. Outside it, callers get SessionWindowClosed and must switch to
        send_template().
        """

    @abstractmethod
    async def check_session_window(self, to: str) -> bool:
        """True iff free-form text to `to` is currently permitted."""

    # -- shared outbox plumbing ----------------------------------------------
    @property
    def db(self) -> Any:
        """Service-role Supabase client, resolved lazily so provider
        construction (and unit tests) never require a live database."""
        if self._db is None:
            from app.database import get_supabase_admin
            self._db = get_supabase_admin()
        return self._db

    def _outbox_insert(
        self,
        *,
        to_number: str,
        message_type: str,
        payload: dict[str, Any],
        status: str,
        language: str = "en",
        template_name: Optional[str] = None,
        provider_message_id: Optional[str] = None,
        error: Optional[str] = None,
        sent_at: Optional[str] = None,
    ) -> dict:
        row = {
            "business_id":         self.business_id,
            "to_number":           to_number,
            "message_type":        message_type,
            "template_name":       template_name,
            "language":            language,
            "payload":             payload,
            "status":              status,
            "provider":            self.name,
            "provider_message_id": provider_message_id,
            "error":               error,
            "sent_at":             sent_at,
        }
        inserted = self.db.table(OUTBOX_TABLE).insert(row).execute().data
        return inserted[0] if inserted else row

    def _outbox_update(self, outbox_id: str, patch: dict[str, Any]) -> dict:
        # business_id predicate is not optional even though `outbox_id` came
        # from this provider's own insert: a provider instance is bound to one
        # tenant, so its writes must be structurally unable to touch another.
        updated = (
            self.db.table(OUTBOX_TABLE).update(patch)
            .eq("id", outbox_id).eq("business_id", self.business_id)
            .execute().data
        )
        return updated[0] if updated else {"id": outbox_id, **patch}
