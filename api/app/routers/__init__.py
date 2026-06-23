from fastapi import APIRouter
from .contact import router as contact_router
from .newsletter import router as newsletter_router
from .health import router as health_router
from .techscape import ts_router
from .travel import travel_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["Health"])
api_router.include_router(contact_router, prefix="/contact", tags=["Contact"])
api_router.include_router(newsletter_router, prefix="/newsletter", tags=["Newsletter"])
api_router.include_router(ts_router)
api_router.include_router(travel_router)

__all__ = ["api_router"]
