"""
Analytics + daily aggregation.

`overview()` returns a 30-day rollup live from logs (cheap, used by the dashboard).
`aggregate_day()` builds rows in `ts_workflow_analytics` for a given date.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from app.database import get_supabase_admin


_DELIVERED_STATES = {"sent", "delivered", "opened", "clicked", "replied"}


class AnalyticsService:
    def __init__(self) -> None:
        self.db = get_supabase_admin()

    # ── Live 30-day overview ─────────────────────────────────
    def overview(self, business_id: UUID) -> dict:
        thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

        wf_total  = self._count("ts_workflows", business_id)
        wf_active = self._count("ts_workflows", business_id, extra={"is_active": True})

        execs = (
            self.db.table("ts_workflow_executions").select("id", count="exact")
            .eq("business_id", str(business_id))
            .gte("started_at", thirty_days_ago).execute()
        ).count or 0

        logs = (
            self.db.table("ts_communication_logs")
            .select("channel,delivery_status,cost")
            .eq("business_id", str(business_id))
            .gte("sent_at", thirty_days_ago).execute()
            .data or []
        )

        by_channel: dict[str, int] = {}
        delivered = 0
        cost_sum  = 0.0
        for r in logs:
            by_channel[r["channel"]] = by_channel.get(r["channel"], 0) + 1
            if r["delivery_status"] in _DELIVERED_STATES:
                delivered += 1
            cost_sum += float(r.get("cost") or 0)

        delivery_rate = round((delivered / len(logs)) * 100, 2) if logs else 0.0

        return {
            "business_id":          str(business_id),
            "total_workflows":      wf_total,
            "active_workflows":     wf_active,
            "total_executions_30d": execs,
            "total_messages_30d":   len(logs),
            "total_cost_30d":       round(cost_sum, 4),
            "delivery_rate":        delivery_rate,
            "by_channel":           by_channel,
        }

    # ── Daily aggregation → ts_workflow_analytics ────────────
    def aggregate_day(self, *, business_id: UUID, target_date: date) -> int:
        """Builds / replaces analytics rows for `target_date`. Returns rows written."""
        start = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        end   = start + timedelta(days=1)

        execs = (
            self.db.table("ts_workflow_executions")
            .select("id,workflow_id,execution_status,total_cost,execution_time_ms")
            .eq("business_id", str(business_id))
            .gte("started_at", start.isoformat())
            .lt("started_at",  end.isoformat())
            .execute().data or []
        )
        logs = (
            self.db.table("ts_communication_logs")
            .select("workflow_id,channel,delivery_status,cost,opened_at,replied_at")
            .eq("business_id", str(business_id))
            .gte("sent_at", start.isoformat())
            .lt("sent_at",  end.isoformat())
            .execute().data or []
        )

        per_wf: dict[str, dict] = defaultdict(lambda: {
            "total_executions": 0, "successful_executions": 0, "failed_executions": 0,
            "total_messages_sent": 0, "total_cost": 0.0, "exec_time_ms_sum": 0,
            "email_sent": 0, "sms_sent": 0, "whatsapp_sent": 0, "voice_calls_made": 0,
            "delivered": 0, "opened": 0, "replied": 0,
        })

        for e in execs:
            row = per_wf[e["workflow_id"]]
            row["total_executions"] += 1
            row["total_cost"]       += float(e.get("total_cost") or 0)
            row["exec_time_ms_sum"] += int(e.get("execution_time_ms") or 0)
            if e["execution_status"] == "completed":
                row["successful_executions"] += 1
            elif e["execution_status"] == "failed":
                row["failed_executions"] += 1

        for l in logs:
            row = per_wf[l.get("workflow_id") or "_orphan"]
            row["total_messages_sent"] += 1
            row["total_cost"]          += float(l.get("cost") or 0)
            ch = l.get("channel")
            if   ch == "email":    row["email_sent"]      += 1
            elif ch == "sms":      row["sms_sent"]        += 1
            elif ch == "whatsapp": row["whatsapp_sent"]   += 1
            elif ch in ("voice", "voicemail"): row["voice_calls_made"] += 1
            if l.get("delivery_status") in _DELIVERED_STATES:
                row["delivered"] += 1
            if l.get("opened_at"):
                row["opened"] += 1
            if l.get("replied_at"):
                row["replied"] += 1

        rows_written = 0
        for wf_id, row in per_wf.items():
            if wf_id == "_orphan":
                continue
            execs_n = row["total_executions"] or 1
            msgs_n  = row["total_messages_sent"] or 1
            payload = {
                "business_id":         str(business_id),
                "workflow_id":         wf_id,
                "date":                target_date.isoformat(),
                "total_executions":    row["total_executions"],
                "successful_executions": row["successful_executions"],
                "failed_executions":   row["failed_executions"],
                "total_messages_sent": row["total_messages_sent"],
                "total_cost":          round(row["total_cost"], 4),
                "avg_execution_time_ms": int(row["exec_time_ms_sum"] / execs_n),
                "email_sent":          row["email_sent"],
                "sms_sent":            row["sms_sent"],
                "whatsapp_sent":       row["whatsapp_sent"],
                "voice_calls_made":    row["voice_calls_made"],
                "delivery_rate":       round(row["delivered"] * 100 / msgs_n, 2),
                "open_rate":           round(row["opened"]    * 100 / msgs_n, 2),
                "reply_rate":          round(row["replied"]   * 100 / msgs_n, 2),
            }
            try:
                self.db.table("ts_workflow_analytics").upsert(
                    payload, on_conflict="workflow_id,date",
                ).execute()
                rows_written += 1
            except Exception:
                pass
        return rows_written

    # ── Per-workflow stats (used by /workflows/:id/analytics) ─
    def workflow_stats(self, *, business_id: UUID, workflow_id: UUID,
                        days: int = 30) -> dict:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        execs = (
            self.db.table("ts_workflow_executions")
            .select("id,execution_status,total_cost,started_at,completed_at,execution_time_ms")
            .eq("business_id", str(business_id))
            .eq("workflow_id", str(workflow_id))
            .gte("started_at", since).execute().data or []
        )
        logs = (
            self.db.table("ts_communication_logs")
            .select("channel,delivery_status,cost,opened_at,replied_at")
            .eq("business_id", str(business_id))
            .eq("workflow_id", str(workflow_id))
            .gte("sent_at", since).execute().data or []
        )

        total       = len(execs)
        successes   = sum(1 for e in execs if e["execution_status"] == "completed")
        failures    = sum(1 for e in execs if e["execution_status"] == "failed")
        last_run    = max((e["started_at"] for e in execs), default=None)
        cost_sum    = round(sum(float(e.get("total_cost") or 0) for e in execs), 4)
        avg_ms      = int(sum(int(e.get("execution_time_ms") or 0) for e in execs) / total) if total else 0

        by_channel: dict[str, int] = {}
        delivered = opens = replies = 0
        for r in logs:
            ch = r.get("channel", "unknown")
            by_channel[ch] = by_channel.get(ch, 0) + 1
            if r["delivery_status"] in _DELIVERED_STATES:
                delivered += 1
            if r.get("opened_at"):
                opens += 1
            if r.get("replied_at"):
                replies += 1

        n = max(len(logs), 1)
        return {
            "workflow_id":            str(workflow_id),
            "period_days":            days,
            "total_executions":       total,
            "successful_executions":  successes,
            "failed_executions":      failures,
            "last_execution_at":      last_run,
            "total_cost":             cost_sum,
            "avg_execution_time_ms":  avg_ms,
            "messages_sent":          len(logs),
            "delivery_rate":          round(delivered * 100 / n, 2),
            "open_rate":              round(opens * 100 / n, 2),
            "reply_rate":             round(replies * 100 / n, 2),
            "by_channel":             by_channel,
        }

    # ── Per-channel rollup ──────────────────────────────────
    def by_channel(self, business_id: UUID, *, days: int = 30) -> list[dict]:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        logs = (
            self.db.table("ts_communication_logs")
            .select("channel,provider,delivery_status,cost,opened_at,replied_at")
            .eq("business_id", str(business_id))
            .gte("sent_at", since).execute().data or []
        )
        agg: dict[str, dict] = {}
        for r in logs:
            ch  = r.get("channel", "unknown")
            row = agg.setdefault(ch, {
                "channel": ch, "messages": 0, "delivered": 0, "failed": 0,
                "opened": 0, "replied": 0, "cost": 0.0,
            })
            row["messages"] += 1
            row["cost"]     += float(r.get("cost") or 0)
            if r["delivery_status"] in _DELIVERED_STATES:
                row["delivered"] += 1
            if r["delivery_status"] in ("failed", "bounced"):
                row["failed"] += 1
            if r.get("opened_at"):  row["opened"]  += 1
            if r.get("replied_at"): row["replied"] += 1
        return [
            {**row,
             "cost":          round(row["cost"], 4),
             "delivery_rate": round(row["delivered"] * 100 / max(row["messages"], 1), 2),
             "open_rate":     round(row["opened"]    * 100 / max(row["messages"], 1), 2),
             "reply_rate":    round(row["replied"]   * 100 / max(row["messages"], 1), 2)}
            for row in agg.values()
        ]

    # ── Per-workflow rollup ─────────────────────────────────
    def by_workflow(self, business_id: UUID, *, days: int = 30) -> list[dict]:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        wfs = (
            self.db.table("ts_workflows").select("id,name")
            .eq("business_id", str(business_id)).execute().data or []
        )
        out = []
        for w in wfs:
            stats = self.workflow_stats(
                business_id=business_id, workflow_id=UUID(w["id"]), days=days,
            )
            out.append({"workflow_id": w["id"], "workflow_name": w["name"], **stats})
        return out

    # ── Cost breakdown ──────────────────────────────────────
    def costs(self, business_id: UUID, *, days: int = 30) -> dict:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        logs = (
            self.db.table("ts_communication_logs").select("channel,provider,cost")
            .eq("business_id", str(business_id))
            .gte("sent_at", since).execute().data or []
        )
        by_ch: dict[str, float] = {}
        by_pv: dict[str, float] = {}
        total = 0.0
        for r in logs:
            c   = float(r.get("cost") or 0)
            ch  = r.get("channel") or "unknown"
            pv  = r.get("provider") or "unknown"
            by_ch[ch] = round(by_ch.get(ch, 0) + c, 4)
            by_pv[pv] = round(by_pv.get(pv, 0) + c, 4)
            total += c
        return {
            "period_days":        days,
            "total_cost":         round(total, 4),
            "by_channel":         by_ch,
            "by_provider":        by_pv,
            "messages":           len(logs),
            "avg_cost_per_message": round(total / max(len(logs), 1), 6),
        }

    # ── ROI estimate ────────────────────────────────────────
    def roi(self, business_id: UUID, *,
            days: int = 30, manual_minutes_per_message: float = 5.0,
            hourly_rate: float = 35.0) -> dict:
        """
        Estimates ROI: if every delivered message replaced ~N minutes of manual
        outreach at $rate/hr, the labour saved minus our cost = net gain.
        """
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        logs = (
            self.db.table("ts_communication_logs").select("delivery_status,cost,opened_at,replied_at")
            .eq("business_id", str(business_id))
            .gte("sent_at", since).execute().data or []
        )
        delivered = sum(1 for r in logs if r["delivery_status"] in _DELIVERED_STATES)
        cost      = round(sum(float(r.get("cost") or 0) for r in logs), 4)
        replied   = sum(1 for r in logs if r.get("replied_at"))
        labour_minutes = delivered * manual_minutes_per_message
        labour_value   = round(labour_minutes / 60 * hourly_rate, 2)
        net_value      = round(labour_value - cost, 2)
        return {
            "period_days":           days,
            "messages":              len(logs),
            "delivered":             delivered,
            "replied":               replied,
            "platform_cost":         cost,
            "labour_minutes_saved":  round(labour_minutes, 2),
            "labour_value_saved":    labour_value,
            "net_value":             net_value,
            "roi_multiple":          round(labour_value / max(cost, 0.000001), 2),
            "assumptions": {
                "manual_minutes_per_message": manual_minutes_per_message,
                "hourly_rate":                hourly_rate,
            },
        }

    # ── helpers ──────────────────────────────────────────────
    def _count(self, table: str, business_id: UUID, *, extra: Optional[dict] = None) -> int:
        q = self.db.table(table).select("id", count="exact").eq("business_id", str(business_id))
        for k, v in (extra or {}).items():
            q = q.eq(k, v)
        return q.execute().count or 0
