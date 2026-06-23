"""Audit log helper — single record per write."""
from __future__ import annotations
from typing import Any, Optional
from uuid import UUID

from app.database import get_supabase_admin


def write_audit(
    *,
    business_id: Optional[str | UUID] = None,
    user_id:     Optional[str | UUID] = None,
    action:      str,
    resource_type: Optional[str] = None,
    resource_id:   Optional[str | UUID] = None,
    details:       Optional[dict[str, Any]] = None,
    ip_address:    Optional[str] = None,
    user_agent:    Optional[str] = None,
) -> None:
    try:
        get_supabase_admin().table("ts_audit_logs").insert({
            "business_id":   str(business_id) if business_id else None,
            "user_id":       str(user_id) if user_id else None,
            "action":        action,
            "resource_type": resource_type,
            "resource_id":   str(resource_id) if resource_id else None,
            "details":       details or {},
            "ip_address":    ip_address,
            "user_agent":    user_agent,
        }).execute()
    except Exception:
        # Audit must never break the request flow. Swallow.
        import logging
        logging.getLogger(__name__).warning("audit log write failed", exc_info=True)
