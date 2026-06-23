"""Demo / seed endpoint — provisions Gogaga + an end-to-end UC walkthrough."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.services.travel import (
    PlaybookExecutor, playbooks as pb_registry, seed_gogaga_demo,
)
from app.routers.techscape._deps import require_business

router = APIRouter()


@router.post("/seed-gogaga")
def seed_gogaga(biz: dict = Depends(require_business)):
    """
    Inserts the full Gogaga Holidays starter set:
      • 8 destinations · 9 packages · 14 wiki entries
      • 8 franchisees · 6 suppliers
      • 3 sample customers · 3 sample bookings (D-14 honeymoon, in-trip family,
        returned heritage tour) — exercises every UC anchor
    Idempotent — safe to call repeatedly.
    """
    return seed_gogaga_demo(UUID(biz["id"]))


@router.post("/playbook-walkthrough")
async def playbook_walkthrough(
    booking_ref: Optional[str] = Query(default="TSAI-20260606-0001"),
    biz: dict = Depends(require_business),
):
    """
    Renders all 24 UCs in dry_run mode against a real booking + customer from
    the Gogaga seed. Proves every template formats end-to-end with merged
    business + booking + customer context.

    Returns a list of 24 entries, each with id/title/channels and rendered
    output per channel (subject/body/content/script).
    """
    executor = PlaybookExecutor()
    db = executor.db
    biz_id = UUID(biz["id"])

    booking = (
        db.table("travel_bookings").select("*")
        .eq("business_id", str(biz_id))
        .eq("booking_ref", booking_ref).limit(1).execute().data
    )
    booking = booking[0] if booking else None
    customer = None
    if booking and booking.get("customer_id"):
        cu = (
            db.table("travel_customer_profiles").select("*")
            .eq("id", booking["customer_id"]).limit(1).execute().data
        )
        customer = cu[0] if cu else None

    extras = _sample_extras()
    ctx = executor.build_context(business=biz, booking=booking,
                                  customer=customer, extra=extras)

    walkthrough: list[dict] = []
    for uc_id in pb_registry.PLAYBOOKS:
        rendered = executor.render(uc_id, ctx)
        walkthrough.append(rendered)

    return {
        "booking_ref": booking_ref,
        "context_keys": sorted(ctx.keys()),
        "count": len(walkthrough),
        "use_cases": walkthrough,
    }


def _sample_extras() -> dict:
    """Plausible defaults for every merge variable across the 24 UCs.
    Anything left unfilled renders as `{var}` (SafeDict)."""
    return {
        "source":          "website",
        "budget_range":    "₹50,000",
        "dates":           "12–22 Jan 2027",
        "amount":          "₹52,500",
        "quote_date":      "06 Jun 2026",
        "expiry_date":     "20 Jun 2026",
        "agent_phone":     "+91-9999900001",
        "flight_out":      "AI-302",
        "origin":          "DEL",
        "dest_city":       "COK",
        "dep_time":        "06:45",
        "flight_ret":      "AI-411",
        "dep_time2":       "21:30",
        "hotel_list":      "Taj Lake Palace (3N) · Niraamaya Retreats (4N)",
        "payment_date":    "06 Jun 2026",
        "visa_deadline":   "01 Dec 2026",
        "payment_link":    "https://pay.gogaga.in/tsai-0001",
        "days_label":      "in 7 days",
        "urgency_line":    "Your balance is due in 7 days.",
        "due_date":        "15 Dec 2026",
        "due_phrase":      "in 7 days",
        "overdue_warning": "",
        "overdue_note":    "",
        "cancellation_warning": "",
        "bank_details":    "HDFC 50100123456789 · IFSC HDFC0000123",
        "extended_deadline":"18 Dec 2026",
        "amendment_type":  "Date Change",
        "original_detail": "12–22 Jan 2027",
        "new_detail":      "19–29 Jan 2027",
        "fee":             "₹2,500",
        "fee_note":        "supplier change fee",
        "price_diff_note": "no price change",
        "new_total":       "₹107,500",
        "additional_due":  "₹2,500",
        "additional_due_date":"20 Jun 2026",
        "additional_payment_link":"",
        "processed_date":  "06 Jun 2026",
        "reason":          "Supplier capacity",
        "alternative":     "Niraamaya Backwaters (same category)",
        "total_paid":      "₹25,000",
        "cancellation_fee":"₹7,500",
        "refund_amount":   "₹17,500",
        "fee_policy":      "30%, more than 21 days before departure",
        "insurance_hotline":"+91-1800-209-5858",
        "visa_status_banner":"REQUIRED",
        "visa_action_required":"Apply within 7 days at gogaga.in/visa",
        "passport_expiry_check":"OK — valid 12 months beyond return",
        "visa_link":       "https://gogaga.in/visa",
        "fourteen_day_date":"23 Dec 2026",
        "three_day_date":  "03 Jan 2027",
        "visa_email":      "visa@gogaga.in",
        "visa_whatsapp_status":"Pending — apply now",
        "travel_month":    "January 2027",
        "weather_summary": "Pleasant, 18–28°C, low humidity",
        "weather_brief":   "warm days, cool evenings",
        "clothing_recommendation":"light cottons + a light jacket",
        "clothing_tip":    "layers",
        "packing_essentials":"Sunscreen · sun hat · power adapter · meds",
        "destination_packing":"Modest temple-wear · waterproof bag",
        "local_currency":  "Indian Rupee",
        "currency_code":   "INR",
        "currency_tip":    "Use UPI / cards · keep ₹2,000 in small notes",
        "exchange_rate":   "1 USD ≈ ₹83",
        "forex_advice":    "Use Hyderabad-airport forex desk before departure",
        "atm_advice":      "ATMs in towns; carry cash for villages",
        "tipping_guide":   "10% restaurants · ₹100/day drivers",
        "local_emergency": "112",
        "hospital_name":   "KIMS Hospital, Trivandrum",
        "hospital_address":"Anayara, Trivandrum 695029",
        "app_list":        "Ola, Google Maps offline, WhatsApp, Splitwise",
        "coord_hours":     "9AM–9PM IST",
        "checkin_time":    "04:00 IST",
        "arrive_by_time":  "04:15",
        "terminal":        "3",
        "driver_name":     "Ravi Kumar",
        "driver_phone":    "+91-9999911111",
        "hotel_name":      "Taj Lake Palace",
        "hotel1_phone":    "+91-9999922222",
        "arrival_airport": "COK",
        "name_on_sign":    "MEHRA — GOGAGA",
        "vehicle_type":    "Toyota Innova (white)",
        "plate_number":    "KL-07-AB-1234",
        "day_number":      3, "total_days": 7,
        "todays_schedule": "Backwater houseboat cruise · Sunset at Kovalam",
        "city":            "Alleppey", "weather": "29°C light breeze",
        "tonight_hotel":   "Niraamaya Backwaters",
        "todays_highlight":"Houseboat cruise",
        "pickup_time":     "10:30 AM",
        "location":        "Kovalam Beach Road",
        "issue_type":      "cab_no_show",
        "actions_taken":   "Backup cab dispatched (ETA 8 min) · Hotel notified",
        "safe_location":   "Hotel Sea Face lobby",
        "passport_no":     "K7654321",
        "passport_expiry": "12 Jan 2031",
        "embassy":         "Indian High Commission",
        "embassy_address": "Plot 50G Diplomatic Enclave",
        "embassy_phone":   "+91-1800-INDIA",
        "eta":             "8 minutes",
        "safe_waiting_location":"Hotel Sea Face lobby",
        "alternative_hotel":"Niraamaya Backwaters (same category)",
        "police_station":  "Kovalam PS, 0.4 km away",
        "medical_hotline": "+91-1800-108-1234",
        "hospital":        "KIMS Hospital, Trivandrum",
        "delay_reason":    "ATC slot",
        "cancellation_note":"",
        "rebooking_option":"  • AI-411 same day +90 min — already held for you",
        "delay_mins":      75,
        "alt_flight_time": "08:00",
        "alt_airline":     "IndiGo 6E-345",
        "new_time":        "08:00",
        "original_time":   "06:45",
        "flight_number":   "AI-302",
        "survey_link":     "https://gogaga.in/survey/0001",
        "google_review_link":"https://g.page/gogaga/review",
        "tripadvisor_link":"https://www.tripadvisor.in/gogaga",
        "facebook_link":   "https://facebook.com/gogagaholidays",
        "loyalty_credit":  "₹1,050",
        "total_balance":   "₹4,050",
        "tier":            "Silver",
        "tier_perks":      "5% loyalty, free upgrades when available",
        "referral_amount": "₹3,000",
        "referral_code":   "SARAH2026",
        "referral_link":   "https://gogaga.in/refer/SARAH2026",
        "destination_suggestions":"Bali (Aug) · Dubai (Nov) · Bhutan (Oct)",
        "bonus_credit":    "₹500",
        "destination_memory_line":"on the houseboat in Alleppey",
        "discount":        "12%",
        "prev_coordinator":"Arjun Mehta",
        "next_destination_suggestions":"Bali · Bhutan · Vietnam",
        "visa_type":       "e-Visa (Tourist)",
        "visa_number":     "TH-2026-987654",
        "valid_from":      "01 Jan 2027",
        "valid_until":     "31 Mar 2027",
        "entry_type":      "Single",
        "entry_notes":     "60-day stay",
        "max_stay":        "60 days",
        "passport_last4":  "4321",
        "entry_conditions":"Yellow fever vaccination not required",
        "border_crossing_instructions":"Present passport + printed visa at immigration",
        "days_remaining":  18,
        "visa_ref":        "VRX-77821",
        "rejection_date":  "06 Jun 2026",
        "rejection_reason":"Insufficient travel history",
        "reapply_details": "Resubmit with last 2 yrs of travel records",
        "success_rate":    "85%",
        "new_timeline":    "10 working days",
        "required_docs":   "Passport stamps · prior visa copies",
        "appeal_details":  "Formal appeal letter within 14 days",
        "appeal_deadline": "20 Jun 2026",
        "alternative_route":"e-Visa via consular jurisdiction Mumbai",
        "eligibility_notes":"OK if you can travel via Mumbai",
        "hold_deadline":   "01 Oct 2026",
        "rebook_deadline": "31 Dec 2026",
        "next_call_date":  "10 Jun 2026",
        "additional_docs": "ITR + bank statements",
        "processing_time": "10",
        "update_frequency":"48 hours",
        "update":          "Reapplication submitted",
        "next_steps":      "Await embassy response",
        "trip_type":       "Honeymoon",
        "price_decor":     "₹3,500",
        "price_champagne": "₹4,500",
        "price_dinner":    "₹8,500",
        "price_spa":       "₹6,500",
        "price_cruise":    "₹12,000",
        "price_cake":      "₹2,500",
        "price_photo":     "₹15,000",
        "price_star":      "₹14,000",
        "price_music":     "₹9,000",
        "destination_risk_factors":"Monsoon season may delay flights · Medical costs abroad are high",
        "trip_value":      "₹1,05,000",
        "evacuation_cost": "₹15-25 lakhs",
        "cancellation_loss":"Up to entire trip value",
        "bag_cost":        "₹35,000",
        "basic_price":     "₹450",
        "std_price":       "₹950",
        "prem_price":      "₹1,650",
        "premium":         "₹950",
        "insurer_name":    "Bajaj Allianz",
        "insurance_link":  "https://gogaga.in/insure/0001",
        "destination_wellness_history":"Kerala is the birthplace of Ayurveda, 5,000 years old",
        "authenticity_notes":"Govt-certified Ayurvedic centres, not hotel spas",
        "wellness_highlight_1":"Authentic Panchakarma centres",
        "wellness_highlight_2":"Yoga Alliance-certified teachers",
        "wellness_highlight_3":"3,000-year-old Vedic traditions",
        "price_1":         "₹1,800", "price_2":"₹2,500", "price_3":"₹6,500",
        "price_4":         "₹1,200", "price_5":"₹8,500", "price_6":"₹22,000",
        "event_type":      "Annual offsite",
        "company_client":  "Acme Corp Pvt Ltd",
        "delegates":       45,
        "gst_number":      "27AAACA1234A1Z5",
        "account_manager": "Rohit Verma",
        "account_manager_phone":"+91-9999900002",
        "account_manager_email":"corporate@gogaga.in",
        "proposal_deadline":"09 Jun 2026",
        "venue_concept":   "Goa beachfront resort",
        "activity_concept":"Catamaran race + spice plantation",
        "reward_type":     "Loyalty Credit",
        "reward_amount":   "₹1,050",
        "new_balance":     "₹4,050",
        "total_trips":     3,
        "total_earned":    "₹4,050",
        "applied_to":      "Trip TSAI-20260606-0003",
        "expiry_note":     "Valid until 31 Dec 2027",
        "referral_line":   "Loyalty credit earned",
        "referral_whatsapp_note":"Loyalty credit earned",
        "next_tier_threshold":"₹50,000",
        "auto_ref":        "WAP-77123",
        "agent_email":     "priya@gogaga.in",
    }
