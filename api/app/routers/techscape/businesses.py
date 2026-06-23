"""Business (tenant) registration + introspection.

Note: `/register` is intentionally unauthenticated — that's how a new
business creates itself. `/me` requires X-API-Key or JWT.
"""
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, EmailStr

from app.services.techscape import BusinessService

from ._deps import require_business

router = APIRouter()


class BusinessRegisterIn(BaseModel):
    name:          str
    contact_email: EmailStr
    contact_phone: str | None = None
    industry:      str = "travel"
    website_url:   str | None = None
    timezone:      str = "UTC"


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register_business(payload: BusinessRegisterIn):
    """Create a new business + emit a one-time API key."""
    return BusinessService().create(payload.model_dump(exclude_none=True))


@router.get("/me")
def me(biz: dict = Depends(require_business)):
    """Current business — never returns api_key_hash or password_hash."""
    return {k: v for k, v in biz.items()
            if k not in ("api_key_hash", "_user")}
