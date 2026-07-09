from fastapi import APIRouter

from .admin import router as admin_router
from .public import router as public_router

cms_router = APIRouter(prefix="/cms", tags=["CMS"])
cms_router.include_router(public_router)
cms_router.include_router(admin_router, prefix="/admin")

__all__ = ["cms_router"]
