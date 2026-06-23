"""AI agent endpoints — message generation, sentiment, intent, summarization,
optimization, and template generation."""
from __future__ import annotations
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.schemas.techscape import (
    AIGenerateIn, AIGenerateOut, AISentimentIn, AISentimentOut,
)
from app.services.techscape import AIService
from app.services.techscape.workflow_service import WorkflowService
from app.services.techscape.execution_service import ExecutionService

from ._deps import require_business

router = APIRouter()


class IntentIn(BaseModel):
    text: str


class IntentOut(BaseModel):
    intent: str
    confidence: float
    rationale: str


class SummarizeIn(BaseModel):
    messages: list[dict]


class SummarizeOut(BaseModel):
    summary: str
    next_steps: list[str] = []
    tone: str = "neutral"
    model: str


class OptimizeWorkflowIn(BaseModel):
    workflow_id: str | None = None


class OptimizeWorkflowOut(BaseModel):
    recommendations: list[str]
    expected_cost_delta: float = 0.0
    expected_delivery_delta: float = 0.0
    model: str


class GenerateTemplateIn(BaseModel):
    channel: str
    scenario: str
    tone: str = "friendly_professional"
    brand: str | None = None


class GenerateTemplateOut(BaseModel):
    subject: str | None = None
    content: str
    variables: list[str] = []
    model: str


# ── Endpoints ────────────────────────────────────────────────────
@router.post("/generate-message", response_model=AIGenerateOut)
async def generate_message(payload: AIGenerateIn, _: dict = Depends(require_business)):
    res = await AIService().generate_message(
        context=payload.context, channel=payload.channel,
        client_data=payload.client_data,
        business_context=payload.business_context,
        tone=payload.tone, max_chars=payload.max_chars,
    )
    return AIGenerateOut(
        channel=payload.channel,
        content=res["body"],
        subject_line=res.get("subject"),
        model=res["model"],
        input_tokens=res.get("input_tokens"),
        output_tokens=res.get("output_tokens"),
    )


@router.post("/analyze-sentiment", response_model=AISentimentOut)
async def analyze_sentiment(payload: AISentimentIn, _: dict = Depends(require_business)):
    return await AIService().analyze_sentiment(text=payload.text)


@router.post("/classify-intent", response_model=IntentOut)
async def classify_intent(payload: IntentIn, _: dict = Depends(require_business)):
    return await AIService().classify_intent(text=payload.text)


@router.post("/summarize-conversation", response_model=SummarizeOut)
async def summarize_conversation(payload: SummarizeIn, _: dict = Depends(require_business)):
    return await AIService().summarize_conversation(messages=payload.messages)


@router.post("/optimize-workflow", response_model=OptimizeWorkflowOut)
async def optimize_workflow(payload: OptimizeWorkflowIn,
                            biz: dict = Depends(require_business)):
    if not payload.workflow_id:
        return await AIService().optimize_workflow(workflow={}, recent_logs=[])
    try:
        wid = UUID(payload.workflow_id)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "bad workflow_id")
    wf = WorkflowService().get_workflow(wid, UUID(biz["id"]))
    if not wf:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "workflow not found")
    logs = ExecutionService().list_communications(UUID(biz["id"]), limit=200)
    return await AIService().optimize_workflow(workflow=wf, recent_logs=logs)


@router.post("/generate-template", response_model=GenerateTemplateOut)
async def generate_template(payload: GenerateTemplateIn,
                            _: dict = Depends(require_business)):
    return await AIService().generate_template(
        channel=payload.channel, scenario=payload.scenario,
        tone=payload.tone, brand=payload.brand,
    )
