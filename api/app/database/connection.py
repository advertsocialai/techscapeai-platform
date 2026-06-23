"""
Supabase database connection and client initialization.
Uses existing Supabase credentials from environment variables.
"""
from supabase import create_client, Client
from app.core.config import settings

_supabase_client: Client | None = None


def get_supabase() -> Client:
    """Get or create the Supabase client (singleton)."""
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_ANON_KEY,
        )
    return _supabase_client


def get_supabase_admin() -> Client:
    """
    Get a Supabase client with the service role key (bypasses RLS).
    Use only in server-side operations that require admin access.
    """
    return create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_SERVICE_ROLE_KEY,
    )
