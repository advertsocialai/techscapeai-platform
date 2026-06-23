"""Franchisee Support Agent endpoint — Q&A grounded in the company wiki."""
from uuid import UUID

from fastapi import APIRouter, Depends

from app.schemas.travel import FranchiseeAnswer, FranchiseeAskIn
from app.services.travel import FranchiseeAgent
from app.routers.techscape._deps import require_business

router = APIRouter()


@router.post("/ask", response_model=FranchiseeAnswer)
async def ask_franchisee(req: FranchiseeAskIn, biz: dict = Depends(require_business)):
    return await FranchiseeAgent().ask(
        business_id=UUID(biz["id"]),
        question=req.question,
        franchisee_id=req.franchisee_id,
        franchisee_city=req.franchisee_city,
    )
