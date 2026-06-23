from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from datetime import datetime


class ContactCreate(BaseModel):
    name: str
    email: EmailStr
    company: Optional[str] = None
    interest: Optional[str] = None
    message: str

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name cannot be empty")
        if len(v) < 2:
            raise ValueError("Name must be at least 2 characters")
        if len(v) > 100:
            raise ValueError("Name cannot exceed 100 characters")
        return v

    @field_validator("message")
    @classmethod
    def message_must_not_be_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Message cannot be empty")
        if len(v) < 10:
            raise ValueError("Message must be at least 10 characters")
        if len(v) > 5000:
            raise ValueError("Message cannot exceed 5000 characters")
        return v

    @field_validator("company")
    @classmethod
    def sanitize_company(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            return v if v else None
        return v


class ContactResponse(BaseModel):
    id: str
    name: str
    email: str
    company: Optional[str]
    interest: Optional[str]
    message: str
    status: str
    created_at: datetime
