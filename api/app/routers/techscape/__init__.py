"""TechScape Workflow Automation Platform — router registry."""
from fastapi import APIRouter

from .admin       import router as admin_router
from .ai          import router as ai_router
from .analytics   import router as analytics_router
from .auth        import router as auth_router
from .billing     import router as billing_router
from .businesses  import router as businesses_router
from .contacts    import router as contacts_router
from .demo        import router as demo_router
from .executions  import router as executions_router
from .gdpr        import router as gdpr_router
from .integrations import router as integrations_router
from .send        import router as send_router
from .templates   import router as templates_router
from .webhooks    import router as webhooks_router
from .workflows   import router as workflows_router


# All routes prefixed with /techscape/v1
ts_router = APIRouter(prefix="/techscape/v1")

ts_router.include_router(auth_router,         prefix="/auth",         tags=["TechScape · Auth"])
ts_router.include_router(businesses_router,   prefix="/businesses",   tags=["TechScape · Businesses"])
ts_router.include_router(workflows_router,    prefix="/workflows",    tags=["TechScape · Workflows"])
ts_router.include_router(templates_router,    prefix="/templates",    tags=["TechScape · Templates"])
ts_router.include_router(executions_router,   prefix="",              tags=["TechScape · Executions"])
ts_router.include_router(contacts_router,     prefix="/contacts",     tags=["TechScape · Contacts"])
ts_router.include_router(integrations_router, prefix="/integrations", tags=["TechScape · Integrations"])
ts_router.include_router(ai_router,           prefix="/ai",           tags=["TechScape · AI"])
ts_router.include_router(send_router,         prefix="",              tags=["TechScape · Send"])
ts_router.include_router(analytics_router,    prefix="/analytics",    tags=["TechScape · Analytics"])
ts_router.include_router(billing_router,      prefix="/billing",      tags=["TechScape · Billing"])
ts_router.include_router(gdpr_router,         prefix="/gdpr",         tags=["TechScape · GDPR"])
ts_router.include_router(admin_router,        prefix="/admin",        tags=["TechScape · Admin"])
ts_router.include_router(webhooks_router,     prefix="/webhooks",     tags=["TechScape · Webhooks"])
ts_router.include_router(demo_router,         prefix="/demo",         tags=["TechScape · Demo"])

__all__ = ["ts_router"]
