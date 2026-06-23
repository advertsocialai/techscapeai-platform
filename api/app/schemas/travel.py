"""Pydantic schemas for the Travel AI Operating Layer."""
from __future__ import annotations
from datetime import date, datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


WikiCategory = Literal[
    "destination", "package", "policy", "sop",
    "objection", "supplier", "pricing", "general",
]
SupplierType  = Literal[
    "hotel", "transport", "activity", "flight",
    "cruise", "restaurant", "other",
]
ItineraryStatus = Literal[
    "draft", "sent", "accepted", "modified", "booked", "cancelled",
]
GuaranteeStatus = Literal[
    "pending", "verified", "failed", "no_response", "reallocated",
]


# ── Wiki ─────────────────────────────────────────────────────────
class WikiEntryIn(_Base):
    category: WikiCategory
    title:    str = Field(min_length=1, max_length=255)
    content:  str = Field(min_length=1)
    metadata: dict[str, Any] = {}
    tags:     list[str] = []
    source:   Optional[str] = None


class WikiEntryOut(WikiEntryIn):
    id: UUID
    business_id: UUID
    created_at: datetime
    updated_at: datetime


class WikiSearchIn(_Base):
    query:    str = Field(min_length=1)
    category: Optional[WikiCategory] = None
    limit:    int = Field(default=8, ge=1, le=50)


# ── Itinerary agent ──────────────────────────────────────────────
class ItineraryRequest(_Base):
    """User intent: free text + structured hints."""
    intent:    str = Field(min_length=3,
                            description="Free text, e.g. 'Family of 4, North India, 6 days, ₹2L'")
    pax_count: int = Field(default=2, ge=1, le=40)
    budget_inr: Optional[int] = None
    duration_days: Optional[int] = Field(default=None, ge=1, le=60)
    destination_hint: Optional[str] = None
    customer_id: Optional[UUID] = None
    customer_email: Optional[EmailStr] = None
    customer_name:  Optional[str] = None
    customer_phone: Optional[str] = None
    language: str = "en"


class ItineraryDay(_Base):
    day:       int
    location:  str
    title:     Optional[str] = None
    activities: list[str] = []
    meals:     list[str] = []
    hotel:     Optional[str] = None
    transport: Optional[str] = None
    notes:     Optional[str] = None


class ItineraryOut(_Base):
    id: UUID
    business_id: UUID
    customer_id: Optional[UUID] = None
    title:  Optional[str] = None
    intent: Optional[str] = None
    pax_count: int
    days: list[dict] = []
    total_cost_inr: Optional[int] = None
    cost_breakdown: dict[str, Any] = {}
    status: ItineraryStatus
    version: int
    model:  Optional[str] = None
    created_at: datetime


class ItineraryRefineIn(_Base):
    """Modification request against an existing itinerary."""
    modifications: str = Field(min_length=3,
                                description="e.g. 'Make it 4 days and add a houseboat night'")


# ── Franchisee agent ─────────────────────────────────────────────
class FranchiseeAskIn(_Base):
    question: str = Field(min_length=3)
    franchisee_id: Optional[UUID] = None
    franchisee_city: Optional[str] = None


class FranchiseeAnswer(_Base):
    answer:    str
    sources:   list[dict] = []
    confident: bool = True
    model:     str


# ── Language bridge ──────────────────────────────────────────────
class TranslateIn(_Base):
    text:        str = Field(min_length=1, max_length=4000)
    source_lang: str = "auto"
    target_lang: str = Field(default="en", min_length=2, max_length=10)
    formality:   Literal["polite", "casual", "formal"] = "polite"


class TranslateOut(_Base):
    translated:  str
    source_lang: str
    target_lang: str
    model:       str


# ── Booking guarantee ────────────────────────────────────────────
class BookingGuaranteeIn(_Base):
    itinerary_id: UUID
    supplier_id:  UUID
    booking_ref:  Optional[str] = None
    checkin_at:   datetime


class BookingGuaranteeOut(_Base):
    id: UUID
    business_id: UUID
    itinerary_id: Optional[UUID] = None
    supplier_id:  Optional[UUID] = None
    booking_ref:  Optional[str] = None
    checkin_at:   Optional[datetime] = None
    verified_at:  Optional[datetime] = None
    verification_status: GuaranteeStatus
    failure_reason: Optional[str] = None
    alternative_id: Optional[UUID] = None
    created_at: datetime


