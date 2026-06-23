"""
Billing rollup service — generates `ts_billing_records` rows per period.

Per spec section 1: usage-based pricing per channel + subscription cost per tier.
"""
from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from app.database import get_supabase_admin


# Subscription monthly fees (USD)
TIER_SUBSCRIPTION = {
    "starter":      0.00,
    "professional": 99.00,
    "enterprise":   499.00,
}


class BillingService:
    def __init__(self) -> None:
        self.db = get_supabase_admin()

    def generate_period(
        self,
        *,
        business_id: UUID,
        start: date,
        end:   date,
    ) -> dict:
        """Aggregate communications between [start, end] and upsert a billing record."""
        start_ts = datetime.combine(start, datetime.min.time()).replace(tzinfo=timezone.utc)
        end_ts   = datetime.combine(end,   datetime.min.time()).replace(tzinfo=timezone.utc) + timedelta(days=1)

        biz = (
            self.db.table("ts_businesses").select("subscription_tier")
            .eq("id", str(business_id)).limit(1).execute().data
        )
        tier = (biz[0]["subscription_tier"] if biz else "starter") or "starter"

        logs = (
            self.db.table("ts_communication_logs")
            .select("channel,cost,delivery_status")
            .eq("business_id", str(business_id))
            .gte("sent_at", start_ts.isoformat())
            .lt("sent_at",  end_ts.isoformat())
            .execute().data or []
        )

        cost_per_channel: dict[str, float] = {"email": 0, "sms": 0, "whatsapp": 0,
                                              "voice": 0, "voicemail": 0}
        total_messages = 0
        total_cost     = 0.0
        for r in logs:
            ch = r.get("channel") or "internal"
            c  = float(r.get("cost") or 0)
            cost_per_channel[ch] = cost_per_channel.get(ch, 0) + c
            total_messages += 1
            total_cost     += c

        subscription_cost = TIER_SUBSCRIPTION.get(tier, 0.0)
        billed_total      = round(total_cost + subscription_cost, 4)

        # delete existing record for the same period (idempotent)
        self.db.table("ts_billing_records").delete().eq("business_id", str(business_id)).eq(
            "billing_period_start", start.isoformat(),
        ).eq("billing_period_end", end.isoformat()).execute()

        row = self.db.table("ts_billing_records").insert({
            "business_id":          str(business_id),
            "billing_period_start": start.isoformat(),
            "billing_period_end":   end.isoformat(),
            "total_messages":       total_messages,
            "total_cost":           billed_total,
            "email_cost":           round(cost_per_channel["email"], 4),
            "sms_cost":             round(cost_per_channel["sms"], 4),
            "whatsapp_cost":        round(cost_per_channel["whatsapp"], 4),
            "voice_cost":           round(cost_per_channel["voice"] + cost_per_channel.get("voicemail", 0), 4),
            "subscription_cost":    subscription_cost,
            "payment_status":       "pending",
        }).execute().data[0]
        return row

    def list_records(self, business_id: UUID, *, limit: int = 12) -> list[dict]:
        return (
            self.db.table("ts_billing_records").select("*")
            .eq("business_id", str(business_id))
            .order("billing_period_start", desc=True).limit(limit)
            .execute().data or []
        )

    def current_period(self, business_id: UUID) -> dict:
        """Synthesise a not-yet-finalised record for the running calendar month."""
        today = datetime.now(tz=timezone.utc).date()
        start = today.replace(day=1)
        return self.generate_period(business_id=business_id, start=start, end=today)
