"""
Contact form router — handles contact submissions from the website.
"""
from fastapi import APIRouter, HTTPException, status, Request
from typing import Optional

from app.schemas.contact import ContactCreate, ContactResponse
from app.schemas.common import SuccessResponse, PaginatedResponse
from app.services.contact_service import ContactService
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "",
    response_model=SuccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a contact form",
    description="Stores the contact submission in the database and triggers a notification email.",
)
async def submit_contact(
    payload: ContactCreate,
    request: Request,
):
    """
    Accept contact form submissions from the TechScape AI website.
    Validates input and stores in Supabase `contact_submissions` table.
    """
    service = ContactService()
    try:
        submission = await service.create(payload)
        logger.info(f"New contact submission from {submission.email} (id={submission.id})")
        return SuccessResponse(
            success=True,
            message="Thank you for reaching out! We'll get back to you within 24 hours.",
        )
    except Exception as e:
        logger.error(f"Failed to save contact submission: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process your request. Please try again.",
        )


@router.get(
    "",
    response_model=PaginatedResponse[ContactResponse],
    summary="List all contact submissions",
    description="Admin endpoint — returns paginated contact submissions.",
    include_in_schema=False,  # Hidden from public docs
)
async def list_contacts(
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
):
    """Admin: list all contact submissions with pagination."""
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20

    service = ContactService()
    rows, total = await service.get_all(page=page, page_size=page_size, status=status)

    return PaginatedResponse(
        data=rows,
        total=total,
        page=page,
        page_size=page_size,
        has_next=(page * page_size) < total,
        has_prev=page > 1,
    )
