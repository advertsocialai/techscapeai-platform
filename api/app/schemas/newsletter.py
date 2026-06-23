from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from datetime import datetime


class NewsletterSubscribe(BaseModel):
    email: EmailStr
    name: Optional[str] = None

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            return v if v else None
        return v


class NewsletterResponse(BaseModel):
    id: str
    email: str
    name: Optional[str]
    subscribed: bool
    created_at: datetime
