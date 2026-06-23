"""
Newsletter subscription router.
"""
from fastapi import APIRouter, HTTPException, status

from app.schemas.newsletter import NewsletterSubscribe, NewsletterResponse
from app.schemas.common import SuccessResponse
from app.services.newsletter_service import NewsletterService
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/subscribe",
    response_model=SuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Subscribe to newsletter",
)
async def subscribe(payload: NewsletterSubscribe):
    """
    Subscribe an email address to the TechScape AI newsletter.
    Handles re-subscription gracefully.
    """
    service = NewsletterService()
    try:
        subscriber, is_new = await service.subscribe(payload)
        message = (
            "You've successfully subscribed to TechScape AI insights!"
            if is_new
            else "You're already subscribed. Welcome back!"
        )
        logger.info(f"Newsletter subscription: {subscriber.email} (new={is_new})")
        return SuccessResponse(success=True, message=message)
    except Exception as e:
        logger.error(f"Newsletter subscribe error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process subscription. Please try again.",
        )


@router.post(
    "/unsubscribe",
    response_model=SuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Unsubscribe from newsletter",
)
async def unsubscribe(payload: NewsletterSubscribe):
    """Unsubscribe an email address from the newsletter."""
    service = NewsletterService()
    try:
        success = await service.unsubscribe(payload.email)
        return SuccessResponse(
            success=success,
            message="You've been unsubscribed." if success else "Email not found.",
        )
    except Exception as e:
        logger.error(f"Newsletter unsubscribe error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process unsubscription.",
        )
