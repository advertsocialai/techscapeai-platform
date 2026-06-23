"""Language Bridge endpoint — translate to/from Indian languages."""
from fastapi import APIRouter, Depends

from app.schemas.travel import TranslateIn, TranslateOut
from app.services.travel import LanguageBridge
from app.routers.techscape._deps import require_business

router = APIRouter()


@router.post("/translate", response_model=TranslateOut)
async def translate(req: TranslateIn, biz: dict = Depends(require_business)):
    return await LanguageBridge().translate(
        text=req.text,
        source_lang=req.source_lang,
        target_lang=req.target_lang,
        formality=req.formality,
    )
