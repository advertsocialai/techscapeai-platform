"""
Gogaga Holidays demo seeder.

Provisions a realistic dataset matching the strategy document so the
3-minute WhatsApp demo flow ("5 day family trip to Kerala under 50K")
works end-to-end without any external data.

Idempotent — re-running clears prior seeded rows by name and recreates.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.database import get_supabase_admin


# ── Destinations ────────────────────────────────────────────────
DESTINATIONS = [
    {"name": "Kerala",     "country": "India",     "region": "South",
     "best_seasons": ["Sep", "Oct", "Nov", "Dec", "Jan", "Feb"],
     "highlights":   ["Backwaters", "Houseboats", "Tea estates", "Beaches", "Spice plantations"],
     "avg_cost_inr": 12000},
    {"name": "Himachal",   "country": "India",     "region": "North",
     "best_seasons": ["Mar", "Apr", "May", "Jun", "Oct", "Nov"],
     "highlights":   ["Manali", "Shimla", "Snow", "Adventure", "Hill stations"],
     "avg_cost_inr": 14000},
    {"name": "Rajasthan",  "country": "India",     "region": "West",
     "best_seasons": ["Oct", "Nov", "Dec", "Jan", "Feb", "Mar"],
     "highlights":   ["Jaipur", "Udaipur", "Jaisalmer", "Forts", "Desert"],
     "avg_cost_inr": 13000},
    {"name": "Goa",        "country": "India",     "region": "West",
     "best_seasons": ["Nov", "Dec", "Jan", "Feb"],
     "highlights":   ["Beaches", "Nightlife", "Portuguese architecture", "Watersports"],
     "avg_cost_inr": 11000},
    {"name": "Thailand",   "country": "Thailand",  "region": "SEA",
     "best_seasons": ["Nov", "Dec", "Jan", "Feb", "Mar"],
     "highlights":   ["Bangkok", "Phuket", "Krabi", "Islands", "Street food"],
     "avg_cost_inr": 35000},
    {"name": "Singapore",  "country": "Singapore", "region": "SEA",
     "best_seasons": ["Feb", "Mar", "Apr", "Jul", "Aug"],
     "highlights":   ["Sentosa", "Universal Studios", "Gardens by the Bay", "Marina Bay"],
     "avg_cost_inr": 45000},
    {"name": "Dubai",      "country": "UAE",       "region": "Middle East",
     "best_seasons": ["Oct", "Nov", "Dec", "Jan", "Feb", "Mar"],
     "highlights":   ["Burj Khalifa", "Desert safari", "Shopping", "Aquaventure"],
     "avg_cost_inr": 55000},
    {"name": "Bali",       "country": "Indonesia", "region": "SEA",
     "best_seasons": ["Apr", "May", "Jun", "Sep", "Oct"],
     "highlights":   ["Ubud", "Beaches", "Temples", "Rice terraces"],
     "avg_cost_inr": 40000},
]


# ── Packages ─────────────────────────────────────────────────────
def _pkg(name, dest_name, days, price, inclusions, exclusions=None):
    return {"_dest": dest_name, "name": name, "duration_days": days,
            "base_price_inr": price, "inclusions": inclusions,
            "exclusions": exclusions or ["Travel insurance", "Personal expenses"],
            "min_pax": 1, "max_pax": 12}


PACKAGES = [
    _pkg("Kerala Family Special — 5N6D",   "Kerala",   6, 42000,
         ["Return flights", "3★ hotels", "Houseboat (1N)", "Breakfast + dinner",
          "Private car", "All transfers", "Sightseeing"]),
    _pkg("Kerala Honeymoon — 4N5D",        "Kerala",   5, 38000,
         ["Return flights", "4★ resorts", "Houseboat (1N)", "Candle-light dinner",
          "Private car", "Spa session"]),
    _pkg("Himachal Adventure — 6N7D",      "Himachal", 7, 45000,
         ["Return flights to Chandigarh", "3★ hotels", "All breakfasts",
          "Volvo transfers", "Manali + Shimla + Solang"]),
    _pkg("Rajasthan Heritage — 6N7D",      "Rajasthan",7, 48000,
         ["Jaipur + Udaipur + Jodhpur", "4★ heritage hotels", "Breakfast + dinner",
          "Private AC car with driver"]),
    _pkg("Goa Beach Break — 3N4D",         "Goa",      4, 22000,
         ["Return flights", "3★ beach resort", "Breakfast",
          "Airport transfers", "Sunset cruise"]),
    _pkg("Thailand Discovery — 6N7D",      "Thailand", 7, 65000,
         ["Return international flights", "4★ hotels Bangkok + Phuket",
          "Breakfast", "Phi Phi island tour", "Coral island tour"]),
    _pkg("Singapore Fun — 5N6D",           "Singapore",6, 75000,
         ["Return flights", "4★ hotels", "Universal Studios", "Sentosa",
          "Night safari", "Half-day city tour"]),
    _pkg("Dubai Family — 5N6D",            "Dubai",    6, 85000,
         ["Return flights", "4★ hotels", "Desert safari", "Burj Khalifa",
          "Dhow cruise", "Aquaventure waterpark"]),
    _pkg("Bali Romance — 6N7D",            "Bali",     7, 70000,
         ["Return flights", "4★ private villa", "Daily breakfast",
          "Ubud tour", "Watersports", "Tanah Lot sunset"]),
]


# ── Wiki entries (RAG knowledge base) ───────────────────────────
WIKI_ENTRIES = [
    # Policies
    {"category": "policy", "title": "Cancellation Policy",
     "content": (
         "Cancellation charges are levied on the basis of when cancellation is requested.\n"
         "• More than 45 days before departure: 10% of package cost (admin fee)\n"
         "• 30-45 days before: 25% of package cost\n"
         "• 15-30 days before: 50% of package cost\n"
         "• 7-15 days before: 75% of package cost\n"
         "• Less than 7 days or no-show: 100% (no refund)\n"
         "International packages have stricter terms — refer the supplier's policy."
     ),
     "tags": ["cancellation", "refund", "policy", "terms"]},

    {"category": "policy", "title": "Refund Process",
     "content": (
         "Eligible refunds are processed within 7-14 working days to the original payment method. "
         "Bank charges and forex conversion fees, if any, are deducted. Customer must email "
         "refunds@gogaga.in with booking reference."
     ),
     "tags": ["refund", "policy"]},

    {"category": "policy", "title": "Payment Terms",
     "content": (
         "• 25% advance to confirm booking\n"
         "• 50% payment due 30 days before travel\n"
         "• Balance due 7 days before departure\n"
         "Accepted: UPI, NEFT, credit card, EMI (Bajaj Finance, HDFC). For franchisees, "
         "settlement is weekly via the franchisee portal."
     ),
     "tags": ["payment", "policy", "advance"]},

    # SOPs
    {"category": "sop", "title": "Itinerary Customization SOP",
     "content": (
         "When a franchisee receives a custom request:\n"
         "1. Capture pax, dates, budget, preferences in the CRM\n"
         "2. Build using the catalog template — modify only inclusions, not pricing structure\n"
         "3. Get HQ approval if budget < 80% of base package or destination not in catalog\n"
         "4. Send quote within 2 working hours; follow up at 24h and 72h"
     ),
     "tags": ["sop", "customization", "franchisee"]},

    {"category": "sop", "title": "Booking Confirmation SOP",
     "content": (
         "Within 30 minutes of confirmation:\n"
         "• Send digital voucher to customer (WhatsApp + email)\n"
         "• Send supplier reconfirmation request\n"
         "• 24h before check-in: re-verify supplier; flag any 'no response' to ops team\n"
         "• Day-of: send 'arrival assist' WhatsApp with hotel contact + property notes"
     ),
     "tags": ["sop", "booking", "supplier", "verification"]},

    {"category": "sop", "title": "Supplier Failure Recovery",
     "content": (
         "If a supplier fails reconfirmation:\n"
         "1. Call the property directly within 1 hour\n"
         "2. If unreachable or full, book the pre-approved alternative in the same tier\n"
         "3. Notify customer with a polite WhatsApp explaining the upgrade/change\n"
         "4. Log the incident in the CRM and flag the supplier's reliability score"
     ),
     "tags": ["sop", "supplier", "recovery", "guarantee"]},

    {"category": "sop", "title": "Franchisee Onboarding SOP",
     "content": (
         "New franchisee onboarding: 14 days from agreement signing.\n"
         "• Week 1: CRM training, brand assets, MoU + KYC\n"
         "• Week 2: Two ride-along bookings with regional manager\n"
         "• Independent operation begins from day 15. First three months are reviewed monthly."
     ),
     "tags": ["sop", "franchisee", "onboarding"]},

    # Objections / responses
    {"category": "objection", "title": "Customer says 'too expensive'",
     "content": (
         "Acknowledge the budget, then offer (a) a shorter package, (b) reduced hotel tier, "
         "or (c) off-peak dates with the same itinerary. Never discount without manager approval. "
         "Highlight inclusions: flights, transfers, sightseeing — most online prices hide these."
     ),
     "tags": ["objection", "sales", "pricing"]},

    {"category": "objection", "title": "Customer wants 'guaranteed cheapest'",
     "content": (
         "We do not price-match aggregators because they exclude essentials. "
         "Position Gogaga as a 'one bill, everything sorted' product — quote against the FULL trip cost "
         "the customer would assemble themselves."
     ),
     "tags": ["objection", "pricing"]},

    # Pricing
    {"category": "pricing", "title": "Group fare logic",
     "content": (
         "Group fares apply for 6+ pax on the same booking. Discount tiers: 6-9 pax 5%, "
         "10-14 pax 8%, 15+ pax 10%. Group fares are non-refundable once ticketed."
     ),
     "tags": ["pricing", "group"]},

    # Destinations (wiki-level extras)
    {"category": "destination", "title": "Kerala — best months & pitfalls",
     "content": (
         "October to February is peak. Monsoon (June-Sept) is dramatic but houseboats are limited. "
         "Avoid Onam week (early Sept) for last-minute bookings — prices spike 40%. "
         "Backwater day cruises are subject to weather cancellation; offer alternatives."
     ),
     "tags": ["destination", "kerala", "season"]},

    {"category": "destination", "title": "Manali / Himachal — booking caveats",
     "content": (
         "Volvo from Delhi books out 7+ days ahead in peak season (May-June, Oct-Nov). "
         "Solang valley adventure activities are weather-dependent. "
         "Snow conditions cannot be guaranteed before mid-December."
     ),
     "tags": ["destination", "himachal", "manali"]},

    # General
    {"category": "general", "title": "Brand promise",
     "content": (
         "From the first thought of a trip to the last memory of it — one intelligent layer that "
         "never leaves your side. Gogaga is the human + AI partnership the travel industry has been missing."
     ),
     "tags": ["brand", "positioning"]},

    {"category": "general", "title": "Multi-language support",
     "content": (
         "English is the primary language. Hindi support is available across all touchpoints. "
         "Regional languages (Tamil, Telugu, Kannada, Malayalam, Marathi, Bengali) are routed to "
         "franchisees who operate in those states."
     ),
     "tags": ["language", "support"]},
]


# ── Franchisees ─────────────────────────────────────────────────
FRANCHISEES = [
    {"name": "Gogaga Hyderabad — Banjara Hills", "city": "Hyderabad", "state": "Telangana"},
    {"name": "Gogaga Bangalore — Indiranagar",   "city": "Bangalore", "state": "Karnataka"},
    {"name": "Gogaga Mumbai — Andheri",          "city": "Mumbai",    "state": "Maharashtra"},
    {"name": "Gogaga Delhi — Connaught Place",   "city": "New Delhi", "state": "Delhi"},
    {"name": "Gogaga Pune — Koregaon Park",      "city": "Pune",      "state": "Maharashtra"},
    {"name": "Gogaga Chennai — T Nagar",         "city": "Chennai",   "state": "Tamil Nadu"},
    {"name": "Gogaga Kochi — Marine Drive",      "city": "Kochi",     "state": "Kerala"},
    {"name": "Gogaga Vizag — Beach Road",        "city": "Visakhapatnam", "state": "Andhra Pradesh"},
]


# ── Suppliers ────────────────────────────────────────────────────
SUPPLIERS = [
    {"name": "Spice Tree Munnar",     "supplier_type": "hotel",     "city": "Munnar",  "country": "India", "reliability_score": 92.0},
    {"name": "Lake Palace Alleppey",  "supplier_type": "hotel",     "city": "Alleppey","country": "India", "reliability_score": 88.0},
    {"name": "Houseboat Co. Kumarakom","supplier_type": "activity", "city": "Kumarakom","country": "India","reliability_score": 90.0},
    {"name": "Solang Adventure Pvt",  "supplier_type": "activity",  "city": "Manali",  "country": "India", "reliability_score": 78.0},
    {"name": "Heritage Cars Rajasthan","supplier_type": "transport","city": "Jaipur",  "country": "India", "reliability_score": 95.0},
    {"name": "Goa Cruise Lines",      "supplier_type": "activity",  "city": "Panaji",  "country": "India", "reliability_score": 81.0},
]


def seed_gogaga_demo(business_id: UUID) -> dict:
    """Wipe and recreate the Gogaga demo dataset."""
    db = get_supabase_admin()
    bid = str(business_id)

    # Wipe
    for t in ("travel_playbook_runs", "travel_bookings",
              "travel_packages", "travel_destinations", "travel_franchisees",
              "travel_suppliers", "travel_wiki", "travel_customer_profiles"):
        db.table(t).delete().eq("business_id", bid).execute()

    # Destinations
    dests_in = [{**d, "business_id": bid} for d in DESTINATIONS]
    dest_rows = db.table("travel_destinations").insert(dests_in).execute().data or []
    dest_id_by_name = {r["name"]: r["id"] for r in dest_rows}

    # Packages (resolve _dest → destination_id)
    pkgs_in = []
    for p in PACKAGES:
        pp = dict(p)
        pp["destination_id"] = dest_id_by_name.get(pp.pop("_dest"))
        pp["business_id"] = bid
        pkgs_in.append(pp)
    pkg_rows = db.table("travel_packages").insert(pkgs_in).execute().data or []

    # Wiki
    wiki_in = [{**w, "business_id": bid} for w in WIKI_ENTRIES]
    wiki_rows = db.table("travel_wiki").insert(wiki_in).execute().data or []

    # Franchisees
    fr_in = [{**f, "business_id": bid,
              "onboarded_at": (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()}
              for f in FRANCHISEES]
    fr_rows = db.table("travel_franchisees").insert(fr_in).execute().data or []

    # Suppliers
    sp_in = [{**s, "business_id": bid} for s in SUPPLIERS]
    sp_rows = db.table("travel_suppliers").insert(sp_in).execute().data or []

    # Sample customers + bookings spanning the schedule anchors so the
    # TravelWorkflow OS scheduler has real data to fire on.
    today = datetime.now(timezone.utc).date()
    customers = [
        {"full_name": "Sarah Mehra",   "email": "sarah@example.com",
         "phone": "+919999000001", "preferred_language": "en"},
        {"full_name": "Arjun Kapoor",  "email": "arjun@example.com",
         "phone": "+919999000002", "preferred_language": "en"},
        {"full_name": "Priya Iyer",    "email": "priya@example.com",
         "phone": "+919999000003", "preferred_language": "en"},
    ]
    cust_in = [{**c, "business_id": bid} for c in customers]
    cust_rows = db.table("travel_customer_profiles").insert(cust_in).execute().data or []
    by_email = {c["email"]: c["id"] for c in cust_rows}

    bookings = [
        # 1. Departing in 14 days → exercises UC-008/009/010/011
        {"booking_ref": "TSAI-20260606-0001",
         "customer_id": by_email.get("sarah@example.com"),
         "destination": "Kerala", "trip_type": "Honeymoon",
         "departure_date": (today + timedelta(days=14)).isoformat(),
         "return_date":    (today + timedelta(days=21)).isoformat(),
         "pax_count": 2, "grand_total_inr": 105000, "deposit_inr": 25000,
         "balance_inr": 80000,
         "balance_due_date": (today + timedelta(days=7)).isoformat(),
         "visa_status": "not_required", "status": "confirmed",
         "coordinator_name": "Arjun Mehta", "coordinator_phone": "+919999900001"},
        # 2. Currently in-trip → exercises UC-012/013/014
        {"booking_ref": "TSAI-20260606-0002",
         "customer_id": by_email.get("arjun@example.com"),
         "destination": "Thailand", "trip_type": "Family Holiday",
         "departure_date": (today - timedelta(days=2)).isoformat(),
         "return_date":    (today + timedelta(days=4)).isoformat(),
         "pax_count": 4, "grand_total_inr": 240000, "deposit_inr": 240000,
         "balance_inr": 0,
         "visa_status": "approved", "status": "in_progress",
         "coordinator_name": "Priya Sharma", "coordinator_phone": "+919999900002"},
        # 3. Returned 2 days ago → exercises UC-015
        {"booking_ref": "TSAI-20260606-0003",
         "customer_id": by_email.get("priya@example.com"),
         "destination": "Rajasthan", "trip_type": "Heritage Tour",
         "departure_date": (today - timedelta(days=12)).isoformat(),
         "return_date":    (today - timedelta(days=2)).isoformat(),
         "pax_count": 2, "grand_total_inr": 88000, "deposit_inr": 88000,
         "balance_inr": 0,
         "visa_status": "not_required", "status": "completed",
         "coordinator_name": "Rohit Verma", "coordinator_phone": "+919999900003"},
    ]
    bk_in = [{**b, "business_id": bid} for b in bookings]
    bk_rows = db.table("travel_bookings").insert(bk_in).execute().data or []

    return {
        "business_id":  bid,
        "destinations": len(dest_rows),
        "packages":     len(pkg_rows),
        "wiki_entries": len(wiki_rows),
        "franchisees":  len(fr_rows),
        "suppliers":    len(sp_rows),
        "customers":    len(cust_rows),
        "bookings":     len(bk_rows),
    }
