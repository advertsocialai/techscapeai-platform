"""
Travel-agency demo seeder.

Creates the four spec workflows from section 5 of the platform spec:
  1. Booking Confirmation Flow (event-triggered, multi-channel)
  2. Lead Inquiry Follow-Up Flow
  3. Payment Collection Flow
  4. Appointment Reminder Flow (generic, reusable)

Plus a couple of templates and a sample contact, all tied to the calling
business. Idempotent: re-running deletes any prior workflow with the same
name and recreates it fresh.
"""
from __future__ import annotations
from typing import Any
from uuid import UUID

from app.database import get_supabase_admin
from .workflow_service import WorkflowService


# ── Templates ───────────────────────────────────────────────────
TEMPLATES = [
    {
        "name":         "booking_confirmation_email",
        "channel":      "email",
        "subject_line": "Booking Confirmed — {{destination}} ({{booking_ref}})",
        "content":      (
            "Hi {{client.name}},\n\n"
            "Your booking to {{destination}} is confirmed for {{dates}}.\n"
            "Reference: {{booking_ref}}\n"
            "Total: {{amount}}\n\n"
            "Itinerary is attached. We'll be in touch closer to your trip.\n\n"
            "Safe travels,\nTech Scape Travel"
        ),
        "approval_status": "approved",
    },
    {
        "name":    "booking_confirmation_whatsapp",
        "channel": "whatsapp",
        "content": "✈️ Hi {{client.name}}! {{destination}} confirmed for {{dates}}. Ref {{booking_ref}}. Full details emailed.",
        "approval_status": "approved",
    },
    {
        "name":    "payment_reminder_sms",
        "channel": "sms",
        "content": "Tech Scape Travel: {{amount}} due on {{booking_ref}}. Pay: ts.travel/p/{{booking_ref}}",
        "approval_status": "approved",
    },
    {
        "name":    "pre_trip_email",
        "channel": "email",
        "subject_line": "Your trip to {{destination}} starts soon!",
        "content": (
            "Hi {{client.name}},\n\n"
            "Your adventure to {{destination}} begins in two days. "
            "Quick checklist: passport, insurance, SIM, local cash.\n"
            "We've attached a packing tip sheet and a fresh weather forecast.\n\n"
            "Tech Scape Travel"
        ),
        "approval_status": "approved",
    },
    {
        "name":    "post_trip_followup_whatsapp",
        "channel": "whatsapp",
        "content": "Hi {{client.name}} 🌟 We hope {{destination}} treated you well. 30-sec review? ts.travel/r",
        "approval_status": "approved",
    },
    {
        "name":    "appt_reminder_sms",
        "channel": "sms",
        "content": "Reminder: {{appointment_label}} at {{appointment_time}}. Reply Y to confirm.",
        "approval_status": "approved",
    },
]


# ── Workflows ───────────────────────────────────────────────────
def _booking_confirmation_workflow(template_ids: dict[str, str]) -> dict:
    return {
        "name":               "Booking Confirmation Flow",
        "description":        "Multi-channel confirmation: email + WhatsApp + payment reminder + pre-trip + follow-up.",
        "trigger_type":       "event_based",
        "trigger_event_type": "booking.created",
        "trigger_config":     {},
        "is_active":          True,
        "steps": [
            {
                "step_number": 1, "action_type": "send_email",
                "action_config": {"template_id": template_ids["booking_confirmation_email"]},
            },
            {
                "step_number": 2, "action_type": "send_whatsapp",
                "delay_seconds": 0,
                "action_config": {"template_id": template_ids["booking_confirmation_whatsapp"]},
            },
            {
                "step_number": 3, "action_type": "conditional_branch",
                "condition_type": "if_then_else",
                "condition_logic": {
                    "op":    "==",
                    "left":  "trigger_data.payment_status",
                    "right": "pending",
                    "then":  "step_4",   # send payment reminder
                    "else":  "step_5",   # skip reminder, jump to pre-trip voicemail
                },
                "action_config":   {},
            },
            {
                "step_number": 4, "action_type": "send_sms",
                "action_config": {"template_id": template_ids["payment_reminder_sms"]},
                "max_retries": 3,
            },
            {
                "step_number": 5, "action_type": "send_voicemail",
                "action_config": {"ai_context": "pre_trip_voicemail", "tone": "friendly_professional"},
            },
            {
                "step_number": 6, "action_type": "send_email",
                "action_config": {"template_id": template_ids["pre_trip_email"]},
            },
            {
                "step_number": 7, "action_type": "send_whatsapp",
                "action_config": {"template_id": template_ids["post_trip_followup_whatsapp"]},
            },
        ],
    }