# ── Customer memory ──────────────────────────────────────────────
class CustomerProfileIn(_Base):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    preferences: dict[str, Any] = {}
    family_profile: dict[str, Any] = {}
    language: str = "en"
    notes: Optional[str] = None


class CustomerProfileOut(CustomerProfileIn):
    id: UUID
    business_id: UUID
    past_trips: list[dict] = []
    last_intent: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# ── Catalog ──────────────────────────────────────────────────────
class DestinationIn(_Base):
    name: str
    country: str
    region: Optional[str] = None
    best_seasons: list[str] = []
    highlights:   list[str] = []
    avg_cost_inr: Optional[int] = None


class DestinationOut(DestinationIn):
    id: UUID
    business_id: UUID
    is_active: bool
    created_at: datetime


class PackageIn(_Base):
    name: str
    destination_id: Optional[UUID] = None
    duration_days: int = Field(ge=1, le=60)
    base_price_inr: int = Field(ge=0)
    inclusions: list[str] = []
    exclusions: list[str] = []
    itinerary_template: list[dict] = []
    min_pax: int = 1
    max_pax: int = 20


class PackageOut(PackageIn):
    id: UUID
    business_id: UUID
    is_active: bool
    created_at: datetime


class FranchiseeIn(_Base):
    name: str
    city: Optional[str] = None
    state: Optional[str] = None
    country: str = "India"
    owner_name: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None


class FranchiseeOut(FranchiseeIn):
    id: UUID
    business_id: UUID
    is_active: bool
    created_at: datetime


class SupplierIn(_Base):
    name: str
    supplier_type: SupplierType
    city: Optional[str] = None
    country: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    api_endpoint: Optional[str] = None


class SupplierOut(SupplierIn):
    id: UUID
    business_id: UUID
    reliability_score: float
    is_active: bool
    created_at: datetime


# ── On-Ground Companion (Attack Point 4) ─────────────────────────
IncidentChannel = Literal["whatsapp", "sms", "voice", "email", "web"]
IncidentType = Literal[
    "cab_no_show", "hotel_change", "flight_delay", "lost_item", "language_help",
    "payment_issue", "medical", "safety", "complaint", "request", "other",
]
IncidentSeverity = Literal["low", "normal", "high", "critical"]
IncidentStatus = Literal["open", "in_progress", "resolved", "escalated"]


class InTripIssueIn(_Base):
    message:      str = Field(min_length=1, max_length=4000)
    itinerary_id: Optional[UUID] = None
    customer_id:  Optional[UUID] = None
    customer_email: Optional[EmailStr] = None
    customer_phone: Optional[str] = None
    channel:      IncidentChannel = "whatsapp"
    language:     str = "en"


class InTripIssueOut(_Base):
    id: UUID
    business_id: UUID
    itinerary_id: Optional[UUID] = None
    customer_id:  Optional[UUID] = None
    channel:      IncidentChannel
    issue_type:   IncidentType
    severity:     IncidentSeverity
    customer_message: str
    agent_response:   Optional[str] = None
    status:       IncidentStatus
    escalated_to: Optional[str] = None
    resolved_at:  Optional[datetime] = None
    metadata:     dict[str, Any] = {}
    created_at:   datetime


class IncidentResolveIn(_Base):
    resolution_note: Optional[str] = None


class IncidentEscalateIn(_Base):
    escalate_to: str = Field(min_length=1, max_length=255)
    note:        Optional[str] = None


# ── Leads / Pre-Booking funnel ───────────────────────────────────
LeadSource        = Literal[
    "whatsapp", "website", "phone", "franchisee", "referral", "sms", "email", "other",
]
LeadQualification = Literal["cold", "warm", "hot", "converted", "lost"]
LeadStatus        = Literal[
    "new", "qualified", "itinerary_sent", "negotiating", "booked", "lost",
]


class LeadIn(_Base):
    raw_message: str = Field(min_length=1)
    source:      LeadSource = "whatsapp"
    customer_email: Optional[EmailStr] = None
    customer_name:  Optional[str] = None
    customer_phone: Optional[str] = None
    language:    str = "en"
    franchisee_id: Optional[UUID] = None


