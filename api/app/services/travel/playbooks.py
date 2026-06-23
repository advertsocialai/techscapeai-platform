"""
TravelWorkflow OS — playbook registry.

Single source of truth for all 24 use cases (UC-001 .. UC-024) from the
TechScape Travel Industry Workflow spec. Each entry has:

  • metadata    — title, category, priority, sla, channels, trigger
  • templates   — email_subject, email_body, whatsapp, sms, phone_script
  • automation  — list of automation rule strings
  • merge_vars  — variable names used in this UC
  • schedule    — relative time anchor + offset (used by the scheduler)

Rendering is done with `str.format_map(SafeDict(...))` so any unmapped
variable is left as `{var}` for the operator to fix.
"""
from __future__ import annotations
from typing import Any


class SafeDict(dict):
    """Format mapping that leaves unknown vars untouched."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


# ── canonical category labels ────────────────────────────────────
CATEGORY = {
    "enquiry":   "Enquiry & Lead Management",
    "booking":   "Booking & Payment",
    "predep":    "Pre-Departure",
    "intrip":    "In-Trip Support",
    "posttrip":  "Post-Trip",
    "visa":      "Visa & Documents",
    "upsell":    "Upsell & Loyalty",
}


# Anchor codes used by the scheduler
#   enquiry_created      → for UC-001/002
#   quote_sent           → for UC-003 (T+24/48/72)
#   booking_confirmed    → for UC-004/020/021/022
#   balance_due          → for UC-005 (D-7/D-3/D-0/D+1)
#   amendment_request    → for UC-006
#   cancellation         → for UC-007
#   departure_date       → for UC-008/009/010/011 (D-30/D-14/D-3/D-0)
#   trip_day             → for UC-012 (every day at 8AM local)
#   emergency            → for UC-013
#   flight_delay         → for UC-014
#   return_date          → for UC-015 (+48h), UC-016 (+7d), UC-017 (+365d)
#   visa_approved        → for UC-018
#   visa_rejected        → for UC-019
#   mice_enquiry         → for UC-023
#   reward_event         → for UC-024


PLAYBOOKS: dict[str, dict[str, Any]] = {

    # ════════════════════════════════════════════════════════════
    # SECTION A — Enquiry & Lead Management
    # ════════════════════════════════════════════════════════════
    "UC-001": {
        "title":    "New Enquiry — Instant Multi-Channel Acknowledgement",
        "category": "enquiry",
        "priority": "P1",
        "sla":      "< 5 minutes",
        "channels": ["email", "whatsapp", "sms", "voice"],
        "trigger":  "Customer submits enquiry via website, WhatsApp, phone, walk-in or partner referral",
        "schedule": {"anchor": "enquiry_created", "offset_minutes": 0},
        "merge_vars": [
            "name","ref","datetime","destination","dates","pax","budget_range",
            "agent_name","company_name","phone","email","website","whatsapp_num",
            "source","timeofday",
        ],
        "email_subject": "Thank you for your travel enquiry — [Ref: {ref}] | {company_name}",
        "email_body": (
            "Dear {name},\n\n"
            "Namaste! Thank you for reaching out to {company_name}. We have received your travel "
            "enquiry and are excited to help plan your perfect journey.\n\n"
            "YOUR ENQUIRY DETAILS\n"
            "════════════════════════════════\n"
            "Reference Number  : {ref}\n"
            "Date & Time       : {datetime} IST\n"
            "Destination       : {destination}\n"
            "Travel Dates      : {dates}\n"
            "No. of Travellers : {pax}\n"
            "Budget Range      : {budget_range} per person\n"
            "Source            : {source}\n"
            "════════════════════════════════\n\n"
            "WHAT HAPPENS NEXT\n"
            "  • Your dedicated travel specialist will call within 2 hours\n"
            "  • A personalised itinerary & quote will be emailed within 4 hours\n"
            "  • We are available Monday–Saturday, 9:00 AM–7:00 PM IST\n\n"
            "In the meantime:\n"
            "  • WhatsApp us at {whatsapp_num}\n"
            "  • Call us directly on {phone}\n"
            "  • Browse our packages at {website}\n\n"
            "Warm regards,\n"
            "{agent_name} | India Travel Specialist | {company_name}\n"
            "Tel: {phone}  |  Email: {email}  |  Web: {website}"
        ),
        "whatsapp": (
            "Namaste {name}! Thank you for contacting *{company_name}*!\n\n"
            "Enquiry received: *{ref}*\n"
            "Received at: {datetime} IST\n"
            "Destination: {destination}\n"
            "Travellers: {pax}\n\n"
            "Your specialist calls within *2 hours*.\n"
            "Browse packages: {website}\n\n"
            "_Available Mon–Sat, 9AM–7PM IST_"
        ),
        "sms": (
            "Hi {name}! {company_name} received your travel enquiry [Ref:{ref}]. "
            "Specialist calls within 2hrs. Questions? Call {phone}"
        ),
        "phone_script": (
            "INBOUND CALL SCRIPT — NEW ENQUIRY\n\n"
            "GREETING: \"Good {timeofday}, thank you for calling {company_name}. My name is "
            "{agent_name}. How may I assist you today?\"\n\n"
            "NEEDS DISCOVERY — Ask all 7 questions:\n"
            "  1. Which destination(s) are you interested in visiting?\n"
            "  2. What are your preferred travel dates and duration?\n"
            "  3. How many people travelling including children's ages?\n"
            "  4. Type of experience — heritage, adventure, beach, wellness, honeymoon?\n"
            "  5. Budget range per person?\n"
            "  6. Travelled here before? Any specific requirements?\n"
            "  7. Flights only, land only, or full package?\n\n"
            "SETTING EXPECTATIONS:\n"
            "  \"I'll email a personalised itinerary and quote within 4 hours to {email}. "
            "Your reference is {ref}. I'll also send a WhatsApp confirmation to this number now.\"\n\n"
            "CLOSE: \"Thank you {name}! I look forward to helping you experience this journey. Speak soon!\""
        ),
        "automation": [
            "T+0: Enquiry created → generate REF → send Email + WhatsApp + SMS ACK simultaneously",
            "T+5 min: If agent not assigned → alert team lead via Slack",
            "T+120 min: If no agent call logged → escalate to supervisor + resend WhatsApp",
            "T+240 min: If no quote sent → automated WhatsApp follow-up",
            "T+24 hr: If no customer response → trigger UC-003 follow-up sequence",
        ],
    },

    "UC-002": {
        "title":    "WhatsApp Inbound — Auto-Triage & Intent Detection",
        "category": "enquiry",
        "priority": "P1",
        "sla":      "< 2 minutes",
        "channels": ["whatsapp", "sms"],
        "trigger":  "WhatsApp message received from new contact or outside business hours",
        "schedule": {"anchor": "whatsapp_inbound", "offset_minutes": 0},
        "merge_vars": ["name","auto_ref","company_name","phone","emergency_line"],
        "whatsapp": (
            "Hello {name}! Welcome to *{company_name}* — India's trusted travel partner.\n\n"
            "We've received your message and will respond within *30 minutes* "
            "(Mon-Sat, 9AM-7PM IST).\n\n"
            "To help us faster, please reply with a number:\n\n"
            "1. *NEW TRIP* — Plan a new holiday\n"
            "2. *EXISTING BOOKING* — Query about a booking\n"
            "3. *VISA HELP* — Visa and documentation support\n"
            "4. *URGENT* — Immediate assistance needed\n"
            "5. *SPEAK TO AGENT* — Connect with a person now\n\n"
            "Your auto-reference: *{auto_ref}*\n\n"
            "_For emergencies outside hours: {emergency_line}_"
        ),
        "sms": (
            "{company_name}: Got your WhatsApp! Ref:{auto_ref}. We reply within 30 mins "
            "(Mon-Sat 9AM-7PM). Urgent? Call {phone}"
        ),
        "phone_script": (
            "CALLBACK SCRIPT — WHATSAPP KEYWORD RESPONSE\n\n"
            "IF '1' (NEW TRIP): transfer to UC-001 inbound flow.\n"
            "IF '2' (EXISTING BOOKING): \"Hello {name}, I'm calling about your existing booking "
            "query. Could I take your booking reference?\"\n"
            "IF '3' (VISA HELP): \"Hello {name}, calling about your visa query. Destination and "
            "nationality please?\"\n"
            "IF '4' (URGENT): Immediate callback — P1, no delay. Follow UC-013 emergency script.\n"
            "IF '5' (SPEAK TO AGENT): Assign next available agent. Call within 5 minutes."
        ),
        "automation": [
            "Keyword '1' or 'NEW' → tag as LEAD → trigger UC-001 flow",
            "Keyword '2' or 'BOOKING' → lookup customer by phone → pull booking",
            "Keyword '4' or 'URGENT' → P1 flag → agent assigned → call within 5 min",
            "Outside hours → queue + OOTO → first-in-queue next morning 9AM",
            "After 3 unrecognised inputs → force-assign to human agent",
        ],
    },

    "UC-003": {
        "title":    "Quote Follow-Up — No Response Sequence (24 / 48 / 72 hrs)",
        "category": "enquiry",
        "priority": "P2",
        "sla":      "Automated at T+24h / T+48h / T+72h",
        "channels": ["email", "whatsapp", "sms", "voice"],
        "trigger":  "Quote sent with no customer response after 24 hours",
        "schedule": {"anchor": "quote_sent", "offset_minutes": 24*60},
        "merge_vars": [
            "name","ref","destination","amount","quote_date","expiry_date",
            "agent_name","agent_phone","deposit","company_name","phone",
        ],
        "email_subject": "Your {destination} travel quote — still available! [Ref: {ref}]",
        "email_body": (
            "Dear {name},\n\n"
            "I wanted to follow up on the personalised {destination} itinerary sent on {quote_date}.\n\n"
            "Your proposal [Ref: {ref}] for {amount} per person is still available and I'd love to "
            "help you secure those dates.\n\n"
            "I'm very happy to:\n"
            "  • Adjust the hotel category to fit a different budget\n"
            "  • Modify travel dates if the current ones don't work\n"
            "  • Add or remove experiences from the itinerary\n"
            "  • Explore 0% EMI payment options over 3–6 months\n"
            "  • Hold your preferred hotels tentatively (no charge for 48 hours)\n\n"
            "THE QUOTE IS VALID UNTIL: {expiry_date}\n\n"
            "Simply reply to this email, call me on {agent_phone}, or WhatsApp me directly.\n\n"
            "Best regards,\n{agent_name} | {company_name}\nDirect: {agent_phone}"
        ),
        "whatsapp": (
            "Hi {name}! Just checking in on your *{destination}* quote from {quote_date}.\n\n"
            "Ref: *{ref}*\n"
            "Price: {amount} per person\n"
            "Valid until: *{expiry_date}*\n\n"
            "Happy to adjust anything — dates, hotels, budget, or payment plan!\n\n"
            "Shall I hold your preferred hotels while you decide? No charge for 48 hours."
        ),
        "sms": (
            "Hi {name}, following up on {destination} quote [{ref}] valid until {expiry_date}. "
            "Changes needed? Call {phone} or reply here. {company_name}"
        ),
        "phone_script": (
            "FOLLOW-UP CALL — 48 HRS POST QUOTE\n\n"
            "OPENING: \"Hello {name}, this is {agent_name} from {company_name}. I sent you a "
            "{destination} proposal a couple of days ago — do you have 2 minutes to go through it?\"\n\n"
            "OBJECTION HANDLING:\n"
            "  Price → \"Shall we adjust hotel category or dates?\"\n"
            "  Dates → \"What dates work better? I can re-price instantly.\"\n"
            "  Need more time → \"Of course — valid until {expiry_date}.\"\n"
            "  Comparing → \"What matters most in choosing a travel partner?\"\n\n"
            "CLOSE: \"Shall I place a tentative hold on your dates? Holds are free for 48 hours.\""
        ),
        "automation": [
            "T+24h: WhatsApp follow-up → tag as 'warm lead'",
            "T+48h: Agent personal call → log outcome",
            "T+72h: Final email + SMS → tag as 'cool lead'",
            "T+7d: Move to 30-day nurture sequence",
            "Quote expiry –24h: 'Last chance' WhatsApp alert",
        ],
    },

    # ════════════════════════════════════════════════════════════
    # SECTION B — Booking & Payment
    # ════════════════════════════════════════════════════════════
    "UC-004": {
        "title":    "Booking Confirmation — Deposit Payment Received",
        "category": "booking",
        "priority": "P1",
        "sla":      "< 10 minutes",
        "channels": ["email", "whatsapp", "sms", "voice"],
        "trigger":  "Deposit payment successfully processed via any payment method",
        "schedule": {"anchor": "booking_confirmed", "offset_minutes": 0},
        "merge_vars": [
            "name","ref","lead_name","destination","departure_date","return_date",
            "nights","pax","deposit","balance","balance_due_date","payment_link",
            "coordinator_name","coord_phone","grand_total","package_type","email",
            "flight_out","origin","dest_city","dep_time","flight_ret","dep_time2",
            "hotel_list","payment_date","visa_deadline","company_name",
        ],
        "email_subject": "Booking Confirmed — {destination} Trip [{ref}] | {company_name}",
        "email_body": (
            "Dear {name},\n\nWonderful news — your {destination} adventure is officially booked!\n\n"
            "BOOKING CONFIRMATION\n"
            "════════════════════════════════\n"
            "Booking Reference : {ref}\n"
            "Lead Traveller    : {lead_name}\n"
            "Departure         : {departure_date}\n"
            "Return            : {return_date}\n"
            "Duration          : {nights} Nights\n"
            "Travellers        : {pax}\n"
            "Package Type      : {package_type}\n"
            "════════════════════════════════\n\n"
            "FLIGHT DETAILS\n"
            "Outbound : {flight_out} | {origin} to {dest_city} | Dep: {dep_time}\n"
            "Return   : {flight_ret} | {dest_city} to {origin} | Dep: {dep_time2}\n\n"
            "ACCOMMODATION CONFIRMED\n{hotel_list}\n\n"
            "PAYMENT SUMMARY\n"
            "════════════════════════════════\n"
            "Package Total (incl. GST) : {grand_total}\n"
            "Deposit Paid              : {deposit} on {payment_date}\n"
            "Balance Due               : {balance} by {balance_due_date}\n"
            "Payment Link              : {payment_link}\n"
            "════════════════════════════════\n\n"
            "YOUR DEDICATED COORDINATOR\n"
            "{coordinator_name} | {coord_phone}\n"
            "Available Mon–Sat, 9AM–7PM IST\n\n"
            "{company_name} Reservations Team"
        ),
        "whatsapp": (
            "BOOKING CONFIRMED — {company_name}!\n\n"
            "Congratulations {name}! Your {destination} trip is officially booked!\n\n"
            "Ref: *{ref}*\n"
            "Departure: *{departure_date}*\n"
            "Return: *{return_date}*\n"
            "Duration: *{nights} Nights*\n"
            "Travellers: *{pax}*\n\n"
            "PAYMENTS:\n"
            " Deposit: {deposit} received\n"
            " Balance: {balance} due by {balance_due_date}\n"
            " Pay link: {payment_link}\n\n"
            "Coordinator: *{coordinator_name}* — {coord_phone}\n"
            "Full confirmation emailed to {email}"
        ),
        "sms": (
            "CONFIRMED! {company_name}: {destination} trip {ref} booked. Dep {departure_date}. "
            "Balance {balance} due {balance_due_date}. Coord: {coordinator_name} {coord_phone}"
        ),
        "phone_script": (
            "BOOKING CONFIRMATION WELCOME CALL\n\n"
            "\"Hello {name}! This is {coordinator_name} from {company_name}. I'm calling with the "
            "best news — your {destination} trip is now officially confirmed! How are you feeling?\"\n\n"
            "KEY POINTS TO COVER:\n"
            "  1. Full confirmation emailed to {email}\n"
            "  2. Balance of {balance} due by {balance_due_date} — payment link in email\n"
            "  3. Visa deadline: {visa_deadline}\n"
            "  4. Full travel pack arrives 14 days before departure\n"
            "  5. I am your dedicated coordinator from now on — {coord_phone}\n\n"
            "\"Wonderful! Counting down with you — {destination} is going to be incredible!\""
        ),
        "automation": [
            "Payment confirmed → generate booking PDF → send all channels within 10 min",
            "Balance due –7 days → trigger UC-005 sequence",
            "Booking created → trigger visa nationality check (UC-018 logic)",
            "30 days pre-departure → trigger UC-008",
            "Honeymoon booking type → trigger UC-020 within 24 hrs",
            "Group 6+ pax → auto-apply group discount → notify agent",
        ],
    },

    "UC-005": {
        "title":    "Payment Reminder — Balance Due (7-Day / 3-Day / Overdue)",
        "category": "booking",
        "priority": "P1",
        "sla":      "Automated: D-7, D-3, D-0, D+1",
        "channels": ["email", "whatsapp", "sms", "voice"],
        "trigger":  "Balance payment due in 7 days, 3 days, on due date, or 1 day overdue",
        "schedule": {"anchor": "balance_due", "offset_minutes": -7*24*60},
        "merge_vars": [
            "name","ref","destination","departure_date","balance","due_date","payment_link",
            "days_label","urgency_line","bank_details","overdue_warning","cancellation_warning",
            "due_phrase","overdue_note","whatsapp_num","phone","company_name","agent",
            "extended_deadline",
        ],
        "email_subject": "Balance Payment Due {days_label} — {destination} Trip [{ref}]",
        "email_body": (
            "Dear {name},\n\n{urgency_line}\n\n"
            "PAYMENT DETAILS\n"
            "════════════════════════════════\n"
            "Booking Reference : {ref}\n"
            "Destination       : {destination}\n"
            "Departure Date    : {departure_date}\n"
            "Balance Amount    : {balance}\n"
            "Due Date          : {due_date}\n"
            "{overdue_warning}\n"
            "════════════════════════════════\n\n"
            "PAYMENT OPTIONS\n"
            "  • Secure payment link: {payment_link}\n"
            "  • Cards (Visa, Mastercard, Amex, RuPay)\n"
            "  • UPI (GPay, PhonePe, Paytm, BHIM)\n"
            "  • Net Banking (all major banks)\n"
            "  • 0% EMI — 3 months (select cards)\n"
            "  • Bank Transfer: {bank_details}\n\n"
            "{cancellation_warning}\n\n"
            "Need help? Call {phone} or WhatsApp {whatsapp_num}.\n\n"
            "{company_name} Accounts Team"
        ),
        "whatsapp": (
            "Payment Reminder — {company_name}\n\n"
            "Hi {name}! Your balance is due *{due_phrase}*.\n\n"
            "Ref: *{ref}*\nAmount: *{balance}*\nDue: *{due_date}*\n\n"
            "Pay now: {payment_link}\n\n"
            "Accepted: UPI · Card · Net Banking · 0% EMI\n\n"
            "{overdue_note}\n\nNeed help? Just reply here!"
        ),
        "sms": "{company_name}: Balance {balance} for {ref} due {due_date}. Pay: {payment_link} Help: {phone}",
        "phone_script": (
            "PAYMENT REMINDER / OVERDUE CALL\n\n"
            "7-DAY: \"Hello {name}, {agent} from {company_name}. Friendly heads-up — balance of "
            "{balance} for your {destination} trip is due {due_date}. Can I help make this easier?\"\n\n"
            "3-DAY: \"Hello {name}, your balance of {balance} is due in just 3 days on {due_date}. "
            "To protect your booking, please pay before {due_date}.\"\n\n"
            "OVERDUE: \"Hello {name}, your balance of {balance} was due {due_date} and we haven't "
            "received it yet. Is everything okay? If payment isn't received by {extended_deadline}, "
            "we may have to release your reservations.\""
        ),
        "automation": [
            "D-7: Email + WhatsApp reminder",
            "D-3: Email + WhatsApp + SMS reminder",
            "D-0: WhatsApp + SMS at 9AM IST",
            "D+1: Mark OVERDUE → all channels + P1 agent call",
            "D+3: Manager review → potential cancellation flag",
            "Payment received → cancel reminders → send receipt",
        ],
    },

    "UC-006": {
        "title":    "Booking Amendment — Change Request Processing",
        "category": "booking",
        "priority": "P2",
        "sla":      "Acknowledge < 1 hour; Resolution < 4 hours",
        "channels": ["email", "whatsapp", "sms", "voice"],
        "trigger":  "Customer requests date change, hotel upgrade/downgrade, pax change or modification",
        "schedule": {"anchor": "amendment_request", "offset_minutes": 0},
        "merge_vars": [
            "name","ref","amendment_type","original_detail","new_detail","fee","new_total",
            "additional_due","additional_due_date","processed_date","destination","email",
            "fee_note","price_diff_note","additional_payment_link","phone","reason",
            "alternative","company_name",
        ],
        "email_subject": "Amendment Confirmed — {amendment_type} | Booking {ref}",
        "email_body": (
            "Dear {name},\n\nWe have successfully processed your amendment for booking {ref}.\n\n"
            "AMENDMENT DETAILS\n"
            "════════════════════════════════\n"
            "Amendment Type : {amendment_type}\n"
            "Original       : {original_detail}\n"
            "Updated To     : {new_detail}\n"
            "Processed On   : {processed_date}\n"
            "════════════════════════════════\n\n"
            "FINANCIAL IMPACT\n"
            "Amendment Fee     : {fee} ({fee_note})\n"
            "Price Difference  : {price_diff_note}\n"
            "New Grand Total   : {new_total}\n"
            "Additional Due    : {additional_due} by {additional_due_date}\n"
            "{additional_payment_link}\n\n"
            "Please find the revised confirmation document attached.\n\n"
            "{company_name} Reservations Team"
        ),
        "whatsapp": (
            "Amendment Confirmed\n\nHi {name}! Your change has been processed.\n\n"
            "Ref: *{ref}*\nChange: {amendment_type}\n"
            " Original: {original_detail}\n Updated: *{new_detail}*\n"
            "Amendment fee: {fee}\n"
            "Additional due: {additional_due} by {additional_due_date}\n\n"
            "Updated confirmation emailed to {email}."
        ),
        "sms": (
            "{company_name}: Amendment confirmed for {ref}. {amendment_type} updated. "
            "Fee {fee}. Extra {additional_due} due {additional_due_date}. {phone}"
        ),
        "phone_script": (
            "AMENDMENT CALL\n\n"
            "\"Hello {name}, I'm calling about your change request for your {destination} booking. "
            "I've checked and I can confirm we can process the {amendment_type}. The amendment fee "
            "is {fee} and your new total is {new_total}. Shall I confirm this change now?\"\n\n"
            "IF NOT POSSIBLE: \"Unfortunately {reason}. However I have an alternative option: "
            "{alternative}. How does that sound?\""
        ),
        "automation": [
            "Amendment request → auto-acknowledge within 30 min → agent assigned",
            "Check availability → if available → process",
            "Airline/hotel fee → present before confirming",
            "Pax count change → recalculate GST → reissue invoice",
            "Confirmed → revised docs all channels → update CRM",
        ],
    },

    "UC-007": {
        "title":    "Cancellation — Customer-Initiated Trip Cancellation",
        "category": "booking",
        "priority": "P1",
        "sla":      "< 2 hours from request",
        "channels": ["email", "whatsapp", "sms", "voice"],
        "trigger":  "Customer formally requests trip cancellation in writing or by call",
        "schedule": {"anchor": "cancellation", "offset_minutes": 0},
        "merge_vars": [
            "name","ref","destination","today","reason","departure_date","total_paid",
            "cancellation_fee","refund_amount","insurance_hotline","fee_policy","email",
            "agent_name","company_name","phone",
        ],
        "email_subject": "Cancellation Confirmed — {destination} Trip [{ref}] | {company_name}",
        "email_body": (
            "Dear {name},\n\nWe are sorry to hear you need to cancel your {destination} trip.\n\n"
            "CANCELLATION DETAILS\n"
            "════════════════════════════════\n"
            "Booking Reference  : {ref}\n"
            "Cancellation Date  : {today}\n"
            "Cancellation Reason: {reason}\n"
            "Original Departure : {departure_date}\n"
            "════════════════════════════════\n\n"
            "REFUND CALCULATION\n"
            "Total Paid           : {total_paid}\n"
            "Cancellation Charges : {cancellation_fee} ({fee_policy})\n"
            "Refund Amount        : {refund_amount}\n"
            "Refund Timeline      : 5–7 business days (original payment method)\n"
            "Status               : Processing\n\n"
            "INSURANCE NOTE: If cancellation is for a covered reason, contact your insurer at "
            "{insurance_hotline}.\n\n"
            "RE-BOOKING OFFER:\n"
            "  • Rebooking administration fee: WAIVED\n"
            "  • Original pricing honoured for 6 months\n"
            "  • Priority access to your preferred dates\n\n"
            "With regrets,\n{agent_name} | {company_name}"
        ),
        "whatsapp": (
            "Hi {name}, we're sorry you need to cancel your *{destination}* trip.\n\n"
            "Ref: *{ref}* — Cancellation confirmed.\n\n"
            "Refund: *{refund_amount}*\nTimeline: 5–7 business days\n"
            "Full details emailed to {email}\n\n"
            "Insurance queries: {insurance_hotline}\n\n"
            "When you're ready to travel again, we'll waive your rebooking fee."
        ),
        "sms": (
            "{company_name}: Cancellation confirmed {ref}. Refund {refund_amount} in 5-7 days. "
            "Insurance: {insurance_hotline}. Questions: {phone}"
        ),
        "phone_script": (
            "CANCELLATION CALL — EMPATHY FIRST, RETENTION SECOND\n\n"
            "OPENING: \"Hello {name}, I received your cancellation request and wanted to call you "
            "personally before processing anything. Is everything okay?\"\n\n"
            "OFFER ALTERNATIVES FIRST:\n"
            "  • Postpone to different dates? (Protect most of your money)\n"
            "  • Transfer the booking to another family member?\n"
            "  • Put the booking on hold for 6 months?\n\n"
            "IF STILL CANCELLING: \"I completely understand. The refund of {refund_amount} will be "
            "back within 5-7 business days. Insurance hotline is {insurance_hotline}. No rebooking "
            "fees for you whenever you're ready to travel again. Take care of yourself, {name}.\""
        ),
        "automation": [
            "Cancellation request → do NOT auto-process → assign senior agent for personal call",
            "After call → if confirmed → process refund → cancel supplier bookings",
            "Refund initiated → daily status check → notify when cleared",
            "Log cancellation reason → feed into retention analytics",
            "If {company_name} error → full refund + goodwill (manager approval)",
        ],
    },

    # ════════════════════════════════════════════════════════════
    # SECTION C — Pre-Departure
    # ════════════════════════════════════════════════════════════
    "UC-008": {
        "title":    "30-Day Pre-Departure — Visa & Document Action Alert",
        "category": "predep",
        "priority": "P1",
        "sla":      "Automated at D-30 09:00 IST",
        "channels": ["email", "whatsapp", "sms", "voice"],
        "trigger":  "Automated: 30 days before departure_date at 9:00 AM IST",
        "schedule": {"anchor": "departure_date", "offset_minutes": -30*24*60},
        "merge_vars": [
            "name","ref","destination","visa_status","visa_status_banner","visa_action_required",
            "passport_expiry_check","balance_due_date","balance","visa_link","coordinator",
            "fourteen_day_date","three_day_date","visa_email","phone","company_name",
            "visa_whatsapp_status",
        ],
        "email_subject": "Action Required — 30 Days to {destination}! Your Complete Checklist [{ref}]",
        "email_body": (
            "Dear {name},\n\nYour {destination} adventure is just 30 days away!\n\n"
            "VISA STATUS — {visa_status_banner}\n"
            "{visa_action_required}\n\n"
            "COMPLETE PRE-DEPARTURE CHECKLIST\n"
            "════════════════════════════════\n"
            "DOCUMENTS\n"
            "  □ Passport valid 6+ months beyond return date ({passport_expiry_check})\n"
            "  □ Visa approved and printed ({visa_status})\n"
            "  □ Travel insurance in hand\n"
            "  □ Vaccination certificates if required\n"
            "  □ Medication with doctor's letter if applicable\n\n"
            "FINANCIAL\n"
            "  □ Balance payment made by {balance_due_date}\n"
            "  □ Foreign currency / forex card loaded\n"
            "  □ Bank notified of travel dates\n"
            "  □ Emergency cash in local currency\n\n"
            "UPCOMING FROM US\n"
            "  • 14-Day Brief   : {fourteen_day_date}\n"
            "  • 3-Day Brief    : {three_day_date}\n"
            "  • Departure Day  : WhatsApp + SMS bon voyage\n\n"
            "Visa Help: {visa_email} | {phone}\n\n"
            "{company_name} Pre-Departure Team"
        ),
        "whatsapp": (
            "30 Days to {destination}!\n\nHi {name}! Your trip is almost here!\n\n"
            "VISA CHECK\n{visa_whatsapp_status}\nApply: {visa_link}\nProcessing: 3–5 working days\n\n"
            "ACTION CHECKLIST:\n"
            " □ Passport valid 6+ months?\n"
            " □ Visa sorted?\n"
            " □ Travel insurance in hand?\n"
            " □ Balance paid by {balance_due_date}?\n"
            " □ Currency organised?\n\n"
            "Reply *VISA DONE* when sorted or *HELP* for assistance!\nRef: {ref}"
        ),
        "sms": (
            "{company_name}: 30 days to {destination}! Ref:{ref}. Visa sorted? Apply: {visa_link}. "
            "Balance {balance} due {balance_due_date}. Help: {phone}"
        ),
        "phone_script": (
            "30-DAY CHECK-IN CALL\n\n"
            "\"Hello {name}! It's {coordinator} from {company_name}. Just 30 days until your "
            "{destination} trip!\n\n"
            "VISA: Has your visa been sorted?\nPASSPORT: When does your passport expire?\n"
            "PAYMENT: Your balance of {balance} is due by {balance_due_date}. All good?\n"
            "HEALTH: Had any required vaccinations for {destination}?\n\n"
            "I'll send your complete travel pack in 2 weeks with tickets, vouchers, and a full guide.\""
        ),
        "automation": [
            "D-30: Trigger email + WhatsApp + SMS at 9AM IST",
            "D-30: If visa_status = null → URGENT visa alert as P1",
            "D-30: If balance unpaid → concurrent UC-005",
            "D-27: If no 'VISA DONE' reply → follow-up WhatsApp",
            "D-14: Trigger UC-009",
        ],
    },

    "UC-009": {
        "title":    "14-Day Pre-Departure — Full Travel Pack Dispatch",
        "category": "predep",
        "priority": "P1",
        "sla":      "Automated at D-14 09:00 IST",
        "channels": ["email", "whatsapp", "sms", "voice"],
        "trigger":  "Automated: 14 days before departure at 9:00 AM IST",
        "schedule": {"anchor": "departure_date", "offset_minutes": -14*24*60},
        "merge_vars": [
            "name","ref","destination","travel_month","weather_summary","weather_brief",
            "clothing_recommendation","clothing_tip","packing_essentials","destination_packing",
            "destination_upper","local_currency","currency_code","currency_tip","exchange_rate",
            "forex_advice","atm_advice","tipping_guide","local_emergency","hospital_name",
            "hospital_address","insurance_hotline","app_list","coordinator","coord_hours",
            "coord_phone","emergency_line","email","company_name",
        ],
        "email_subject": "Your Complete {destination} Travel Pack — 14 Days to Go! [{ref}]",
        "email_body": (
            "Dear {name},\n\nJust 2 weeks to go! Your complete travel pack is attached.\n\n"
            "DOCUMENTS ATTACHED\n"
            "════════════════════════════════\n"
            "  • E-Tickets (all flights)\n  • Hotel Vouchers (all properties)\n"
            "  • Transfer Confirmation Sheets\n  • Day-by-Day Detailed Itinerary\n"
            "  • Emergency Contact Card\n  • {destination} Destination Guide\n"
            "  • Local Map and Key Locations PDF\n"
            "════════════════════════════════\n\n"
            "PLEASE SAVE ALL DOCUMENTS OFFLINE — internet may be limited.\n\n"
            "WEATHER FORECAST — {destination}, {travel_month}\n"
            "{weather_summary}\nRecommended clothing: {clothing_recommendation}\n\n"
            "PACKING ESSENTIALS\n{packing_essentials}\n\n"
            "Destination-Specific Items:\n{destination_packing}\n\n"
            "MONEY IN {destination_upper}\n"
            "Currency     : {local_currency} ({currency_code})\n"
            "Exchange Rate: {exchange_rate}\nBest Exchange: {forex_advice}\n"
            "ATM Tip      : {atm_advice}\nTipping Guide: {tipping_guide}\n\n"
            "HEALTH AND SAFETY\n"
            "Local Emergency : {local_emergency}\n"
            "Nearest Hospital: {hospital_name}, {hospital_address}\n"
            "Insurance 24/7  : {insurance_hotline}\n\n"
            "APPS TO DOWNLOAD BEFORE FLYING\n{app_list}\n\n"
            "Your coordinator {coordinator} is available {coord_hours}.\n\nBon voyage!\n{company_name}"
        ),
        "whatsapp": (
            "14 Days to {destination}! Travel pack ready!\n\nHi {name}! 2 weeks to go!\n\n"
            "SENT TO {email}:\n  E-Tickets\n  Hotel Vouchers\n  Full Itinerary\n"
            "  Emergency Contacts\n  {destination} Guide\n\n"
            "Weather: {weather_brief}\nCurrency tip: {currency_tip}\n\n"
            "SAVE NOW: Emergency no. *{local_emergency}*\n\n"
            "Download offline: Google Maps for {destination}\n\nAny questions? Reply here!"
        ),
        "sms": (
            "{company_name}: 14 days to {destination}! Ref:{ref}. Full travel pack emailed. "
            "SAVE emergency no: {local_emergency}. Coordinator: {coordinator} {coord_phone}"
        ),
        "phone_script": (
            "14-DAY COORDINATOR CALL\n\n"
            "\"Hello {name}! It's {coordinator} from {company_name}! Just 14 days to go!\n\n"
            "I've sent your complete travel pack to {email} — tickets, hotel vouchers, full "
            "itinerary, and a destination guide.\n\n"
            "Please save all documents offline. And save our 24/7 emergency line right now: "
            "{emergency_line}. Local emergency in {destination}: {local_emergency}.\n\n"
            "Any dietary requirements or hotel requests? Any experiences to add? Weather will be "
            "{weather_brief} so pack {clothing_tip}.\""
        ),
        "automation": [
            "D-14: Generate/attach all documents → send all channels at 9AM",
            "D-14: If any hotel voucher missing → alert ops team P1",
            "D-14: If visa_status ≠ APPROVED → URGENT escalation",
            "D-14: Check all flight PNRs confirmed",
            "D-3: Trigger UC-010",
        ],
    },

    "UC-010": {
        "title":    "3-Day Pre-Departure — Final Brief & Emergency Numbers",
        "category": "predep",
        "priority": "P1",
        "sla":      "Automated at D-3 09:00 IST",
        "channels": ["email", "whatsapp", "sms", "voice"],
        "trigger":  "Automated: 3 days before departure at 9:00 AM IST",
        "schedule": {"anchor": "departure_date", "offset_minutes": -3*24*60},
        "merge_vars": [
            "name","ref","destination","flight_number","origin","dest_city","terminal",
            "checkin_time","dep_time","arrive_by_time","emergency_line","coordinator",
            "coord_phone","driver_name","driver_phone","hotel_name","hotel1_phone",
            "insurance_hotline","local_emergency","arrival_airport","name_on_sign",
            "vehicle_type","plate_number","agent_name","company_name",
        ],
        "email_subject": "Final Pre-Departure Brief — {destination} in 3 Days! [{ref}]",
        "email_body": (
            "Dear {name},\n\nThe countdown is ON — just 3 days until your {destination} adventure!\n\n"
            "YOUR DEPARTURE DETAILS\n"
            "════════════════════════════════\n"
            "Flight          : {flight_number}\nRoute           : {origin} to {dest_city}\n"
            "Terminal        : Terminal {terminal}\nCheck-in Opens  : {checkin_time}\n"
            "Departs         : {dep_time}\nArrive at airport by: {arrive_by_time}\n"
            "════════════════════════════════\n\n"
            "SAVE THESE NUMBERS IN YOUR PHONE RIGHT NOW\n"
            "════════════════════════════════\n"
            "{company_name} 24/7 Emergency : {emergency_line}\n"
            "Your Coordinator {coordinator}: {coord_phone}\n"
            "Your Driver {driver_name}     : {driver_phone}\n"
            "Hotel — {hotel_name}          : {hotel1_phone}\n"
            "Travel Insurance 24/7         : {insurance_hotline}\n"
            "Local Emergency {destination} : {local_emergency}\n"
            "════════════════════════════════\n\n"
            "AIRPORT ARRIVAL TRANSFER\n"
            "{driver_name} will meet you at {arrival_airport} Arrivals with a sign showing: "
            "{name_on_sign}\nVehicle: {vehicle_type} | Registration: {plate_number}\n\n"
            "FINAL CHECKLIST\n"
            "  □ Passport + visa printout in carry-on bag\n"
            "  □ E-tickets downloaded offline on phone\n"
            "  □ Hotel address saved offline for taxi if needed\n"
            "  □ Foreign currency / forex card loaded and tested\n"
            "  □ Travel insurance documents accessible\n"
            "  □ Emergency numbers saved in phone\n"
            "  □ WhatsApp notifications turned ON\n"
            "  □ Medication in carry-on — NOT checked baggage\n\n"
            "Have an absolutely incredible trip!\n{agent_name} | {company_name}"
        ),
        "whatsapp": (
            "3 Days to {destination}!\n\nHi {name}! Almost time!\n\n"
            "YOUR FLIGHT:\n*{flight_number}* | Terminal {terminal}\n"
            "Departs: *{dep_time}*\nBe at airport by: *{arrive_by_time}*\n\n"
            "SAVE THESE NOW:\n"
            " Emergency 24/7: *{emergency_line}*\n"
            " Driver {driver_name}: *{driver_phone}*\n"
            " Hotel: *{hotel1_phone}*\n"
            " Insurance: *{insurance_hotline}*\n\n"
            "{driver_name} meets you at {arrival_airport} Arrivals with your name sign.\n\n"
            "Checklist: Passport + visa | Currency | Notifications ON\n\nSO excited for you!"
        ),
        "sms": (
            "{company_name}: 3 days to {destination}! Flight {flight_number} dep {dep_time} "
            "T{terminal}. Be there by {arrive_by_time}. Driver {driver_name}: {driver_phone}. "
            "24/7: {emergency_line}"
        ),
        "phone_script": (
            "3-DAY FINAL CALL\n\n"
            "\"Hello {name}! Just 3 days to go!\n\nYour flight is {flight_number} departing at "
            "{dep_time} from Terminal {terminal}. Please be there by {arrive_by_time}.\n\n"
            "Driver {driver_name} will be at Arrivals with your name. Number: {driver_phone}. "
            "Our 24/7 emergency: {emergency_line}.\n\nHave the most incredible trip!\""
        ),
        "automation": [
            "D-3: Send all channels at 9AM IST",
            "D-3: Check all PNR statuses → flight change → alert agent",
            "D-3: Driver dispatch confirmation sent",
            "D-3: Hotel arrival notification with expected check-in",
            "D-0: Trigger UC-011 at 6AM local time",
        ],
    },

    "UC-011": {
        "title":    "Departure Day — Bon Voyage Message",
        "category": "predep",
        "priority": "P2",
        "sla":      "06:00 local time on departure day",
        "channels": ["whatsapp", "sms"],
        "trigger":  "Automated: Day of departure at 6:00 AM local time",
        "schedule": {"anchor": "departure_date", "offset_minutes": 6*60},
        "merge_vars": [
            "name","destination","flight_number","dep_time","terminal","arrive_by_time",
            "driver_name","driver_phone","emergency_line","company_name",
        ],
        "whatsapp": (
            "Today's the day, {name}! Your *{destination}* adventure starts RIGHT NOW!\n\n"
            "Flight *{flight_number}*\nDeparts: *{dep_time}*\nTerminal: *{terminal}*\n"
            "Be there by: *{arrive_by_time}*\n\n"
            "Driver *{driver_name}* is ready at Arrivals: *{driver_phone}*\n\n"
            "We're with you 24/7: *{emergency_line}*\n\n"
            "Have the most incredible journey! {destination} is waiting for you!\n\n"
            "{company_name} — always here if you need us"
        ),
        "sms": (
            "BON VOYAGE {name}! Flight {flight_number} dep {dep_time} T{terminal}. Be there by "
            "{arrive_by_time}. Driver {driver_name}: {driver_phone}. 24/7: {emergency_line}. "
            "Enjoy {destination}! {company_name}"
        ),
        "phone_script": (
            "[No scheduled outbound call on departure day]\n\n"
            "INBOUND HANDLING — DEPARTURE DAY:\n"
            "Rule: ZERO hold times. Any call from departing customer = P1.\n\n"
            "\"Hello {name}! How can I help you on this exciting day?!\"\n"
            "Last-minute query: Resolve immediately. No transfers.\n"
            "Lost passport: Activate emergency protocol → nearest embassy.\n"
            "Flight concern: Live flight status → advise immediately.\n"
            "Transfer concern: Contact driver directly while customer on line."
        ),
        "automation": [
            "D-0 at 6AM: Send WhatsApp + SMS",
            "D-0: Set customer status IN-TRANSIT in CRM",
            "D-0: Begin flight API monitoring → auto-trigger UC-014 on delay",
            "D-0: Driver dispatch confirmation with updated flight ETA",
            "D-0: Hotel arrival notification with expected check-in",
        ],
    },

    # ════════════════════════════════════════════════════════════
    # SECTION D — In-Trip Support
    # ════════════════════════════════════════════════════════════
    "UC-012": {
        "title":    "Daily In-Trip Check-In — Every Morning",
        "category": "intrip",
        "priority": "P2",
        "sla":      "Daily at 8:00 AM local time",
        "channels": ["whatsapp", "voice"],
        "trigger":  "Every day at 8:00 AM local destination time during trip",
        "schedule": {"anchor": "trip_day", "offset_minutes": 8*60},
        "merge_vars": [
            "name","day_number","total_days","hotel_name","todays_schedule","city","weather",
            "driver_name","driver_phone","tonight_hotel","coordinator","todays_highlight",
            "pickup_time","company_name",
        ],
        "whatsapp": (
            "Good morning {name}!\n\n{company_name} — Day {day_number} of {total_days} Check-In\n\n"
            "Hope you rested wonderfully at *{hotel_name}*!\n\n"
            "TODAY'S PLAN:\n{todays_schedule}\n\n"
            "Weather in {city}: {weather}\n"
            "Your driver today: *{driver_name}* — {driver_phone}\n"
            "Tonight's hotel: *{tonight_hotel}*\n\n"
            "Reply *ALL GOOD* to carry on enjoying your day!\n"
            "Or message us any time — we're always here."
        ),
        "phone_script": (
            "DAILY VIP CHECK-IN CALL (VIP tier only)\n\n"
            "\"Good morning {name}! It's {coordinator} from {company_name}. Quick check-in — how "
            "was yesterday? Everything go smoothly?\"\n\n"
            "\"Today you have {todays_highlight} — driver {driver_name} collects you at "
            "{pickup_time}.\"\n\n"
            "\"Anything I can arrange — restaurant reservation, special request, itinerary change?\"\n\n"
            "RULE: Keep VIP calls under 3 minutes unless customer wants to talk."
        ),
        "automation": [
            "Each trip day 7:50AM local: generate schedule → send WhatsApp at 8AM",
            "Reply contains ISSUE/PROBLEM/HELP → escalate to agent immediately",
            "No reply by 10AM → optional wellness check for VIP",
            "Driver changes → auto-update check-in message",
            "VIP: agent call replaces WhatsApp check-in",
        ],
    },

    "UC-013": {
        "title":    "Emergency Response — In-Trip Crisis Protocol",
        "category": "intrip",
        "priority": "P1 CRITICAL",
        "sla":      "< 5 minutes initial | < 15 minutes resolution plan",
        "channels": ["voice", "whatsapp", "sms"],
        "trigger":  "Customer reports emergency: medical, stranded, theft, lost documents, safety",
        "schedule": {"anchor": "emergency", "offset_minutes": 0},
        "merge_vars": [
            "name","ref","location","issue_type","actions_taken","safe_location","coordinator",
            "local_emergency","medical_hotline","hospital","insurance_hotline","passport_no",
            "passport_expiry","embassy","embassy_address","embassy_phone","eta",
            "safe_waiting_location","alternative_hotel","police_station","agent","update",
            "next_steps","company_name",
        ],
        "whatsapp": (
            "EMERGENCY RESPONSE — {company_name}\n\n"
            "Hi {name}, I have received your urgent message.\n\n"
            "I am personally handling this RIGHT NOW.\n\n"
            "Your location: {location}\nIssue: {issue_type}\n\n"
            "IMMEDIATELY ACTIONED:\n{actions_taken}\n\n"
            "Stay at {safe_location} and stay calm.\n\nI am calling you in the next 3 minutes.\n\n"
            "If life-threatening: call local emergency *{local_emergency}* immediately.\n\n"
            "— {coordinator}, {company_name} Emergency Team"
        ),
        "sms": (
            "URGENT {company_name}: Received your emergency. {coordinator} calling NOW. Local "
            "emergency: {local_emergency}. Medical: {medical_hotline}. Stay calm. Ref:{ref}"
        ),
        "phone_script": (
            "EMERGENCY CALL SCRIPT — P1 CRITICAL\n\n"
            "OPENING (calm, controlled): \"{name}, this is {coordinator} from {company_name}. "
            "I am here. What is happening right now?\"\n\n"
            "MEDICAL: \"I am arranging medical assistance right now. Nearest hospital: {hospital}. "
            "I am also calling your travel insurance on another line. Need an ambulance? I will "
            "stay on the line / call back every 10 minutes until resolved.\"\n\n"
            "THEFT/ROBBERY: \"First — are you physically safe? That is all that matters right now. "
            "Report to local police within 24 hours for insurance. Nearest: {police_station}. "
            "Embassy: {embassy}.\"\n\n"
            "LOST PASSPORT: \"Your passport details on file: Number {passport_no}, expiry "
            "{passport_expiry}. Nearest embassy: {embassy_address}, phone {embassy_phone}. "
            "Emergency travel documents can be issued in 24-48 hours.\"\n\n"
            "STRANDED: \"Where exactly are you? Alternative vehicle arranged — ETA {eta}. Wait at "
            "{safe_waiting_location}.\"\n\n"
            "HOTEL ISSUE: \"Calling the hotel manager directly. If not resolved in 30 minutes, "
            "I will relocate you to {alternative_hotel} at our cost.\"\n\n"
            "FOLLOW-UP: Call every 15–30 min until resolved. File incident report within 2 hrs. "
            "Brief operations director if P1."
        ),
        "automation": [
            "Keywords HELP/EMERGENCY/URGENT on WhatsApp → P1 → agent alert within 60s",
            "Inbound emergency call → override queue → immediate answer",
            "P1 incident → auto-alert operations director via Slack",
            "Medical incident → trigger insurance partner API notification",
            "All emergency interactions → mandatory incident register entry",
        ],
    },

    "UC-014": {
        "title":    "Flight Delay — Real-Time Alert & Rebooking",
        "category": "intrip",
        "priority": "P1",
        "sla":      "< 5 minutes from API detection",
        "channels": ["whatsapp", "sms", "voice"],
        "trigger":  "Flight delay > 45 min OR cancellation detected via flight tracking API",
        "schedule": {"anchor": "flight_delay", "offset_minutes": 0},
        "merge_vars": [
            "name","flight_number","origin","destination","original_time","new_time","delay_reason",
            "cancellation_note","rebooking_option","driver_name","coordinator","emergency_line",
            "delay_mins","alt_flight_time","alt_airline","company_name",
        ],
        "whatsapp": (
            "FLIGHT UPDATE — {company_name}\n\n"
            "Hi {name}! We have detected a change to your flight.\n\n"
            "Flight: *{flight_number}*\nRoute: {origin} to {destination}\n"
            "Original departure: {original_time}\n*New departure: {new_time}*\n"
            "Reason: {delay_reason}\n{cancellation_note}\n\n"
            "WE HAVE ALREADY:\n  • Notified your hotel about delayed arrival\n"
            "  • Updated your driver {driver_name}\n  • Checked for alternative flight options\n"
            "{rebooking_option}\n\n"
            "No action needed from you unless you want alternatives.\n\n"
            "Reply *ALTERNATIVES* to see other flight options.\n"
            "Reply *CALL ME* to speak with someone.\n\n— {company_name} Flight Support"
        ),
        "sms": (
            "FLIGHT ALERT {name}: {flight_number} now departs {new_time} (was {original_time}). "
            "Hotel and driver notified. No action needed. Help: {emergency_line}. {company_name}"
        ),
        "phone_script": (
            "FLIGHT DELAY PROACTIVE CALL — Call before the customer does\n\n"
            "\"Hello {name}, this is {coordinator} from {company_name}. Our flight tracking has "
            "detected a change to your flight {flight_number}.\n\n"
            "New departure time is {new_time} — a {delay_mins}-minute delay.\n\n"
            "I have already: notified your hotel, updated your driver, and checked alternatives.\n\n"
            "[If significant]: 'Alternative flight at {alt_flight_time} on {alt_airline}. Switch?'\n\n"
            "Situations like this are exactly why you have us. We are handling everything.\""
        ),
        "automation": [
            "FlightAware API polling every 10 min for all active departures",
            "Delay > 45 min OR cancellation → WhatsApp + SMS immediately",
            "Delay > 2 hrs → hotel API call → flag late arrival",
            "Delay > 2 hrs → driver notification → recalculate pickup",
            "Cancellation → pull alternatives → present within 15 min",
            "Delay > 4 hrs → compensation check → brief agent",
        ],
    },

    # ════════════════════════════════════════════════════════════
    # SECTION E — Post-Trip
    # ════════════════════════════════════════════════════════════
    "UC-015": {
        "title":    "Welcome Home — Post-Trip Follow-Up & Loyalty Activation",
        "category": "posttrip",
        "priority": "P2",
        "sla":      "48 hours after return",
        "channels": ["email", "whatsapp", "sms", "voice"],
        "trigger":  "Automated: 48 hours after return_date",
        "schedule": {"anchor": "return_date", "offset_minutes": 48*60},
        "merge_vars": [
            "name","destination","survey_link","google_review_link","tripadvisor_link",
            "facebook_link","loyalty_credit","total_balance","tier","tier_perks","referral_amount",
            "referral_code","referral_link","destination_suggestions","agent_name","agent",
            "company_name",
        ],
        "email_subject": "Welcome Home, {name}! How was {destination}? | {company_name}",
        "email_body": (
            "Dear {name},\n\nWelcome home! We hope you have arrived safely and are still glowing "
            "from your incredible {destination} journey.\n\n"
            "SHARE YOUR EXPERIENCE (takes 2 minutes)\n{survey_link}\n\n"
            "REVIEW US — it would mean the world\n"
            "  • Google Review : {google_review_link}\n"
            "  • TripAdvisor   : {tripadvisor_link}\n"
            "  • Facebook      : {facebook_link}\n\n"
            "YOUR LOYALTY REWARDS\n"
            "════════════════════════════════\n"
            "Travel Credit Earned : {loyalty_credit}\nYour Total Balance   : {total_balance}\n"
            "Tier Status          : {tier} ({tier_perks})\n"
            "════════════════════════════════\n\n"
            "REFER A FRIEND — EARN CASH\n"
            "Earn {referral_amount} for every friend who books with us!\n"
            "Your unique referral code : {referral_code}\nShare link                : {referral_link}\n\n"
            "WHERE NEXT?\n{destination_suggestions}\n\n"
            "With genuine gratitude,\n{agent_name} | {company_name}"
        ),
        "whatsapp": (
            "Welcome home, {name}!\n\nHope {destination} was absolutely magical!\n\n"
            "We'd love to hear how it went — just 2 minutes:\nRate your trip: {survey_link}\n\n"
            "Reviews that make our day:\n  Google: {google_review_link}\n  TripAdvisor: {tripadvisor_link}\n\n"
            "YOUR REWARDS:\n  {loyalty_credit} travel credit earned!\n"
            "  Refer friends and earn {referral_amount} cash each\n"
            "  Your code: *{referral_code}*\n\nWhere shall we take you next?"
        ),
        "sms": (
            "Welcome home {name}! Hope {destination} was amazing. Rate trip: {survey_link} "
            "Earned {loyalty_credit} credit. Refer: code {referral_code} = {referral_amount} cash. "
            "{company_name}"
        ),
        "phone_script": (
            "WELCOME HOME CALL\n\n"
            "\"Hello {name}! It's {agent} from {company_name} — welcome home! How was {destination}?!\"\n\n"
            "GUIDED QUESTIONS:\n  • What was the absolute highlight for you?\n"
            "  • Was there anything that could have been even better?\n"
            "  • How was the hotel / driver / guide?\n\n"
            "REVIEW REQUEST: \"If you get a spare 2 minutes, an honest Google review would help "
            "other travellers. I'll pop the link in a WhatsApp now.\"\n\n"
            "LOYALTY: \"You've earned {loyalty_credit} travel credit. If any friends ask about "
            "{destination}, please mention us — we'll give you {referral_amount} per booking.\""
        ),
        "automation": [
            "Return date + 48 hrs → send email + WhatsApp + SMS",
            "Add loyalty credit → update tier if threshold reached",
            "Survey low score → flag for review → respond within 24 hrs",
            "Google review posted → alert marketing → respond",
            "Return + 30 days → next destination nurture email",
            "Return + 365 days → trigger UC-017",
        ],
    },

    "UC-016": {
        "title":    "Review Chase — No Response Follow-Up (7 Days Post-Return)",
        "category": "posttrip",
        "priority": "P3",
        "sla":      "D+7 post-return — one-time send",
        "channels": ["whatsapp", "email"],
        "trigger":  "No review submitted 7 days after welcome home message",
        "schedule": {"anchor": "return_date", "offset_minutes": 7*24*60},
        "merge_vars": [
            "name","destination","google_review_link","tripadvisor_link","bonus_credit",
            "agent_name","agent_email","company_name",
        ],
        "email_subject": "One small favour, {name}? Your {destination} review would help so many travellers",
        "email_body": (
            "Dear {name},\n\nI hope you have settled back in well after your {destination} trip!\n\n"
            "I'm reaching out one final time with a small request. Your honest review genuinely "
            "helps other travellers make decisions and helps our small team grow.\n\n"
            "It takes about 60 seconds:\n"
            "  • Google Review : {google_review_link}\n"
            "  • TripAdvisor   : {tripadvisor_link}\n\n"
            "As a small token of appreciation, I'll add {bonus_credit} to your travel wallet when "
            "you submit a review. Just forward a screenshot and I'll add it manually.\n\n"
            "If you had any concerns you'd prefer to share privately first, I'm all ears at "
            "{agent_email}.\n\nThank you so much for considering it, {name}.\n\n"
            "{agent_name} | {company_name}"
        ),
        "whatsapp": (
            "Hi {name}!\n\nDid you get a chance to look at our feedback request?\n\n"
            "We're a small, passionate team and your experience genuinely shapes how we serve "
            "future travellers. Takes just 60 seconds:\n\n"
            "Leave a quick review: {google_review_link}\n\n"
            "As a thank you, we'll add *{bonus_credit} extra* to your travel wallet when you post!\n\n"
            "No pressure at all — just know it means a lot to us."
        ),
        "automation": [
            "Post-trip D+7: If review_count = 0 → send ONCE only",
            "Do NOT send if customer gave negative feedback → route to complaints team",
            "Do NOT send more than one follow-up",
            "If review posted after this → cancel further re-engagement",
            "Bonus credit added manually on screenshot proof",
        ],
    },

    "UC-017": {
        "title":    "Anniversary Re-Engagement — Annual Retention Trigger",
        "category": "posttrip",
        "priority": "P3",
        "sla":      "On anniversary at 09:00 IST",
        "channels": ["whatsapp", "email"],
        "trigger":  "Customer travel anniversary (return_date + 365 days)",
        "schedule": {"anchor": "return_date", "offset_minutes": 365*24*60},
        "merge_vars": [
            "name","destination","destination_memory_line","discount","prev_coordinator",
            "next_destination_suggestions","agent_name","company_name",
        ],
        "email_subject": "Happy Travel Anniversary! One year since {destination} — a gift from {company_name}",
        "email_body": (
            "Dear {name},\n\nHappy Travel Anniversary!\n\n"
            "One year ago today, you were {destination_memory_line}. We hope the memories still "
            "make you smile.\n\n"
            "To celebrate your anniversary with us, here is your exclusive returning-traveller offer:\n\n"
            "YOUR ANNIVERSARY GIFT\n"
            "════════════════════════════════\n"
            "  • {discount} discount on your next booking\n"
            "  • Complimentary room upgrade at select hotels\n"
            "  • Free one-way airport transfer\n"
            "  • Priority access to peak-season dates before general release\n"
            "  • Your previous coordinator {prev_coordinator} reserved for you\n"
            "════════════════════════════════\n\n"
            "This offer is valid for 30 days. Simply reply or WhatsApp us to start planning.\n\n"
            "WHERE COULD YEAR TWO TAKE YOU?\n{next_destination_suggestions}\n\n"
            "{agent_name} | {company_name}"
        ),
        "whatsapp": (
            "{name} — one year ago today!\n\n"
            "One year ago you were exploring *{destination}* with us — what a journey that was!\n\n"
            "We hope you're celebrating today. To mark this anniversary, here is something exclusive:\n\n"
            "ANNIVERSARY OFFER — valid 30 days:\n"
            "  • {discount} off your next trip\n"
            "  • Complimentary room upgrade at partner hotels\n"
            "  • Free airport transfer one-way\n"
            "  • Priority access to early-bird dates\n\n"
            "Reply *ANNIVERSARY* to claim, or just tell us where you'd like to go next!\n\n"
            "{company_name} — crafting your memories"
        ),
        "automation": [
            "Return date + 365 days → auto-trigger at 9AM IST",
            "Repeat booking in last 6 months → skip trigger",
            "Unresolved complaint → skip → relationship manager",
            "Offer validity: 30 days → expiry reminder at day 25",
            "Reply → create new enquiry → assign original coordinator",
        ],
    },

    # ════════════════════════════════════════════════════════════
    # SECTION F — Visa & Documents
    # ════════════════════════════════════════════════════════════
    "UC-018": {
        "title":    "Visa Approved — Celebration & Traveller Instructions",
        "category": "visa",
        "priority": "P1",
        "sla":      "< 30 minutes from approval",
        "channels": ["email", "whatsapp", "sms"],
        "trigger":  "Visa approval confirmed and document received",
        "schedule": {"anchor": "visa_approved", "offset_minutes": 0},
        "merge_vars": [
            "name","ref","destination","visa_type","visa_number","lead_name","valid_from",
            "valid_until","entry_type","entry_notes","max_stay","passport_last4",
            "entry_conditions","border_crossing_instructions","days_remaining","email",
            "company_name",
        ],
        "email_subject": "Visa APPROVED — {destination} Visa Confirmed [{ref}] | {company_name}",
        "email_body": (
            "Dear {name},\n\nExcellent news — your {destination} visa has been APPROVED!\n\n"
            "VISA DETAILS\n"
            "════════════════════════════════\n"
            "Visa Type    : {visa_type}\nVisa Number  : {visa_number}\nIssued To    : {lead_name}\n"
            "Valid From   : {valid_from}\nValid Until  : {valid_until}\n"
            "Entry Type   : {entry_type} ({entry_notes})\nMax Stay     : {max_stay}\n"
            "════════════════════════════════\n\n"
            "IMPORTANT — PLEASE READ:\n"
            "  • Print a physical copy and carry with your passport at all times\n"
            "  • This visa is linked to passport number ending {passport_last4}\n"
            "  • Do NOT travel on any other passport\n"
            "  • Check entry conditions carefully: {entry_conditions}\n\n"
            "HOW TO USE YOUR VISA AT THE BORDER:\n{border_crossing_instructions}\n\n"
            "Your approved visa is attached to this email as a PDF.\n\n"
            "{days_remaining} days remaining until your trip!\n\n"
            "{company_name} Visa Team"
        ),
        "whatsapp": (
            "VISA APPROVED, {name}!\n\nYour *{destination}* visa is confirmed!\n\n"
            "Visa No: *{visa_number}*\nValid: {valid_from} to {valid_until}\n"
            "{entry_type} entry | Max stay: {max_stay}\n\n"
            "Visa PDF emailed to {email}. Please print a copy!\n\n"
            "Just *{days_remaining} days* until your trip!"
        ),
        "sms": (
            "GREAT NEWS {name}! {destination} visa APPROVED. No:{visa_number}. "
            "Valid to {valid_until}. Print a copy! Doc emailed. {days_remaining} days to trip!"
        ),
        "automation": [
            "Visa approval → send notifications within 30 min",
            "Update visa_status = APPROVED in CRM",
            "Update booking checklist — visa item ticked",
            "Valid_until < return_date → URGENT agent alert",
            "Single-entry + multi-city → check re-entry requirements",
        ],
    },

    "UC-019": {
        "title":    "Visa Rejected — Emergency Response & Escalation Protocol",
        "category": "visa",
        "priority": "P1 CRITICAL",
        "sla":      "Phone call within 15 minutes — call first before any written communication",
        "channels": ["voice", "email", "whatsapp"],
        "trigger":  "Visa application formally rejected by immigration authority",
        "schedule": {"anchor": "visa_rejected", "offset_minutes": 0},
        "merge_vars": [
            "name","destination","visa_ref","rejection_date","rejection_reason","reapply_details",
            "success_rate","new_timeline","required_docs","appeal_details","appeal_deadline",
            "alternative_route","eligibility_notes","hold_deadline","rebook_deadline",
            "insurance_hotline","next_call_date","agent_name","agent_phone","email","agent",
            "reason","additional_docs","processing_time","alternative","update_frequency",
            "company_name","ref",
        ],
        "email_subject": "URGENT: Your {destination} Visa Application — Update & All Your Options [{ref}]",
        "email_body": (
            "Dear {name},\n\nFollowing our phone call, here is a written summary of your visa "
            "situation and all available options.\n\n"
            "VISA APPLICATION STATUS\n"
            "════════════════════════════════\n"
            "Application Reference : {visa_ref}\nDestination           : {destination}\n"
            "Rejection Date        : {rejection_date}\nReason Given          : {rejection_reason}\n"
            "════════════════════════════════\n\n"
            "YOUR OPTIONS IN DETAIL\n\n"
            "OPTION 1 — REAPPLY WITH ADDITIONAL DOCUMENTS\n{reapply_details}\n"
            "Likelihood of success: {success_rate}\nNew timeline: {new_timeline}\n"
            "Documents needed: {required_docs}\n\n"
            "OPTION 2 — FORMAL APPEAL\n{appeal_details}\nAppeal deadline: {appeal_deadline}\n"
            "We can prepare the appeal letter: YES — at no extra charge\n\n"
            "OPTION 3 — ALTERNATIVE VISA ROUTE\n{alternative_route}\nEligibility: {eligibility_notes}\n\n"
            "OPTION 4 — POSTPONE YOUR TRIP\n"
            "Booking held penalty-free until {hold_deadline}\nRebook by: {rebook_deadline}\n\n"
            "OPTION 5 — CANCEL WITH MAXIMUM REFUND\n"
            "Our admin fees: FULLY WAIVED in these circumstances\n"
            "Insurance coverage: Contact {insurance_hotline}\n\n"
            "YOUR BOOKING STATUS\nAll components held until {hold_deadline}. Nothing cancelled "
            "without your explicit instruction.\n\n"
            "I will call you again on {next_call_date} to discuss your preferred option.\n\n"
            "{agent_name} — Direct Line: {agent_phone}"
        ),
        "whatsapp": (
            "Hi {name},\n\nAs discussed on our call — full details and all your options regarding "
            "your {destination} visa are now in your email at {email}.\n\n"
            "Please do not worry. We are right here with you and we will find a solution together.\n\n"
            "Reply any time or call me directly: {agent_phone}"
        ),
        "phone_script": (
            "VISA REJECTION CALL — MANDATORY: CALL FIRST. NEVER email/WhatsApp first.\n\n"
            "\"{name}, this is {agent} from {company_name}. I am calling you personally because I "
            "have an update about your {destination} visa application and I wanted to speak with "
            "you directly before you see anything in writing.\n\n"
            "I am sorry to share that your visa application has been returned with a rejection.\n\n"
            "The rejection reason: {rejection_reason}\n\n"
            "Now — this is not the end of the road. Here are your options:\n\n"
            "OPTION 1: Reapply — additional docs {additional_docs}, approval rate {success_rate}, "
            "takes {processing_time} days.\nOPTION 2: Formal appeal within {appeal_deadline}.\n"
            "OPTION 3: Alternative route via {alternative}.\nOPTION 4: Postpone — booking held "
            "until {hold_deadline}.\nOPTION 5: Cancel with maximum refund.\n\n"
            "I am personally overseeing this and will update you every {update_frequency} until "
            "resolved. What would you like to do first?\"\n\n"
            "FOLLOW-UP CALL EVERY 48 HRS:\n"
            "\"Hello {name}, {agent} here. Update: {update}. Next steps: {next_steps}.\""
        ),
        "automation": [
            "Visa rejection → P1 → agent assigned → call within 15 min",
            "DO NOT auto-send WhatsApp/SMS before call — human contact first",
            "Log rejection reason → feed visa success rate analytics",
            "Place HOLD flag on booking → no auto-cancellation",
            "Hold booking → update visa_status = REJECTED",
        ],
    },

    # ════════════════════════════════════════════════════════════
    # SECTION G — Upsell & Loyalty
    # ════════════════════════════════════════════════════════════
    "UC-020": {
        "title":    "Honeymoon & Anniversary — Special Arrangements Coordination",
        "category": "upsell",
        "priority": "P2",
        "sla":      "< 24 hours of booking confirmation",
        "channels": ["whatsapp", "email", "voice"],
        "trigger":  "Booking type HONEYMOON or ANNIVERSARY at booking confirmation",
        "schedule": {"anchor": "booking_confirmed", "offset_minutes": 24*60},
        "merge_vars": [
            "name","trip_type","destination","ref","price_decor","price_champagne","price_dinner",
            "price_spa","price_cruise","price_cake","price_photo","price_star","price_music",
            "agent_name","agent","company_name",
        ],
        "email_subject": "Let's make your {trip_type} absolutely magical | Ref: {ref}",
        "email_body": (
            "Dear {name},\n\nCongratulations on your upcoming {trip_type} to {destination}! "
            "We want every single detail to be perfect.\n\n"
            "COMPLIMENTARY ROMANCE TOUCHES — already arranged at no extra cost:\n"
            "  • Early check-in request submitted to hotel\n"
            "  • {trip_type} noted on all hotel and transfer bookings\n"
            "  • Special occasion highlighted to all drivers and guides\n\n"
            "OPTIONAL SPECIAL ARRANGEMENTS — we coordinate everything discreetly\n\n"
            "  • Room Decoration — rose petals, candles, balloons   : {price_decor}\n"
            "  • Welcome Champagne and Strawberries                  : {price_champagne}\n"
            "  • Private Candlelit Dinner                            : {price_dinner}\n"
            "  • Couples Spa or Ayurveda Package                    : {price_spa}\n"
            "  • Private Sunset Cruise                               : {price_cruise}\n"
            "  • Surprise Anniversary or Wedding Cake                : {price_cake}\n"
            "  • Professional Honeymoon Photo Shoot                  : {price_photo}\n"
            "  • Stargazing Private Dinner                           : {price_star}\n"
            "  • Live Musician for Dinner                            : {price_music}\n\n"
            "HOW SURPRISES WORK:\nNote your wish in your reply. We coordinate only with hotel "
            "staff and you. Your partner sees nothing until the moment arrives.\n\n"
            "{agent_name} | Romance Travel Specialist | {company_name}"
        ),
        "whatsapp": (
            "Hi {name}! Congratulations on your upcoming *{trip_type}* to {destination}!\n\n"
            "We want every single moment to be absolutely perfect.\n\n"
            "I'd love to arrange some surprise extras. Which of these appeal to you?\n\n"
            "1. Rose petal and candle turndown on arrival\n"
            "2. Champagne, strawberries and chocolate welcome\n"
            "3. Private candlelit dinner — beach, rooftop or garden\n"
            "4. Couples Ayurvedic or spa treatment\n"
            "5. Sunrise private yoga session\n"
            "6. Romantic sunset boat cruise\n"
            "7. Professional honeymoon photo shoot\n"
            "8. Surprise anniversary cake\n"
            "9. Private stargazing dinner\n\n"
            "Reply with numbers and I'll coordinate everything discreetly with the hotel!\n\n"
            "Your partner will not see any of this — all surprises are completely safe with us."
        ),
        "phone_script": (
            "HONEYMOON AND ANNIVERSARY COORDINATION CALL\n\n"
            "\"Hello {name}! This is {agent} from {company_name}. Huge congratulations on your "
            "upcoming {trip_type}!\n\nI am your dedicated romance travel coordinator for this trip. "
            "I've already flagged your booking as a special occasion with all our suppliers.\n\n"
            "Is there anything specific you have always dreamed of? Anything your partner has "
            "mentioned wanting?\n\nLeave it all with me. I'll coordinate everything discreetly "
            "with the hotel and send you a private confirmation that only you can see.\""
        ),
        "automation": [
            "Booking type HONEYMOON/ANNIVERSARY → auto-tag → assign romance coordinator",
            "Within 24 hrs → WhatsApp options + coordination email",
            "Arrangements confirmed → email hotel special requests letter → cc agent",
            "3 days before departure → reconfirm with hotel directly",
            "Post-trip: anniversary date stored → UC-017 annual re-engagement",
        ],
    },

    "UC-021": {
        "title":    "Travel Insurance — Trigger-Based Upsell",
        "category": "upsell",
        "priority": "P2",
        "sla":      "Within 2 hours of booking confirmation",
        "channels": ["whatsapp", "email", "voice"],
        "trigger":  "Booking confirmed with NO insurance AND trip value > threshold OR high-risk destination",
        "schedule": {"anchor": "booking_confirmed", "offset_minutes": 2*60},
        "merge_vars": [
            "name","ref","destination","destination_upper","trip_value","destination_risk_factors",
            "evacuation_cost","cancellation_loss","bag_cost","basic_price","std_price","prem_price",
            "insurer_name","insurance_link","premium","agent_name","agent","company_name",
        ],
        "email_subject": "Important: Travel Insurance Recommended for Your {destination} Trip [{ref}]",
        "email_body": (
            "Dear {name},\n\n"
            "I noticed your {destination} booking (Ref: {ref}) does not yet include travel "
            "insurance. Given the trip value of {trip_value}, I would be doing you a disservice if "
            "I did not highlight this.\n\n"
            "WHY INSURANCE IS ESSENTIAL FOR {destination_upper}\n{destination_risk_factors}\n\n"
            "THE FINANCIAL RISK WITHOUT INSURANCE\n"
            "Medical evacuation alone can cost        : {evacuation_cost}\n"
            "Trip cancellation loss if uninsured      : {cancellation_loss}\n"
            "Single lost bag replacement average      : {bag_cost}\n\n"
            "OUR RECOMMENDED PLANS\n"
            "═══════════════════════════════════\n"
            "Plan      Medical    Cancellation  Luggage   Per Person\n"
            "Basic     10 Lakhs   50,000        25,000    {basic_price}\n"
            "Standard  25 Lakhs   1 Lakh        50,000    {std_price}\n"
            "Premium   50 Lakhs   2 Lakhs       1 Lakh    {prem_price}\n"
            "═══════════════════════════════════\n\n"
            "INSURER: {insurer_name} (IRDA-certified)\nAdd to booking: {insurance_link}\n\n"
            "This is entirely your choice — but I would genuinely not feel comfortable letting you "
            "travel without mentioning it.\n\n{agent_name} | {company_name}"
        ),
        "whatsapp": (
            "Hi {name}! Regarding your *{destination}* trip (Ref: {ref}).\n\n"
            "We noticed travel insurance has not yet been added to your booking. For a trip of "
            "this value ({trip_value}), comprehensive cover is strongly recommended.\n\n"
            "WHAT IT COVERS FOR {destination_upper}:\n"
            "  • Medical emergencies up to 50 Lakhs\n"
            "  • Trip cancellation and curtailment\n"
            "  • Flight delays and missed connections\n"
            "  • Lost and stolen luggage and documents\n"
            "  • Emergency evacuation and repatriation\n\n"
            "Starting from just {premium} per person.\n\n"
            "Reply *INSURE ME* for an instant quote, or I'll call you within 30 minutes!"
        ),
        "phone_script": (
            "INSURANCE UPSELL CALL — GENUINE, NOT SALESY\n\n"
            "\"Hello {name}, this is {agent} from {company_name}. Calling about your {destination} "
            "booking — nothing to worry about, just something I wanted to flag personally.\n\n"
            "I noticed your booking does not include travel insurance. For a trip of this value "
            "and this destination, I'd feel remiss not to mention it. May I take 2 minutes?\n\n"
            "We work with {insurer_name} and our most popular plan for a trip like yours is "
            "{std_price} per person. Shall I add it to your booking? I can do that in 60 seconds.\""
        ),
        "automation": [
            "Booking + no insurance + trip_value > threshold → trigger within 2 hrs",
            "Destination in HIGH_RISK_LIST → trigger regardless",
            "Jun–Sep bookings → add monsoon disruption cover note",
            "Adventure activity → flag adventure cover add-on",
            "Customer declines → note in CRM → do not resend",
            "Insurance added → cancel upsell sequence",
        ],
    },

    "UC-022": {
        "title":    "Wellness Upsell — Ayurveda, Yoga & Spa Add-On",
        "category": "upsell",
        "priority": "P3",
        "sla":      "Within 24 hours of booking confirmation",
        "channels": ["whatsapp", "email"],
        "trigger":  "Destination includes Kerala, Rishikesh, Mysore, or Goa OR interests = wellness",
        "schedule": {"anchor": "booking_confirmed", "offset_minutes": 24*60},
        "merge_vars": [
            "name","destination","destination_upper","destination_wellness_history",
            "authenticity_notes","wellness_highlight_1","wellness_highlight_2",
            "wellness_highlight_3","price_1","price_2","price_3","price_4","price_5","price_6",
            "agent_name","ref",
        ],
        "email_subject": "Don't miss {destination}'s legendary wellness experiences — curated for you [{ref}]",
        "email_body": (
            "Dear {name},\n\n{destination} is one of the world's premier wellness destinations and "
            "we'd love to help you experience it at its most authentic.\n\n"
            "THE WELLNESS STORY OF {destination_upper}\n{destination_wellness_history}\n\n"
            "WHY THIS IS DIFFERENT FROM A HOTEL SPA\n{authenticity_notes}\n\n"
            "OUR VETTED WELLNESS EXPERIENCES\n"
            "════════════════════════════════\n"
            "Experience                       Duration     Per Person\n"
            "Authentic Ayurvedic Consultation 90 minutes   {price_1}\n"
            "Full-Body Abhyanga Massage       60 minutes   {price_2}\n"
            "Panchakarma Introduction Day     Full day     {price_3}\n"
            "Sunrise Yoga with Teacher        90 minutes   {price_4}\n"
            "Couples Spa and Wellness Journey Half day     {price_5}\n"
            "3-Day Wellness Immersion         3 days       {price_6}\n"
            "════════════════════════════════\n\n"
            "ALL PARTNERS ARE:\n"
            "  • Certified by Government of Kerala or Yoga Alliance\n"
            "  • Personally vetted by our team\n"
            "  • Able to accommodate dietary requirements\n\n"
            "Simply reply with your preferences to add to your itinerary.\n\n"
            "{agent_name} | Wellness Travel Specialist"
        ),
        "whatsapp": (
            "Hi {name}! You're visiting *{destination}* — one of the world's greatest wellness "
            "destinations!\n\n"
            "{destination} is internationally renowned for:\n"
            "  • {wellness_highlight_1}\n  • {wellness_highlight_2}\n  • {wellness_highlight_3}\n\n"
            "Would you like to add an authentic wellness experience to your itinerary?\n\n"
            "CURATED OPTIONS from {price_1}:\n"
            "  • Authentic Ayurvedic consultation and treatment\n"
            "  • Full-day Panchakarma introduction\n"
            "  • Sunrise yoga with certified teacher\n"
            "  • Couples holistic spa day\n"
            "  • 3-day wellness mini-retreat\n\n"
            "Reply *WELLNESS* and I'll send our full vetted options with photos!"
        ),
        "automation": [
            "Destination in WELLNESS_DESTINATIONS → trigger within 24 hrs of booking",
            "Interest tag includes 'wellness' → trigger on any booking",
            "Customer age 45+ → add Panchakarma longevity programme note",
            "Added to booking → brief wellness partner",
            "Customer notes stress/burnout → highlight Rishikesh retreat",
        ],
    },

    "UC-023": {
        "title":    "MICE & Corporate — Group Event Booking Workflow",
        "category": "upsell",
        "priority": "P1",
        "sla":      "< 2 hours — account manager personal contact",
        "channels": ["email", "voice", "whatsapp"],
        "trigger":  "Group size 10+ OR keywords: conference, incentive, corporate, MICE, offsite, event",
        "schedule": {"anchor": "mice_enquiry", "offset_minutes": 0},
        "merge_vars": [
            "name","event_type","company_client","delegates","budget_range","dates","destination",
            "account_manager","account_manager_phone","account_manager_email","ref","gst_number",
            "email","proposal_deadline","venue_concept","activity_concept","company_name",
        ],
        "email_subject": "Your Corporate / MICE Travel Proposal — {event_type} for {company_client} [{ref}]",
        "email_body": (
            "Dear {name},\n\nThank you for reaching out about your corporate travel and event "
            "requirements. We specialise in large-group and MICE travel.\n\n"
            "WHAT WE UNDERSTAND FROM YOUR ENQUIRY\n"
            "════════════════════════════════\n"
            "Event Type     : {event_type}\nDelegate Count : {delegates}\n"
            "Budget Range   : {budget_range} per delegate\nPreferred Dates: {dates}\n"
            "Destination    : {destination}\nCompany Name   : {company_client}\n"
            "GST Number     : {gst_number}\n"
            "════════════════════════════════\n\n"
            "YOUR DEDICATED CORPORATE ACCOUNT TEAM\n"
            "Account Manager : {account_manager}\nDirect Line     : {account_manager_phone}\n"
            "Email           : {account_manager_email}\n\n"
            "WHAT WE DELIVER WITHIN 24 HOURS\n"
            "  • Tailored venue shortlist — 3 options with capacity, AV specs, pricing\n"
            "  • Group accommodation comparison with block rate options\n"
            "  • Ground logistics proposal — fleet, transfers, coordination\n"
            "  • Team-building experience options\n"
            "  • Formal RFP response document\n\n"
            "OUR CORPORATE SERVICE INCLUDES\n"
            "  • Dedicated account manager throughout\n"
            "  • GST-compliant invoicing with your GSTIN\n"
            "  • Credit terms — Net-30 or Net-45 for approved accounts\n"
            "  • 24/7 on-site event coordinator option\n"
            "  • Post-event reconciliation report\n\n"
            "{account_manager} | Corporate Travel and MICE Division | {company_name}"
        ),
        "whatsapp": (
            "Hello {name}! Thank you for your corporate and MICE enquiry!\n\n"
            "Your dedicated account manager *{account_manager}* will call you within *2 hours*.\n\n"
            "Meanwhile, could you confirm:\n"
            "  • How many delegates?\n"
            "  • Preferred dates?\n"
            "  • Destination?\n"
            "  • Type of event — conference, incentive, team offsite, other?\n"
            "  • Budget per delegate?\n\n"
            "This helps us prepare your tailored proposal faster!\n\nRef: *{ref}*"
        ),
        "phone_script": (
            "MICE ENQUIRY — CORPORATE DISCOVERY CALL\n\n"
            "\"Hello {name}, this is {account_manager} from {company_name}'s corporate travel "
            "division. I received your enquiry about organising {event_type} — sounds like a "
            "fantastic event.\n\nDISCOVERY QUESTIONS:\n"
            "  1. How many delegates?\n  2. Fixed dates or flexibility by a few weeks?\n"
            "  3. Is {destination} definite or open to alternatives?\n"
            "  4. Self-funded by company or delegates contributing?\n"
            "  5. Key objective — team bonding, reward, client entertainment, training?\n"
            "  6. Approximate budget per person all-in?\n"
            "  7. Need everything (flights/hotels/transfers/activities) or just land arrangements?\n"
            "  8. Who else is involved in the decision and what's your timeline?\n\n"
            "'I'm thinking {venue_concept} for the accommodation, with {activity_concept} for the "
            "team-building element.'\n\n"
            "Comprehensive proposal on your desk by {proposal_deadline}. Email {email}?\""
        ),
        "automation": [
            "Group 10+ OR MICE keywords → auto-assign corporate account manager",
            "Account manager call within 2 hrs (business hours) — P1",
            "After discovery → generate RFP → send to top 3 matched venues within 4 hrs",
            "Venue quotes received → comparison table → sent to client within 24 hrs",
            "MICE booking confirmed → create event file → assign on-site coordinator",
        ],
    },

    "UC-024": {
        "title":    "Loyalty & Referral — Reward Issuance & Redemption",
        "category": "upsell",
        "priority": "P3",
        "sla":      "< 24 hours of triggering event",
        "channels": ["email", "whatsapp", "sms"],
        "trigger":  "Booking completed (loyalty credit) OR referred customer books (referral bonus)",
        "schedule": {"anchor": "reward_event", "offset_minutes": 0},
        "merge_vars": [
            "name","reward_type","reward_amount","new_balance","tier","total_trips","total_earned",
            "referral_amount","referral_code","referral_link","applied_to","expiry_note",
            "referral_line","referral_whatsapp_note","next_tier_threshold","phone","company_name",
        ],
        "email_subject": "Your reward of {reward_amount} has been added — {reward_type} | {company_name}",
        "email_body": (
            "Dear {name},\n\nGreat news — a reward has been added to your {company_name} travel "
            "wallet!\n\nREWARD DETAILS\n"
            "════════════════════════════════\n"
            "Reward Type        : {reward_type}\nAmount Awarded     : {reward_amount}\n"
            "{referral_line}\nApplied To         : {applied_to}\nNew Wallet Balance : {new_balance}\n"
            "Expiry             : {expiry_note}\n"
            "════════════════════════════════\n\n"
            "YOUR LOYALTY SUMMARY\n"
            "════════════════════════════════\n"
            "Total Trips Booked   : {total_trips}\nTotal Rewards Earned : {total_earned}\n"
            "Current Balance      : {new_balance}\nLoyalty Tier         : {tier}\n"
            "Next Tier Threshold  : {next_tier_threshold} more in bookings\n"
            "════════════════════════════════\n\n"
            "HOW TO USE YOUR REWARDS\n"
            "  • Reply to any quote email: 'Please apply my wallet credit'\n"
            "  • Mention to your coordinator at time of booking\n"
            "  • Minimum redemption: 1,000\n\n"
            "REFER MORE FRIENDS — EARN MORE\n"
            "Your unique referral link: {referral_link}\nYour referral code:        {referral_code}\n\n"
            "Every friend who books earns you {referral_amount} cash to your wallet.\n\n"
            "Keep exploring — every trip earns you more!\n{company_name} Loyalty Team"
        ),
        "whatsapp": (
            "Reward Added — {company_name}\n\nHi {name}! Congratulations!\n\n"
            "{reward_type}: *{reward_amount}*\n{referral_whatsapp_note}\n"
            "New wallet balance: *{new_balance}*\n\n"
            "YOUR LOYALTY STATUS:\n  Tier: *{tier}*\n  Total trips: {total_trips}\n"
            "  Total earned: {total_earned}\n\n"
            "Use your credit on your next booking — just mention it to your coordinator!\n\n"
            "Refer friends with code *{referral_code}* and earn {referral_amount} per booking."
        ),
        "sms": (
            "{company_name}: {reward_amount} {reward_type} added! Balance: {new_balance}. "
            "Refer friends code {referral_code} = {referral_amount} each. Queries: {phone}"
        ),
        "automation": [
            "Booking COMPLETED → calculate 1% loyalty credit → add to wallet",
            "Referred booking confirmed → credit referrer wallet → notify both",
            "Wallet milestones 10k/25k/50k → tier upgrade → congrats message",
            "Reward expiry –30 days → reminder WhatsApp",
            "Annual wallet statement emailed every January",
            "Referral code used → track attribution in CRM",
        ],
    },
}


def use_case_summary() -> list[dict[str, Any]]:
    """Compact list for /playbooks listing endpoint."""
    return [
        {
            "id":       uc_id,
            "title":    spec["title"],
            "category": CATEGORY[spec["category"]],
            "priority": spec["priority"],
            "sla":      spec["sla"],
            "channels": spec["channels"],
            "trigger":  spec["trigger"],
        }
        for uc_id, spec in PLAYBOOKS.items()
    ]


def get_playbook(uc_id: str) -> dict[str, Any] | None:
    return PLAYBOOKS.get(uc_id.upper())


def render(uc_id: str, channel: str, context: dict[str, Any]) -> dict[str, str] | None:
    """Render a single channel's template(s) for a UC with the given context."""
    pb = get_playbook(uc_id)
    if not pb:
        return None
    safe = SafeDict({k: ("" if v is None else str(v)) for k, v in (context or {}).items()})
    out: dict[str, str] = {}
    if channel == "email":
        if "email_subject" in pb:
            out["subject"] = pb["email_subject"].format_map(safe)
        if "email_body" in pb:
            out["body"] = pb["email_body"].format_map(safe)
    elif channel == "whatsapp" and "whatsapp" in pb:
        out["content"] = pb["whatsapp"].format_map(safe)
    elif channel == "sms" and "sms" in pb:
        out["content"] = pb["sms"].format_map(safe)
    elif channel == "voice" and "phone_script" in pb:
        out["script"] = pb["phone_script"].format_map(safe)
    return out or None
