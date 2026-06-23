"""
Workflow execution engine.

Features:
  • Sequential step execution with conditional branching (`condition_logic`)
  • Per-step retry with exponential backoff (capped)
  • Subscription cap + active-status enforcement
  • TCPA window check for sms / voice / voicemail
  • Contact-consent enforcement (do_not_contact + per-channel consent flags)
  • Communication log written for every send (success or failure)
  • Idempotent execution row; bumps execution_count and rolls up cost
"""
from __future__ import annotations
import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

import httpx

from app.database import get_supabase_admin

from .ai_service        import AIService
from .business_service  import BusinessService
from .conditions        import evaluate as eval_condition
from .providers.router  import get_router
from .tcpa              import is_within_tcpa_window
from .template_service  import TemplateService

logger = logging.getLogger(__name__)


CHANNEL_BY_ACTION = {
    "send_email":      "email",
    "send_sms":        "sms",
    "send_whatsapp":   "whatsapp",
    "make_voice_call": "voice",
    "send_voicemail":  "voicemail",
}


class ExecutionService:
    def __init__(self) -> None:
        self.db        = get_supabase_admin()
        self.router    = get_router()
        self.ai        = AIService()
        self.templates = TemplateService()
        self.bizsvc    = BusinessService()

    # ── Public entry point ────────────────────────────────────
    async def trigger(
        self,
        *,
        workflow_id: UUID,
        business_id: UUID,
        trigger_data: dict[str, Any],
        client_email: Optional[str] = None,
        client_phone: Optional[str] = None,
        client_name:  Optional[str] = None,
        client_identifier: Optional[str] = None,
    ) -> dict:
        wf = (
            self.db.table("ts_workflows").select("*")
            .eq("id", str(workflow_id)).eq("business_id", str(business_id))
            .limit(1).execute().data
        )
        if not wf:
            raise ValueError("workflow not found")
        workflow = wf[0]
        if not workflow["is_active"]:
            raise ValueError("workflow is not active")

        biz = self.bizsvc.get(business_id)
        if not biz or biz.get("status") != "active":
            raise ValueError("business not active")

        steps = (
            self.db.table("ts_workflow_steps").select("*")
            .eq("workflow_id", str(workflow_id))
            .eq("enabled", True)
            .order("step_number").execute().data
            or []
        )

        started = datetime.now(timezone.utc)
        exec_row = (
            self.db.table("ts_workflow_executions").insert({
                "workflow_id":       str(workflow_id),
                "business_id":       str(business_id),
                "trigger_data":      trigger_data,
                "execution_status":  "in_progress",
                "total_steps":       len(steps),
                "completed_steps":   0,
                "failed_steps":      0,
                "total_cost":        0.0,
                "started_at":        started.isoformat(),
                "client_identifier": client_identifier,
                "client_email":      client_email,
                "client_phone":      client_phone,
                "client_name":       client_name,
            }).execute().data[0]
        )
        execution_id = UUID(exec_row["id"])

        ctx: dict[str, Any] = {
            "trigger_data": trigger_data,
            **trigger_data,
            "client": {
                "name":       client_name,
                "email":      client_email,
                "phone":      client_phone,
                "identifier": client_identifier,
            },
            "business": {
                "id":       biz["id"],
                "name":     biz.get("name"),
                "timezone": biz.get("timezone") or "UTC",
                "tier":     biz.get("subscription_tier") or "starter",
            },
        }

        # contact lookup (consent + DNC)
        contact = self._find_contact(business_id, client_email, client_phone)
        if contact:
            ctx["contact"] = contact

        completed = 0
        failed    = 0
        skipped   = 0
        cost_sum  = 0.0

        # Build a step-number → step map for branching jumps
        steps_by_no = {s["step_number"]: s for s in steps}
        step_numbers = sorted(steps_by_no.keys())
        i = 0
        while i < len(step_numbers):
            step = steps_by_no[step_numbers[i]]
            try:
                outcome = await self._run_step(
                    step=step, execution_id=execution_id,
                    business_id=business_id, workflow_id=workflow_id,
                    biz=biz, contact=contact, context=ctx,
                )
                if outcome["status"] == "completed":
                    completed += 1
                elif outcome["status"] == "skipped":
                    skipped += 1
                else:
                    failed += 1
                cost_sum += outcome.get("cost", 0.0)

                jump_to = outcome.get("jump_to")
                if jump_to is not None and jump_to in steps_by_no:
                    i = step_numbers.index(jump_to)
                    continue
            except Exception:
                logger.exception("step %s failed", step.get("id"))
                failed += 1
            i += 1

        ended = datetime.now(timezone.utc)
        if completed == 0 and failed > 0:
            status = "failed"
        elif failed > 0:
            status = "completed"  # partial — still mark as completed per spec
        else:
            status = "completed"

        self.db.table("ts_workflow_executions").update({
            "execution_status":  status,
            "completed_steps":   completed,
            "failed_steps":      failed,
            "total_cost":        round(cost_sum, 4),
            "completed_at":      ended.isoformat(),
            "execution_time_ms": int((ended - started).total_seconds() * 1000),
        }).eq("id", str(execution_id)).execute()

        # bump execution_count
        self.db.table("ts_workflows").update({
            "execution_count": (workflow.get("execution_count") or 0) + 1,
        }).eq("id", str(workflow_id)).execute()

        return self.get_execution(execution_id, business_id) or exec_row

    # ── Single step ───────────────────────────────────────────
    async def _run_step(
        self,
        *,
        step: dict,
        execution_id: UUID,
        business_id:  UUID,
        workflow_id:  UUID,
        biz:          dict,
        contact:      Optional[dict],
        context:      dict[str, Any],
    ) -> dict:
        action = step["action_type"]
        cfg    = step.get("action_config") or {}
        delay  = step.get("delay_seconds") or 0
        # Real Celery integration would honour the full delay; in-process keep it short.
        if delay and delay <= 2:
            await asyncio.sleep(delay)

        # Conditional branching
        if action == "conditional_branch":
            ok = eval_condition(step.get("condition_logic"), context)
            cl = step.get("condition_logic") or {}
            target = (cl.get("then") if ok else cl.get("else")) if isinstance(cl, dict) else None
            jump_to = _to_step_number(target)
            return {"status": "completed", "cost": 0.0, "jump_to": jump_to}

        if action == "wait":
            return {"status": "completed", "cost": 0.0}

        if action == "http_webhook":
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    await client.post(
                        cfg["url"],
                        json={"context": context, **(cfg.get("payload") or {})},
                    )
            except Exception as e:
                logger.warning("http_webhook failed: %s", e)
                return {"status": "failed", "cost": 0.0}
            return {"status": "completed", "cost": 0.0}

        if action == "ai_generate_response":
            ai = await self.ai.generate_message(
                context=cfg.get("context", "follow_up"),
                channel=cfg.get("channel", "email"),
                client_data=context.get("client", {}),
                business_context=cfg.get("business_context", {}),
                tone=cfg.get("tone", "friendly_professional"),
            )
            context.setdefault("ai", {})[cfg.get("output_key", "last")] = ai
            return {"status": "completed", "cost": 0.0}

        if action in CHANNEL_BY_ACTION:
            return await self._send_message_step(
                step=step, action=action, cfg=cfg,
                execution_id=execution_id,
                business_id=business_id, workflow_id=workflow_id,
                biz=biz, contact=contact, context=context,
            )

        raise ValueError(f"unsupported action_type: {action}")

    async def _send_message_step(
        self, *, step, action, cfg, execution_id, business_id,
        workflow_id, biz, contact, context,
    ) -> dict:
        channel = CHANNEL_BY_ACTION[action]
        to_email = (context.get("client") or {}).get("email")
        to_phone = (context.get("client") or {}).get("phone")

        # 1. Subscription cap
        ok, reason = self.bizsvc.can_send_messages(business_id, 1)
        if not ok:
            return self._record_skip(
                execution_id, workflow_id, business_id, step, channel,
                to_email=to_email, to_phone=to_phone,
                reason=reason, content=cfg.get("content", ""),
            )

        # 2. DNC + per-channel consent
        if contact and contact.get("do_not_contact"):
            return self._record_skip(
                execution_id, workflow_id, business_id, step, channel,
                to_email=to_email, to_phone=to_phone,
                reason="contact has do_not_contact=true",
                content=cfg.get("content", ""),
            )
        if contact and not contact.get(f"consent_{channel}", True):
            return self._record_skip(
                execution_id, workflow_id, business_id, step, channel,
                to_email=to_email, to_phone=to_phone,
                reason=f"contact opted out of {channel}",
                content=cfg.get("content", ""),
            )

        # 3. TCPA window
        biz_tz = biz.get("timezone") or "UTC"
        ok_tcpa, why = is_within_tcpa_window(channel=channel, timezone_str=biz_tz)
        if not ok_tcpa:
            return self._record_skip(
                execution_id, workflow_id, business_id, step, channel,
                to_email=to_email, to_phone=to_phone,
                reason=why, content=cfg.get("content", ""),
            )

        # 4. Resolve content (template / AI fallback) and render variables
        content = cfg.get("content") or ""
        subject = cfg.get("subject")
        template_id = cfg.get("template_id")
        if template_id:
            tpl = self.templates.get(UUID(template_id), business_id)
            if tpl:
                content = tpl["content"]
                subject = subject or tpl.get("subject_line")
        if not content and cfg.get("ai_context"):
            ai = await self.ai.generate_message(
                context=cfg["ai_context"], channel=channel,
                client_data=context.get("client", {}),
                business_context=cfg.get("business_context", {}),
                tone=cfg.get("tone", "friendly_professional"),
            )
            content = ai["body"]
            if channel == "email" and not subject:
                subject = ai.get("subject")
        # Render {{var}} placeholders in both content and subject
        content = TemplateService.render(content, context)
        if subject:
            subject = TemplateService.render(subject, context)

        # 5. Send with retry (exponential backoff)
        send_res, retries = await self._send_with_retry(
            channel=channel, to_email=to_email, to_phone=to_phone,
            subject=subject, content=content,
            template_name=cfg.get("template_name"),
            template_params=cfg.get("template_params"),
            max_retries=int(step.get("max_retries") or 0),
            base_delay=int(step.get("retry_delay_seconds") or 1),
        )

        # 6. Log
        self.db.table("ts_communication_logs").insert({
            "execution_id":        str(execution_id),
            "workflow_id":         str(workflow_id),
            "step_id":             step["id"],
            "business_id":         str(business_id),
            "recipient_email":     to_email,
            "recipient_phone":     to_phone,
            "channel":             channel,
            "message_content":     (content or "")[:8000],
            "message_subject":     subject,
            "template_id":         template_id,
            "provider":            send_res.get("provider"),
            "provider_message_id": send_res.get("provider_message_id"),
            "delivery_status":     send_res.get("delivery_status", "queued"),
            "cost":                send_res.get("cost", 0.0),
            "error_message":       send_res.get("error"),
            "retry_count":         retries,
            "max_retries":         int(step.get("max_retries") or 0),
            "sent_at":             datetime.now(timezone.utc).isoformat(),
        }).execute()

        # 7. Bump usage if delivered/sent
        if send_res.get("delivery_status") in ("sent", "delivered"):
            self.bizsvc.increment_message_count(business_id, 1)
            return {"status": "completed", "cost": float(send_res.get("cost", 0.0))}

        return {"status": "failed", "cost": float(send_res.get("cost", 0.0))}

    async def _send_with_retry(
        self, *, channel, to_email, to_phone, subject, content,
        template_name, template_params, max_retries: int, base_delay: int,
    ) -> tuple[dict, int]:
        attempt = 0
        last: dict = {}
        while True:
            last = await self.router.send(
                channel=channel, to_email=to_email, to_phone=to_phone,
                subject=subject, content=content,
                template_name=template_name, template_params=template_params,
            )
            if last.get("delivery_status") not in (None, "failed"):
                return last, attempt
            if attempt >= max_retries:
                return last, attempt
            attempt += 1
            # Exponential backoff capped at 5s in-process — production would queue.
            wait = min(5, base_delay * (2 ** (attempt - 1))) + random.uniform(0, 0.25)
            await asyncio.sleep(wait)

    def _record_skip(
        self, execution_id, workflow_id, business_id, step, channel,
        *, to_email, to_phone, reason: str, content: str,
    ) -> dict:
        self.db.table("ts_communication_logs").insert({
            "execution_id":     str(execution_id),
            "workflow_id":      str(workflow_id),
            "step_id":          step["id"],
            "business_id":      str(business_id),
            "recipient_email":  to_email,
            "recipient_phone":  to_phone,
            "channel":          channel,
            "message_content":  (content or "")[:8000],
            "provider":         "internal",
            "delivery_status":  "failed",
            "cost":             0.0,
            "error_message":    f"skipped: {reason}",
            "retry_count":      0,
            "max_retries":      0,
            "sent_at":          datetime.now(timezone.utc).isoformat(),
        }).execute()
        return {"status": "skipped", "cost": 0.0}

    def _find_contact(
        self, business_id: UUID, email: Optional[str], phone: Optional[str],
    ) -> Optional[dict]:
        try:
            q = self.db.table("ts_business_contacts").select("*").eq(
                "business_id", str(business_id)
            )
            if email:
                r = q.eq("email", email).limit(1).execute().data
                if r:
                    return r[0]
            if phone:
                r = (
                    self.db.table("ts_business_contacts").select("*")
                    .eq("business_id", str(business_id))
                    .eq("phone", phone).limit(1).execute().data
                )
                if r:
                    return r[0]
        except Exception:
            return None
        return None

    # ── Read APIs ────────────────────────────────────────────
    def list_executions(self, business_id: UUID, *, workflow_id: Optional[UUID] = None,
                        limit: int = 50) -> list[dict]:
        q = self.db.table("ts_workflow_executions").select("*").eq(
            "business_id", str(business_id)
        )
        if workflow_id:
            q = q.eq("workflow_id", str(workflow_id))
        return q.order("started_at", desc=True).limit(limit).execute().data or []

    def get_execution(self, execution_id: UUID, business_id: UUID) -> dict | None:
        r = (
            self.db.table("ts_workflow_executions").select("*")
            .eq("id", str(execution_id)).eq("business_id", str(business_id))
            .limit(1).execute()
        )
        return r.data[0] if r.data else None

    def list_communications(self, business_id: UUID, *, execution_id: Optional[UUID] = None,
                            limit: int = 100) -> list[dict]:
        q = self.db.table("ts_communication_logs").select("*").eq(
            "business_id", str(business_id)
        )
        if execution_id:
            q = q.eq("execution_id", str(execution_id))
        return q.order("sent_at", desc=True).limit(limit).execute().data or []


def _to_step_number(value: Any) -> Optional[int]:
    """Accepts 'step_4' or 4 → 4."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    s = str(value).strip().lower()
    if s.startswith("step_"):
        s = s[len("step_"):]
    try:
        return int(s)
    except ValueError:
        return None