class LeadOut(_Base):
    id: UUID
    business_id: UUID
    customer_id: Optional[UUID] = None
    source:      LeadSource
    raw_message: str
    intent:      Optional[str] = None
    destination_hint: Optional[str] = None
    pax_count:   Optional[int] = None
    budget_inr:  Optional[int] = None
    duration_days: Optional[int] = None
    score:       int
    qualification: LeadQualification
    status:      LeadStatus
    itinerary_id: Optional[UUID] = None
    franchisee_id: Optional[UUID] = None
    metadata:    dict[str, Any] = {}
    created_at:  datetime


class LeadStatusUpdate(_Base):
    status: LeadStatus


# ── Inbound WhatsApp dispatcher ──────────────────────────────────
class WhatsAppInboundIn(_Base):
    """Body for the /travel/v1/inbound/whatsapp endpoint.

    Designed so it can be called both by Wapi webhooks and by the demo UI.
    """
    from_number: str = Field(min_length=4, max_length=32,
                              description="E.164 phone number of the sender")
    text:        str = Field(min_length=1, max_length=4000)
    customer_name: Optional[str] = None
    customer_email: Optional[EmailStr] = None
    language:    str = "en"
    itinerary_id: Optional[UUID] = None


class WhatsAppInboundOut(_Base):
    intent:       Literal["new_lead", "in_trip_issue", "translate", "general"]
    response_text: str
    lead_id:      Optional[UUID] = None
    itinerary_id: Optional[UUID] = None
    incident_id:  Optional[UUID] = None
    translated:   Optional[str] = None
    customer_id:  Optional[UUID] = None


# ── Bookings (TravelWorkflow OS anchor) ──────────────────────────
BookingStatus    = Literal["confirmed", "in_progress", "completed", "cancelled"]
BookingVisaState = Literal["not_required", "pending", "submitted", "approved", "rejected"]


class BookingIn(_Base):
    booking_ref:        str = Field(min_length=3, max_length=64)
    customer_id:        Optional[UUID] = None
    itinerary_id:       Optional[UUID] = None
    destination:        Optional[str] = None
    trip_type:          Optional[str] = None
    departure_date:     Optional[date] = None
    return_date:        Optional[date] = None
    pax_count:          int = 1
    grand_total_inr:    int = 0
    deposit_inr:        int = 0
    balance_inr:        int = 0
    balance_due_date:   Optional[date] = None
    visa_status:        BookingVisaState = "not_required"
    status:             BookingStatus = "confirmed"
    coordinator_name:   Optional[str] = None
    coordinator_phone:  Optional[str] = None
    metadata:           dict[str, Any] = {}


class BookingOut(BookingIn):
    id: UUID
    business_id: UUID
    created_at: datetime


class BookingPatch(_Base):
    destination:        Optional[str] = None
    trip_type:          Optional[str] = None
    departure_date:     Optional[date] = None
    return_date:        Optional[date] = None
    pax_count:          Optional[int] = None
    grand_total_inr:    Optional[int] = None
    deposit_inr:        Optional[int] = None
    balance_inr:        Optional[int] = None
    balance_due_date:   Optional[date] = None
    visa_status:        Optional[BookingVisaState] = None
    status:             Optional[BookingStatus] = None
    coordinator_name:   Optional[str] = None
    coordinator_phone:  Optional[str] = None
    metadata:           Optional[dict[str, Any]] = None


# ── Playbook dispatch ────────────────────────────────────────────
PlaybookChannel = Literal["email", "whatsapp", "sms", "voice"]


class PlaybookRender(_Base):
    context:  dict[str, Any] = {}
    channels: Optional[list[PlaybookChannel]] = None


class PlaybookDispatchIn(_Base):
    context:     dict[str, Any] = {}
    channels:    Optional[list[PlaybookChannel]] = None
    to_email:    Optional[EmailStr] = None
    to_phone:    Optional[str] = None
    booking_id:  Optional[UUID] = None
    booking_ref: Optional[str] = None
    customer_id: Optional[UUID] = None
    lead_id:     Optional[UUID] = None
    incident_id: Optional[UUID] = None
    dry_run:     bool = False


class PlaybookRunOut(_Base):
    id:            UUID
    business_id:   UUID
    use_case_id:   str
    booking_id:    Optional[UUID] = None
    customer_id:   Optional[UUID] = None
    trigger_kind:  str
    channels:      list[str]
    status:        str
    rendered:      dict[str, Any] = {}
    delivery:      dict[str, Any] = {}
    error_message: Optional[str] = None
    created_at:    datetime
