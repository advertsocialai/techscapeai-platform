"""
Right-to-erasure service (COMPLIANCE_CHECKLIST.md D-3, DPDP-shaped).

ANONYMIZE, NEVER DELETE
    Personal fields are nulled / replaced with placeholders; rows stay.
    Money rows are NEVER deleted or re-valued: payment_links amounts,
    booking totals/deposits/balances and anything an invoice was computed
    from must survive erasure, or the books stop reconciling (invoice /
    audit integrity — same reasoning as the frozen-invoice trigger in
    migration 0019). What gets removed is the person, not the transaction.

WHAT COUNTS AS PERSONAL DATA HERE — honest enumeration against the real
schema (database/travel_schema.sql + migrations 0003/0005/0010/0011/0013/
0021). Tables touched, in erase order:

  1. travel_leads (customer_id = X)      — phone, raw_message (verbatim
     customer words, NOT NULL → placeholder), intent, metadata, embedding
     (embedding of the raw message = derived personal data). Funnel columns
     (source, score, qualification, status, budget, pax) are kept for stats.
  2. travel_calls (via those lead ids)   — recording_url (the caller's
     voice IS personal data), summary (LLM summary of what they said).
     Duration/status/timestamps kept for ops stats.
  3. travel_transcripts (via call ids)   — text_original (NOT NULL →
     placeholder), text_translated, embedding. Sentiment JSON kept
     (derived score, no identity once text is gone).
  4. travel_itineraries (customer_id)    — intent (customer's own words),
     raw_response (LLM output that quotes them). days/costs kept — trip
     content, not identity. CAVEAT noted for Gowtham: LLM-generated `days`
     COULD embed a traveller name; scrubbing inside that JSON is a
     wording/policy call, flagged below, not silently guessed.
  5. travel_in_trip_incidents (customer_id) — customer_message (NOT NULL →
     placeholder), agent_response (written about the customer), metadata.
  6. travel_bookings (customer_id)       — metadata (free-form JSONB that
     may carry traveller names/passport details). booking_ref, dates, pax
     and ALL money columns kept (see banner). coordinator_name/phone are
     presumed AGENCY STAFF, not the traveller — left intact (Gowtham
     decision if that presumption is wrong).
  7. follow_ups (via lead ids)           — metadata (message context may
     quote the customer). Schedule/status columns kept.
  8. whatsapp_outbox (to_number = profile.phone) — to_number (E.164 =
     personal data) → placeholder, payload (verbatim message body) → {}.
     This table has NO customer_id/lead_id column (migration 0011); phone
     match is the only linkage, so rows are only reachable while the
     profile still holds the phone — which is why this runs BEFORE the
     profile is scrubbed.
  9. payment_links (customer_id)         — customer_id → NULL (detach; the
     column is already ON DELETE SET NULL by design, migration 0021: "must
     not destroy the record of money"). Amount/status/gateway ids kept.
 10. travel_customer_profiles (the row)  — full_name/email/phone/notes/
     last_intent → NULL, preferences/family_profile → {}, past_trips → [].
     Row kept (FK anchor + proof the erasure happened).

DELIBERATELY NOT TOUCHED (each a conscious call, not an oversight):
  - activity_log — append-only audit trail (migration 0014); its metadata
    MAY reference the customer. Scrubbing an audit log is a policy
    decision for Gowtham (DPDP vs audit-retention tension), not code's.
  - ts_business_contacts (profile.contact_id) — techscape/* surface, out
    of scope for travel-side code per gogaga-backend skill.
  - usage/billing tables (0016/0019) — tenant-level aggregates, no
    per-customer personal data.

EDGE CASES → 409 (Gowtham decisions, refused rather than guessed):
  - erase while a booking is confirmed/in_progress: the trip is still
    being operated; erasing contact data mid-trip could strand the
    traveller. Policy call (erase after completion? partial erase?).
  - erase while a call is live: transcript rows are still being written;
    a half-scrubbed call is worse than a queued erasure.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.database import get_supabase_admin
from app.services.travel import activity_log

logger = logging.getLogger(__name__)

#: Placeholder for NOT NULL text columns that held personal content.
ERASED_TEXT = "[erased per DPDP request]"
#: Placeholder for NOT NULL phone columns (whatsapp_outbox.to_number,
#: VARCHAR(20)) — syntactically phone-shaped, obviously not a real number.
ERASED_PHONE = "+910000000000"


class ActiveRecordConflict(Exception):
    """Raised when erasure is blocked by in-flight business state (→ 409)."""

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


def _ids(rows: list[dict]) -> list[str]:
    return [r["id"] for r in rows or []]


def erase_customer(
    customer_id: str,
    business_id: str,
    *,
    actor_id: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Anonymize every personal-data row for one customer profile.

    Returns a summary dict {"tables": {table: rows_touched}, ...} on
    success, or None when no profile with that id exists in this business
    (caller turns that into 404 — never 403, don't leak existence).
    Raises ActiveRecordConflict for the 409 edge cases in the module
    docstring.
    """
    db = get_supabase_admin()

    profile_rows = (
        db.table("travel_customer_profiles").select("*")
        .eq("id", customer_id).eq("business_id", business_id)
        .limit(1).execute().data
    )
    if not profile_rows:
        return None
    profile = profile_rows[0]

    touched: dict[str, int] = {}

    # ── Edge-case guards (409 — Gowtham decisions, see module docstring) ──
    active_bookings = (
        db.table("travel_bookings").select("id")
        .eq("customer_id", customer_id).eq("business_id", business_id)
        .in_("status", ["confirmed", "in_progress"])
        .execute().data
    )
    if active_bookings:
        raise ActiveRecordConflict(
            "Customer has a confirmed or in-progress booking. Erasing personal "
            "data mid-trip is a policy decision (BLK: Gowtham) — complete or "
            "cancel the booking first, then retry."
        )

    lead_rows = (
        db.table("travel_leads").select("id")
        .eq("customer_id", customer_id).eq("business_id", business_id)
        .execute().data
    )
    lead_ids = _ids(lead_rows)

    call_ids: list[str] = []
    if lead_ids:
        call_rows = (
            db.table("travel_calls").select("id,status")
            .in_("lead_id", lead_ids).eq("business_id", business_id)
            .execute().data
        )
        if any(c.get("status") == "active" for c in call_rows or []):
            raise ActiveRecordConflict(
                "A call for this customer is still live; transcripts are still "
                "being written. Retry after the call ends."
            )
        call_ids = _ids(call_rows)

    # ── 8. whatsapp_outbox FIRST — reachable only via the profile's phone ──
    if profile.get("phone"):
        rows = (
            db.table("whatsapp_outbox")
            .update({"to_number": ERASED_PHONE, "payload": {}})
            .eq("business_id", business_id)
            .eq("to_number", profile["phone"])
            .execute().data
        )
        touched["whatsapp_outbox"] = len(rows or [])

    # ── 1. travel_leads ──
    if lead_ids:
        rows = (
            db.table("travel_leads")
            .update({
                "phone": None,
                "raw_message": ERASED_TEXT,   # NOT NULL
                "intent": None,
                "metadata": {},
                "embedding": None,
            })
            .in_("id", lead_ids).eq("business_id", business_id)
            .execute().data
        )
        touched["travel_leads"] = len(rows or [])

    # ── 2. travel_calls / 3. travel_transcripts ──
    if call_ids:
        rows = (
            db.table("travel_calls")
            .update({"recording_url": None, "summary": None})
            .in_("id", call_ids)
            .execute().data
        )
        touched["travel_calls"] = len(rows or [])

        rows = (
            db.table("travel_transcripts")
            .update({
                "text_original": ERASED_TEXT,   # NOT NULL
                "text_translated": None,
                "embedding": None,
            })
            .in_("call_id", call_ids)
            .execute().data
        )
        touched["travel_transcripts"] = len(rows or [])

    # ── 4. travel_itineraries ──
    rows = (
        db.table("travel_itineraries")
        .update({"intent": None, "raw_response": {}})
        .eq("customer_id", customer_id).eq("business_id", business_id)
        .execute().data
    )
    touched["travel_itineraries"] = len(rows or [])

    # ── 5. travel_in_trip_incidents ──
    rows = (
        db.table("travel_in_trip_incidents")
        .update({
            "customer_message": ERASED_TEXT,   # NOT NULL
            "agent_response": None,
            "metadata": {},
        })
        .eq("customer_id", customer_id).eq("business_id", business_id)
        .execute().data
    )
    touched["travel_in_trip_incidents"] = len(rows or [])

    # ── 6. travel_bookings (non-active only — guard above) ──
    rows = (
        db.table("travel_bookings")
        .update({"metadata": {}})
        .eq("customer_id", customer_id).eq("business_id", business_id)
        .execute().data
    )
    touched["travel_bookings"] = len(rows or [])

    # ── 7. follow_ups ──
    if lead_ids:
        rows = (
            db.table("follow_ups")
            .update({"metadata": {}})
            .in_("lead_id", lead_ids).eq("business_id", business_id)
            .execute().data
        )
        touched["follow_ups"] = len(rows or [])

    # ── 9. payment_links — detach only, money rows are never deleted ──
    rows = (
        db.table("payment_links")
        .update({"customer_id": None})
        .eq("customer_id", customer_id).eq("business_id", business_id)
        .execute().data
    )
    touched["payment_links"] = len(rows or [])

    # ── 10. the profile itself, last ──
    rows = (
        db.table("travel_customer_profiles")
        .update({
            "full_name": None,
            "email": None,       # UNIQUE(business_id,email) — NULLs don't collide
            "phone": None,
            "notes": None,
            "last_intent": None,
            "preferences": {},
            "past_trips": [],
            "family_profile": {},
        })
        .eq("id", customer_id).eq("business_id", business_id)
        .execute().data
    )
    touched["travel_customer_profiles"] = len(rows or [])

    # One audit row proving the erasure happened. entity_type "customer" is
    # not in migration 0014's CHECK vocabulary; activity_log.record() coerces
    # it to 'other' and preserves the raw value in metadata by design.
    activity_log.record(
        actor_id=actor_id,
        action="customer.personal_data.erased",
        entity_type="customer",
        entity_id=customer_id,
        business_id=business_id,
        metadata={"tables_touched": touched},
    )

    logger.info(
        "erasure complete: customer=%s business=%s tables=%s",
        customer_id, business_id, touched,
    )
    return {"customer_id": customer_id, "tables": touched}
