"""
CMS schemas — pages, blog/research posts, jobs, applications, media.
Mirrors the cms.* tables (see website repo migration 0001_cms_schema.sql).
Write models are lenient on optional fields so drafts can be saved partially.
"""
from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

Status = Literal["draft", "published", "archived"]
ContentType = Literal["blog", "research"]
JobStatus = Literal["draft", "published", "closed", "archived"]


# ── Pages ───────────────────────────────────────────────────────────
class PageCreate(BaseModel):
    slug: str
    title: str
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    og_image_id: Optional[UUID] = None
    content: list[dict[str, Any]] = Field(default_factory=list)
    status: Status = "draft"
    published_at: Optional[datetime] = None


class PageResponse(PageCreate):
    id: UUID
    created_at: datetime
    updated_at: datetime


# ── Posts (blog + research, one table) ──────────────────────────────
class PostCreate(BaseModel):
    content_type: ContentType = "blog"
    slug: str
    title: str
    excerpt: Optional[str] = None
    body: Optional[str] = None
    cover_image_id: Optional[UUID] = None
    author_id: Optional[UUID] = None
    category_id: Optional[UUID] = None
    tags: list[str] = Field(default_factory=list)
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    reading_time: Optional[int] = None
    status: Status = "draft"
    published_at: Optional[datetime] = None
    related_post_ids: list[UUID] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PostResponse(PostCreate):
    id: UUID
    created_at: datetime
    updated_at: datetime


# ── Jobs ────────────────────────────────────────────────────────────
class JobCreate(BaseModel):
    slug: str
    title: str
    department: Optional[str] = None
    location: Optional[str] = None
    employment_type: Optional[str] = None
    workplace_type: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: str = "USD"
    status: JobStatus = "draft"
    posted_at: Optional[datetime] = None
    closes_at: Optional[datetime] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class JobResponse(JobCreate):
    id: UUID
    created_at: datetime
    updated_at: datetime


# ── Job applications (public submit) ────────────────────────────────
class JobApplicationCreate(BaseModel):
    full_name: str
    email: EmailStr
    phone: Optional[str] = None
    resume_url: Optional[str] = None
    cover_letter: Optional[str] = None
    linkedin_url: Optional[str] = None


# ── Media ───────────────────────────────────────────────────────────
class MediaResponse(BaseModel):
    id: UUID
    storage_path: str
    public_url: str
    alt_text: Optional[str] = None
    caption: Optional[str] = None
    mime_type: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    size_bytes: Optional[int] = None
    created_at: datetime