def _lead_followup_workflow(template_ids: dict[str, str]) -> dict:
    return {
        "name":               "Lead Inquiry Follow-Up Flow",
        "description":        "Acknowledge → WhatsApp welcome → wait → SMS → AI voice call → final email.",
        "trigger_type":       "event_based",
        "trigger_event_type": "lead.created",
        "is_active":          True,
        "steps": [
            {"step_number": 1, "action_type": "send_email",
             "action_config": {"subject": "We received your inquiry — Tech Scape Travel",
                               "ai_context": "lead_acknowledgment"}},
            {"step_number": 2, "action_type": "send_whatsapp",
             "action_config": {"ai_context": "lead_welcome"}},
            {"step_number": 3, "action_type": "wait",
             "action_config": {}, "delay_seconds": 0},
            {"step_number": 4, "action_type": "send_sms",
             "action_config": {"ai_context": "lead_followup"}},
            {"step_number": 5, "action_type": "make_voice_call",
             "action_config": {"ai_context": "lead_voice_call"}},
            {"step_number": 6, "action_type": "send_email",
             "action_config": {"ai_context": "lead_final_offer"}},
        ],
    }


def _payment_collection_workflow(template_ids: dict[str, str]) -> dict:
    return {
        "name":               "Payment Collection Flow",
        "description":        "Email → WhatsApp → SMS → AI voice call → escalation.",
        "trigger_type":       "scheduled",
        "trigger_event_type": "payment.due_in_7_days",
        "is_active":          True,
        "steps": [
            {"step_number": 1, "action_type": "send_email",
             "action_config": {"ai_context": "payment_reminder_email"}},
            {"step_number": 2, "action_type": "send_whatsapp",
             "action_config": {"ai_context": "payment_reminder"}},
            {"step_number": 3, "action_type": "send_sms",
             "action_config": {"template_id": template_ids["payment_reminder_sms"]}},
            {"step_number": 4, "action_type": "make_voice_call",
             "action_config": {"ai_context": "payment_voicemail"}},
            {"step_number": 5, "action_type": "send_email",
             "action_config": {"ai_context": "payment_overdue_escalation"}},
        ],
    }


def _appointment_reminder_workflow(template_ids: dict[str, str]) -> dict:
    return {
        "name":               "Appointment Reminder Flow",
        "description":        "Generic reusable reminder: email 48h → WhatsApp 24h → SMS 2h.",
        "trigger_type":       "scheduled",
        "trigger_event_type": "appointment.upcoming",
        "is_active":          True,
        "steps": [
            {"step_number": 1, "action_type": "send_email",
             "action_config": {"ai_context": "appointment_reminder_email"}},
            {"step_number": 2, "action_type": "send_whatsapp",
             "action_config": {"ai_context": "appointment_reminder"}},
            {"step_number": 3, "action_type": "send_sms",
             "action_config": {"template_id": template_ids["appt_reminder_sms"]}},
        ],
    }


# ── Sample contact ──────────────────────────────────────────────
SAMPLE_CONTACT = {
    "name":              "Jane Demo",
    "email":             "jane.demo@example.com",
    "phone":             "+15555550199",
    "preferred_channel": "whatsapp",
    "tags":              ["demo", "vip"],
    "metadata":          {"loyalty_tier": "gold", "last_destination": "Paris"},
}


def seed_travel_demo(business_id: UUID) -> dict[str, Any]:
    """Wipe and recreate the four spec workflows + templates + sample contact."""
    db = get_supabase_admin()
    biz_id = str(business_id)

    # 1. Templates — upsert by (business_id, name); we just delete prior demo ones first
    template_names = [t["name"] for t in TEMPLATES]
    db.table("ts_communication_templates").delete().eq("business_id", biz_id).in_("name", template_names).execute()

    template_rows = [{**t, "business_id": biz_id, "is_ai_generated": False, "variables": []} for t in TEMPLATES]
    inserted = db.table("ts_communication_templates").insert(template_rows).execute().data or []
    template_ids = {row["name"]: row["id"] for row in inserted}

    # 2. Workflows — delete by name and recreate
    workflow_factories = [
        _booking_confirmation_workflow,
        _lead_followup_workflow,
        _payment_collection_workflow,
        _appointment_reminder_workflow,
    ]
    workflow_names = [f(template_ids)["name"] for f in workflow_factories]
    db.table("ts_workflows").delete().eq("business_id", biz_id).in_("name", workflow_names).execute()

    # Route through WorkflowService.create_workflow so the rows pick up the
    # same explicit defaults (is_archived=False, version=1, …) as user-created
    # workflows and are visible in /workflows immediately.
    wf_svc = WorkflowService()
    created_workflows = []
    for factory in workflow_factories:
        spec_wf = factory(template_ids)
        wf = wf_svc.create_workflow(business_id, spec_wf)
        created_workflows.append({"id": wf["id"], "name": wf["name"],
                                   "steps": len(wf.get("steps") or [])})

    # 3. Sample contact (upsert on email)
    db.table("ts_business_contacts").upsert(
        {**SAMPLE_CONTACT, "business_id": biz_id},
        on_conflict="business_id,email",
    ).execute()

    return {
        "business_id":     biz_id,
        "templates":       len(template_ids),
        "workflows":       created_workflows,
        "sample_contact":  SAMPLE_CONTACT["email"],
    }
