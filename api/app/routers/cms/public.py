"""
Public CMS routers — what the website reads. Published content only.
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.schemas.cms import (
    JobApplicationCreate,
    JobResponse,
    PageResponse,
    PostResponse,
)
from app.schemas.common import PaginatedResponse, SuccessResponse
from app.services.cms import CMSService

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Pages ───────────────────────────────────────────────────────────
@router.get("/pages/{slug}", response_model=PageResponse, summary="Get a published page")
async def get_page(slug: str):
    page = await CMSService().get_page(slug)
    if not page:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Page not found")
    return page


# ── Posts (blog + research) ─────────────────────────────────────────
@router.get(
    "/posts",
    response_model=PaginatedResponse[PostResponse],
    summary="List published posts (blog + research)",
)
async def list_posts(
    content_type: Optional[str] = Query(default=None, pattern="^(blog|research)$"),
    tag: Optional[str] = None,
    category: Optional[str] = None,
    page: int = 1,
    page_size: int = Query(default=20, le=100),
):
    if page < 1:
        page = 1
    rows, total = await CMSService().list_posts(
        content_type=content_type, tag=tag, category=category,
        page=page, page_size=page_size,
    )
    return PaginatedResponse(
        data=rows, total=total, page=page, page_size=page_size,
        has_next=(page * page_size) < total, has_prev=page > 1,
    )


@router.get("/posts/{slug}", response_model=PostResponse, summary="Get a published post")
async def get_post(slug: str):
    post = await CMSService().get_post(slug)
    if not post:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")
    return post


# ── Jobs ────────────────────────────────────────────────────────────
@router.get("/jobs", response_model=list[JobResponse], summary="List published jobs")
async def list_jobs(department: Optional[str] = None):
    return await CMSService().list_jobs(department=department)


@router.get("/jobs/{slug}", response_model=JobResponse, summary="Get a published job")
async def get_job(slug: str):
    job = await CMSService().get_job(slug)
    if not job:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return job


@router.post(
    "/jobs/{slug}/apply",
    response_model=SuccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Apply to a job",
)
async def apply_to_job(slug: str, payload: JobApplicationCreate, request: Request):
    ok = await CMSService().create_application(
        job_slug=slug,
        data=payload.model_dump(mode="json"),
        ip=request.client.host if request.client else None,
        ua=request.headers.get("user-agent"),
    )
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found or closed")
    return SuccessResponse(success=True, message="Application received. Thank you!")


# ── Settings + sitemap ──────────────────────────────────────────────
@router.get("/settings/{key}", summary="Get a site setting")
async def get_setting(key: str):
    setting = await CMSService().get_setting(key)
    if not setting:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Setting not found")
    return setting


@router.get("/sitemap-urls", summary="All published URLs for sitemap generation")
async def sitemap_urls():
    return await CMSService().sitemap_urls()
