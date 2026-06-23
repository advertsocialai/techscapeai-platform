"""
Newsletter subscription service — stores subscriptions in Supabase.
"""
from uuid import uuid4
from datetime import datetime, timezone
from typing import Optional

from app.database.connection import get_supabase_admin
from app.schemas.newsletter import NewsletterSubscribe, NewsletterResponse
import logging

logger = logging.getLogger(__name__)

TABLE = "newsletter_subscribers"


class NewsletterService:
    def __init__(self):
        self.db = get_supabase_admin()

    async def subscribe(self, data: NewsletterSubscribe) -> tuple[NewsletterResponse, bool]:
        """
        Subscribe an email to the newsletter.
        Returns (subscriber, is_new) tuple.
        """
        # Check if already subscribed
        existing = (
            self.db.table(TABLE)
            .select("*")
            .eq("email", data.email)
            .execute()
        )
        if existing.data:
            row = existing.data[0]
            if not row.get("subscribed"):
                # Re-subscribe
                update = (
                    self.db.table(TABLE)
                    .update({"subscribed": True, "name": data.name})
                    .eq("email", data.email)
                    .execute()
                )
                row = update.data[0] if update.data else row
            return NewsletterResponse(**row), False

        # New subscriber
        record = {
            "id": str(uuid4()),
            "email": data.email,
            "name": data.name,
            "subscribed": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            response = self.db.table(TABLE).insert(record).execute()
            if response.data:
                return NewsletterResponse(**response.data[0]), True
            raise ValueError("Failed to insert newsletter subscriber")
        except Exception as e:
            logger.error(f"NewsletterService.subscribe error: {e}")
            raise

    async def unsubscribe(self, email: str) -> bool:
        """Unsubscribe an email from the newsletter."""
        response = (
            self.db.table(TABLE)
            .update({"subscribed": False})
            .eq("email", email)
            .execute()
        )
        return bool(response.data)
