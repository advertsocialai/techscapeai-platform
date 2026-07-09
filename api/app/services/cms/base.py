"""
CMS services — data access for the cms.* schema.

All CMS tables live in the Postgres `cms` schema, isolated from the
platform's public/ts_/travel_ tables. We reuse the app's existing
service-role client (get_supabase_admin) and scope it to `cms`.
"""
from supabase import Client

from app.database.connection import get_supabase_admin


def cms_db() -> Client:
    """Service-role Supabase client scoped to the `cms` schema.

    Reuses the app's admin client (bypasses RLS); .schema('cms') pins
    PostgREST to the cms namespace so calls read/write cms.* tables.
    """
    return get_supabase_admin().schema("cms")
