"""
Traveller-facing endpoints (the customer-app "trip" surface).

    POST /me/auth/request-otp   → send a login code to a known traveller
    POST /me/auth/verify-otp    → exchange the code for a traveller token
    GET  /me/trip               → the traveller's own booking
    GET  /me/payments           → payment links raised against that booking
    GET  /me/messages           → what the agency has sent them

WHY THIS EXISTS
---------------
customer-app's trip screens were built against `travellerApi.ts`, which returned
fixtures because none of these endpoints existed (B-FE7-03). The screens were
correct; there was simply nothing behind them.

A TRAVELLER IS NOT A ts_users ROW
---------------------------------
They are a `travel_customer_profiles` row: no password, no role, no branch. The
tempting shortcut — give travellers a ts_users row with role='customer' — is
specifically wrong, because it puts customer records one join away from every
Team screen, access matrix and role check in the product. See B-FE7-02.

So the login is OTP-only (they have no password to present) and the token is a
separate family that agency endpoints refuse outright. `core/deps.py`
get_current_user rejects any token whose `type` != "access", and
get_current_traveller requires "traveller_access" — neither can be used where
the other belongs, and that holds without a single change to agency code.

SCOPING RULE, APPLIED TO EVERY QUERY BELOW
------------------------------------------
Filter by BOTH `customer_id` AND `business_id`, always, both taken from the
token and never from the request. business_id alone is the AGENCY's scope —
using it by itself would show a traveller every other customer's booking in the
same agency, which is the exact leak this file exists to prevent.

No path parameter anywhere identifies a resource. There is deliberately no
`GET /me/trip/{id}`: with no id in the URL there is no id to tamper with, so
the whole class of "change the number, read someone else's booking" bug cannot
be expressed against this surface.

WHAT IS HONESTLY NOT HERE
-------------------------
💬 There is no `POST /me/messages`. The WhatsApp integration is outbound-only —
no traveller→agency inbound channel exists on any provider we have wired. An
endpoint that accepted a message and dropped it would be worse than its absence:
a customer who believes they reported a visa problem, and did not, is worse off
than one who was told the channel is unavailable. customer-app already renders
that composer disabled with the reason attached; this file keeps that honest.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, EmailStr, Field

from app.core.deps import get_current_traveller
from app.core.public_rate_limit import enforce as rate_limit
from app.core.security import TRAVELLER_TOKEN_TTL_MIN, issue_traveller_token
from app.database import get_supabase_admin

logger = logging.getLogger(__name__)
router = APIRouter()


# ── DTOs ──────────────────────────────────────────────────────────────────
class RequestOtpIn(BaseModel):
    email: EmailStr


class VerifyOtpIn(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=10)


class TravellerTokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_min: int


class TripDay(BaseModel):
    day: int
    title: str
    detail: str


class TripOut(BaseModel):
    booking_ref: str
    destination: Optional[str] = None
    status: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    pax: int = 1
    agency_name: Optional[str] = None
    agent_name: Optional[str] = None
    itinerary: list[TripDay] = []
    # Major units, as a string, paired with its currency — never a bare number.
    # The dashboard's money rule applies just as hard on the customer's own
    # booking, which is the worst possible place for an ambiguous figure.
    total_amount: str
    currency: str
    amount_paid: str
    visa_state: str


class TravellerPaymentOut(BaseModel):
    id: str
    description: str
    amount: str
    currency: str
    status: str
    due_at: Optional[str] = None
    # A `stub://` URL is NOT openable. It is returned as-is rather than hidden
    # so the client can render it inert; the payments gateway runs in stub mode
    # without Razorpay credentials, and a dead "Pay now" button reads to a
    # customer as a broken booking.
    pay_url: Optional[str] = None


class TravellerMessageOut(BaseModel):
    id: str
    from_: str = Field(serialization_alias="from")
    text: str
    at: str


# ── Helpers ───────────────────────────────────────────────────────────────
def _profile_by_email(db, email: str) -> Optional[dict[str, Any]]:
    """
    Resolve an email to ONE customer profile.

    travel_customer_profiles is UNIQUE(business_id, email), NOT unique on email
    — so the same person booking with two agencies has two profiles, and a
    lookup by email alone can match both. The first version of this took
    `.limit(1)`, which meant an arbitrary agency won: the traveller would be
    shown a real booking of their own, but potentially from the wrong agency,
    varying between logins.

    Not a cross-person leak (both rows are the same human), but wrong, and
    non-deterministically wrong, which is worse to diagnose.

    Resolution: oldest profile wins, so a given address always lands on the same
    agency instead of flipping. Ambiguity is logged rather than hidden, because
    the real fix is scoping the login to one agency — which needs a product
    decision about how customer-app learns which agency it is serving
    (subdomain, branding, deep link). Logged as B-FE7-08.
    """
    res = (
        db.table("travel_customer_profiles")
        .select("id, business_id, full_name, email, phone, created_at")
        .eq("email", email)
        .order("created_at", desc=False)
        .execute()
    )
    rows = res.data or []
    if not rows:
        return None
    if len(rows) > 1:
        logger.warning(
            "traveller email %s matches %d profiles across businesses %s — "
            "resolving to the oldest (B-FE7-08)",
            email,
            len(rows),
            [r.get("business_id") for r in rows],
        )
    return rows[0]


def _current_booking(db, customer_id: str, business_id: str) -> Optional[dict[str, Any]]:
    """
    The traveller's most recent non-cancelled booking.

    Both filters are load-bearing. Dropping business_id would let a stale token
    from a deleted tenant resolve against a recycled customer row.
    """
    res = (
        db.table("travel_bookings")
        .select("*")
        .eq("customer_id", customer_id)
        .eq("business_id", business_id)
        .neq("status", "cancelled")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    return rows[0] if rows else None


# ── Auth ──────────────────────────────────────────────────────────────────
@router.post("/auth/request-otp", status_code=status.HTTP_202_ACCEPTED)
def request_otp(payload: RequestOtpIn, request: Request) -> dict[str, Any]:
    """
    ALWAYS returns 202, whether or not the address belongs to a traveller.

    RISK-1: this endpoint sends email and is reachable by anyone — added with
    NO rate limit on 2026-08-09 and fixed the same day. 6/5min per IP,
    3/5min per target inbox.

    This is an enumeration guard, not sloppiness: a 404 here would turn the
    endpoint into an oracle for "is this person a customer of this agency?",
    which is exactly the kind of question a travel agency's customer list should
    not answer to anonymous callers.
    """
    # Imported here rather than at module scope: these are the techscape auth
    # router's private OTP helpers, and importing them at import-time creates a
    # cycle (that router imports from core, which this module also touches).
    from app.routers.techscape.auth import _issue_otp

    rate_limit(request, bucket="trav-otp-send", limit=6, window_sec=300, email=str(payload.email))

    db = get_supabase_admin()
    profile = _profile_by_email(db, str(payload.email))

    if profile:
        code = _issue_otp(str(payload.email))
        # The code is NEVER returned in this response, in any environment.
        # techscape's /auth/otp/send leaks it under DEBUG for developer
        # convenience; this endpoint is reachable by anyone who knows a
        # customer's address, so it does not get that affordance.
        logger.info("traveller OTP issued for customer=%s", profile["id"])
        if not code:  # pragma: no cover - defensive
            logger.warning("OTP issue returned empty for %s", profile["id"])
    else:
        logger.info("traveller OTP requested for unknown address — no-op")

    return {"ok": True, "message": "If that address is on a booking, a code is on its way."}


@router.post("/auth/verify-otp", response_model=TravellerTokenOut)
def verify_otp(payload: VerifyOtpIn, request: Request) -> TravellerTokenOut:
    from app.routers.techscape.auth import _verify_otp

    # OTP brute force: 10 guesses per 5 min per inbox ends the 1e6-space attack.
    rate_limit(request, bucket="trav-otp-verify", limit=10, window_sec=300, email=str(payload.email))
    from app.core.security import TRAVELLER_TOKEN_TTL_MIN

    if not _verify_otp(str(payload.email), payload.code):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired code")

    db = get_supabase_admin()
    profile = _profile_by_email(db, str(payload.email))
    if not profile:
        # A valid code for an address with no profile: treat as failure with
        # the SAME message, so a correct guess still reveals nothing.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired code")

    token = issue_traveller_token(
        customer_id=str(profile["id"]), business_id=str(profile["business_id"])
    )
    return TravellerTokenOut(access_token=token, expires_in_min=TRAVELLER_TOKEN_TTL_MIN)


# ── Trip ──────────────────────────────────────────────────────────────────
@router.get("/trip", response_model=TripOut)
def my_trip(traveller: dict = Depends(get_current_traveller)) -> TripOut:
    db = get_supabase_admin()
    booking = _current_booking(db, traveller["customer_id"], traveller["business_id"])
    if not booking:
        # 404 rather than an empty object: "you have no booking" and "your
        # booking has no data" are different states, and the client renders
        # different screens for them.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No active booking found")

    agency_name = None
    biz = (
        db.table("ts_businesses")
        .select("name")
        .eq("id", traveller["business_id"])
        .limit(1)
        .execute()
    )
    if biz.data:
        agency_name = biz.data[0].get("name")

    itinerary: list[TripDay] = []
    if booking.get("itinerary_id"):
        itin = (
            db.table("travel_itineraries")
            .select("days")
            .eq("id", booking["itinerary_id"])
            .eq("business_id", traveller["business_id"])
            .limit(1)
            .execute()
        )
        if itin.data:
            for i, d in enumerate(itin.data[0].get("days") or [], start=1):
                if isinstance(d, dict):
                    itinerary.append(
                        TripDay(
                            day=int(d.get("day", i)),
                            title=str(d.get("title", f"Day {i}")),
                            detail=str(d.get("detail", "")),
                        )
                    )

    grand = booking.get("grand_total_inr") or 0
    paid = booking.get("deposit_inr") or 0

    return TripOut(
        booking_ref=str(booking.get("booking_ref") or ""),
        destination=booking.get("destination"),
        status=str(booking.get("status") or "confirmed"),
        start_date=str(booking["departure_date"]) if booking.get("departure_date") else None,
        end_date=str(booking["return_date"]) if booking.get("return_date") else None,
        pax=int(booking.get("pax_count") or 1),
        agency_name=agency_name,
        agent_name=booking.get("coordinator_name"),
        itinerary=itinerary,
        # travel_bookings stores INR integers (grand_total_inr). The currency is
        # therefore INR by construction here — it is stated explicitly rather
        # than left for the client to assume, because the moment this table
        # grows a currency column the assumption would silently go wrong.
        total_amount=str(grand),
        currency="INR",
        amount_paid=str(paid),
        visa_state=str(booking.get("visa_status") or "not_required"),
    )


# ── Payments ──────────────────────────────────────────────────────────────
@router.get("/payments", response_model=list[TravellerPaymentOut])
def my_payments(traveller: dict = Depends(get_current_traveller)) -> list[TravellerPaymentOut]:
    """
    payment_links carries lead_id, not customer_id, so the traveller's links are
    reached through their leads. Both hops are business-scoped: the lead lookup
    filters on business_id, and so does the payment lookup — a link is only
    returned if BOTH its lead and itself belong to the token's tenant.
    """
    db = get_supabase_admin()
    cols = "id, amount, currency, status, expiry_at, gateway_short_url, created_at"

    # Direct attribution (payment_links.customer_id, migration 0021).
    direct = (
        db.table("payment_links")
        .select(cols)
        .eq("customer_id", traveller["customer_id"])
        .eq("business_id", traveller["business_id"])
        .order("created_at", desc=True)
        .execute()
    )
    rows = {r["id"]: r for r in (direct.data or [])}

    # Fallback via leads, kept deliberately. 0021 backfilled customer_id only
    # where a lead already implied it, so a link created before that migration
    # against a lead whose customer was set later still has customer_id NULL.
    # Dropping this path would silently hide those payment requests from the
    # person who has to pay them.
    leads = (
        db.table("travel_leads")
        .select("id")
        .eq("customer_id", traveller["customer_id"])
        .eq("business_id", traveller["business_id"])
        .execute()
    )
    lead_ids = [r["id"] for r in (leads.data or [])]
    if lead_ids:
        via_leads = (
            db.table("payment_links")
            .select(cols)
            .in_("lead_id", lead_ids)
            .eq("business_id", traveller["business_id"])
            .order("created_at", desc=True)
            .execute()
        )
        for r in via_leads.data or []:
            rows.setdefault(r["id"], r)  # de-dupe: a link can satisfy both paths

    out: list[TravellerPaymentOut] = []
    for r in sorted(rows.values(), key=lambda x: str(x.get("created_at") or ""), reverse=True):
        out.append(
            TravellerPaymentOut(
                id=str(r["id"]),
                description="Trip payment",
                amount=str(r.get("amount") or "0"),
                currency=str(r.get("currency") or "INR"),
                status=str(r.get("status") or "created"),
                due_at=str(r["expiry_at"]) if r.get("expiry_at") else None,
                pay_url=r.get("gateway_short_url"),
            )
        )
    return out


# ── Messages ──────────────────────────────────────────────────────────────
@router.get("/messages", response_model=list[TravellerMessageOut])
def my_messages(traveller: dict = Depends(get_current_traveller)) -> list[TravellerMessageOut]:
    """
    Outbound only, and every row is `from: "agency"` — because that is all that
    exists. whatsapp_outbox is a SEND log; there is no inbound table to read,
    so no message can ever legitimately be marked as coming from the traveller.

    Rows are matched on the profile's phone number, which is fetched here rather
    than trusted from the token: a token carries ids, and a phone number is
    mutable data that must be re-read.
    """
    db = get_supabase_admin()

    profile = (
        db.table("travel_customer_profiles")
        .select("phone")
        .eq("id", traveller["customer_id"])
        .eq("business_id", traveller["business_id"])
        .limit(1)
        .execute()
    )
    if not profile.data:
        return []
    phone = (profile.data[0] or {}).get("phone")
    if not phone:
        return []

    rows = (
        db.table("whatsapp_outbox")
        .select("id, payload, status, created_at, sent_at, template_name")
        .eq("business_id", traveller["business_id"])
        .eq("to_number", phone)
        .in_("status", ["sent", "stubbed"])
        .order("created_at", desc=True)
        .limit(100)
        .execute()
    )

    out: list[TravellerMessageOut] = []
    for r in rows.data or []:
        payload = r.get("payload") or {}
        text = ""
        if isinstance(payload, dict):
            body = payload.get("text")
            if isinstance(body, dict):
                text = str(body.get("body") or "")
            elif isinstance(body, str):
                text = body
        if not text:
            text = f"[{r.get('template_name') or 'message'}]"
        out.append(
            TravellerMessageOut(
                id=str(r["id"]),
                from_="agency",
                text=text,
                at=str(r.get("sent_at") or r.get("created_at") or ""),
            )
        )
    return out


# ── Combined single-step login (Phase 3.3 — agency-scoped) ────────────────
class TravellerLoginIn(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=10)


@router.post("/login", response_model=TravellerTokenOut)
def traveller_login(
    payload: TravellerLoginIn,
    request: Request,
    business_id: str = Query(..., description="Business ID / agency UUID"),
) -> TravellerTokenOut:
    """Single-step OTP login scoped to an explicit agency (B-FE7-08).

    The two-step /auth/request-otp → /auth/verify-otp flow above is the one
    customer-app calls. This endpoint is the subdomain-per-agency variant:
    same OTP pool, but the profile lookup is scoped to (business_id, email)
    instead of oldest-profile-wins, so a traveller with bookings at two
    agencies lands on the right one. Until the subdomain→business_id mapping
    exists, business_id comes as an explicit query parameter.

    Issues the SAME traveller_access token family as verify-otp, so a token
    from here works on every /me/* endpoint.
    """
    from app.routers.techscape.auth import _verify_otp

    # Same brute-force budget as verify-otp — this is the same attack surface.
    rate_limit(request, bucket="trav-otp-verify", limit=10, window_sec=300,
               email=str(payload.email))

    if not _verify_otp(str(payload.email), payload.code):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired code")

    try:
        biz_id = str(UUID(business_id))
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid business ID format")

    db = get_supabase_admin()
    res = (
        db.table("travel_customer_profiles")
        .select("id, business_id")
        .eq("business_id", biz_id)
        .eq("email", str(payload.email))
        .limit(1)
        .execute()
    )
    if not res.data:
        # Same message as a bad code — a valid guess must not confirm that the
        # address belongs to a customer of this (or any) agency.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired code")

    token = issue_traveller_token(
        customer_id=str(res.data[0]["id"]), business_id=biz_id
    )
    return TravellerTokenOut(access_token=token, expires_in_min=TRAVELLER_TOKEN_TTL_MIN)
