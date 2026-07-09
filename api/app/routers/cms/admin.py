"""
Admin CMS routers — content management. Guarded by require_cms_admin.
Hidden from public OpenAPI docs (include_in_schema=False).
"""
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.routers.cms._deps import require_cms_admin
from app.schemas.cms import (
    JobCreate,
    JobResponse,
    MediaResponse,
    PageCreate,
    PageResponse,
    PostCreate,
    PostResponse,
)
from app.schemas.common import SuccessResponse
from app.services.cms import CMSService, MediaService

logger = logging.getLogger(__name__)
router = APIRouter(
    dependencies=[Depends(require_cms_admin)],
    include_in_schema=False,
)

_DELETABLE = {"pages", "blog_posts", "jobs", "authors", "categories", "redirects"}


@router.post("/pages", response_model=PageResponse, summary="Create/update a page")
async def upsert_page(payload: PageCreate):
    return await CMSService().upsert_page(payload)


@router.post("/posts", response_model=PostResponse, summary="Create/update a post")
async def upsert_post(payload: PostCreate):
    return await CMSService().upsert_post(payload)


@router.post("/jobs", response_model=JobResponse, summary="Create/update a job")
async def upsert_job(payload: JobCreate):
    return await CMSService().upsert_job(payload)


@router.post("/media", response_model=MediaResponse, summary="Upload media")
async def upload_media(
    file: UploadFile = File(...),
    alt_text: str = Form(default=""),
    caption: str = Form(default=""),
):
    data = await file.read()
    return await MediaService().upload(
        filename=file.filename or "upload.bin",
        data=data,
        content_type=file.content_type,
        alt_text=alt_text,
        caption=caption,
    )


@router.delete("/{table}/{row_id}", response_model=SuccessResponse, summary="Delete a row")
async def delete_row(table: str, row_id: str):
    if table not in _DELETABLE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Table not deletable here")
    await CMSService().delete_row(table, row_id)
    return SuccessResponse(success=True, message="Deleted")
