"""
Pydantic schemas for the TechScape Workflow Automation Platform.
Mirrors the Postgres tables prefixed with `ts_`.
"""
from __future__ import annotations
from datetime import datetime, date
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, ConfigDict


# ── Shared types ─────────────────────────────────────────────────
Channel = Literal["email", "sms", "whatsapp", "voice", "voicemail"]
ActionType = Literal[
    "send_email", "send_sms", "send_whatsapp", "make_voice_call",
    "send_voicemail", "ai_generate_response", "http_webhook",
    "conditional_branch", "wait",
]
TriggerType = Literal["event_based", "scheduled", "manual", "api_triggered"]
ExecutionStatus = Literal["pending", "in_progress", "completed", "failed", "paused", "cancelled"]
DeliveryStatus = Literal[
    "queued", "sent", "delivered", "failed", "bounced",
    "complained", "opened", "clicked", "replied",
]
Provider = Literal["twilio", "wapi", "sendgrid", "internal"]


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# ── Workflows ────────────────────────────────────────────────────
class WorkflowStepIn(_Base):
    step_number: int = Field(ge=1)
    action_type: ActionType
    action_config: dict[str, Any]
    condition_type: Literal["none", "if_then", "if_then_else", "switch"] = "none"
    condition_logic: Optional[dict[str, Any]] = None
    delay_seconds: int = 0
    max_retries: int = 3
    retry_delay_seconds: int = 300
    timeout_seconds: int = 3600
    enabled: bool = True


class WorkflowStepOut(WorkflowStepIn):
    id: UUID
    workflow_id: UUID
    created_at: datetime
    updated_at: datetime


class WorkflowIn(_Base):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    trigger_type: TriggerType
    trigger_event_type: Optional[str] = None
    trigger_config: dict[str, Any] = {}
    is_active: bool = True
    steps: list[WorkflowStepIn] = []


class WorkflowUpdate(_Base):
    name: Optional[str] = None
    description: Optional[str] = None
    trigger_type: Optional[TriggerType] = None
    trigger_event_type: Optional[str] = None
    trigger_config: Optional[dict[str, Any]] = None
    is_active: Optional[bool] = None
    is_archived: Optional[bool] = None


class WorkflowOut(_Base):
    id: UUID
    business_id: UUID
    name: str
    description: Optional[str] = None
    trigger_type: TriggerType
    trigger_event_type: Optional[str] = None
    trigger_config: dict[str, Any] = {}
    is_active: bool
    is_archived: bool
    version: int
    execution_count: int
    success_rate: float
    estimated_monthly_cost: float
    created_at: datetime
    updated_at: datetime
    steps: list[WorkflowStepOut] = []


# ── Templates ────────────────────────────────────────────────────
class TemplateIn(_Base):
    name: str
    description: Optional[str] = None
    channel: Channel
    content: str
    subject_line: Optional[str] = None
    variables: list[str] = []
    is_ai_generated: bool = False
    ai_prompt: Optional[str] = None
    media_urls: list[str] = []


class TemplateUpdate(_Base):
    name: Optional[str] = None
    description: Optional[str] = None
    content: Optional[str] = None
    subject_line: Optional[str] = None
    variables: Optional[list[str]] = None
    approval_status: Optional[Literal["draft", "pending_approval", "approved", "rejected"]] = None


class TemplateOut(_Base):
    id: UUID
    business_id: UUID
    name: str
    description: Optional[str] = None
    channel: Channel
    content: str
    subject_line: Optional[str] = None
    variables: list[Any] = []
    is_ai_generated: bool
    ai_prompt: Optional[str] = None
    approval_status: str
    usage_count: int
    conversion_rate: float
    created_at: datetime
    updated_at: datetime


class TemplatePreviewIn(_Base):
    sample_data: dict[str, Any] = {}


# ── Executions ───────────────────────────────────────────────────
class ExecutionTrigger(_Base):
    """Payload to start an execution of a workflow."""
    trigger_data: dict[str, Any] = {}
    client_identifier: Optional[str] = None
    client_email: Optional[EmailStr] = None
    client_phone: Optional[str] = None
    client_name: Optional[str] = None


class ExecutionOut(_Base):
    id: UUID
    workflow_id: UUID
    business_id: UUID
    execution_status: ExecutionStatus
    total_steps: Optional[int] = None
    completed_steps: int
    failed_steps: int
    error_message: Optional[str] = None
    total_cost: float
    started_at: datetime
    completed_at: Optional[datetime] = None
    execution_time_ms: Optional[int] = None
    client_identifier: Optional[str] = None
    client_email: Optional[str] = None
    client_phone: Optional[str] = None
    client_name: Optional[str] = None


class CommunicationLogOut(_Base):
    id: UUID
    execution_id: Optional[UUID] = None
    workflow_id: Optional[UUID] = None
    step_id: Optional[UUID] = None
    business_id: UUID
    channel: Channel
    provider: Optional[Provider] = None
    recipient_email: Optional[str] = None
    recipient_phone: Optional[str] = None
    message_subject: Optional[str] = None
    message_content: str
    delivery_status: DeliveryStatus
    cost: float
    sent_at: datetime
    delivered_at: Optional[datetime] = None
    error_message: Optional[str] = None


# ── Contacts ─────────────────────────────────────────────────────
class ContactIn(_Base):
    external_contact_id: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    name: Optional[str] = None
    preferred_channel: Optional[Channel] = None
    do_not_contact: bool = False
    consent_email: bool = True
    consent_sms: bool = True
    consent_whatsapp: bool = True
    consent_voice: bool = True
    tags: list[str] = []
    metadata: dict[str, Any] = {}


class ContactOut(ContactIn):
    id: UUID
    business_id: UUID
    last_contacted_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


# ── AI agent ─────────────────────────────────────────────────────
class AIGenerateIn(_Base):
    context: str = Field(description="High-level scenario, e.g. booking_confirmation_email")
    channel: Channel
    client_data: dict[str, Any] = {}
    business_context: dict[str, Any] = {}
    tone: str = "friendly_professional"
    max_chars: Optional[int] = None  # auto-applied for SMS (160), voicemail (~600), etc.


class AIGenerateOut(_Base):
    channel: Channel
    content: str
    subject_line: Optional[str] = None
    model: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


class AISentimentIn(_Base):
    text: str


class AISentimentOut(_Base):
    sentiment: Literal["positive", "neutral", "negative"]
    score: float = Field(ge=-1, le=1)
    rationale: str


# ── Send-message helper (one-off, outside a workflow) ────────────
class DirectSendIn(_Base):
    channel: Channel
    to_email: Optional[EmailStr] = None
    to_phone: Optional[str] = None
    subject: Optional[str] = None
    content: str
    business_id: UUID


class DirectSendOut(_Base):
    log_id: UUID
    provider: Provider
    delivery_status: DeliveryStatus
    provider_message_id: Optional[str] = None
    cost: float


# ── Analytics ────────────────────────────────────────────────────
class AnalyticsOverview(_Base):
    business_id: UUID
    total_workflows: int
    active_workflows: int
    total_executions_30d: int
    total_messages_30d: int
    total_cost_30d: float
    delivery_rate: float
    by_channel: dict[str, int]
