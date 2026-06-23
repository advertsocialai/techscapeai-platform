"""
Contact form service — stores submissions in Supabase.
"""
from uuid import uuid4
from datetime import datetime, timezone
from typing import List, Optional

from app.database.connection import get_supabase_admin
from app.schemas.contact import ContactCreate, ContactResponse
import logging

logger = logging.getLogger(__name__)

TABLE = "contact_submissions"


class ContactService:
    def __init__(self):
        self.db = get_supabase_admin()

    async def create(self, data: ContactCreate) -> ContactResponse:
        """Insert a new contact submission into the database."""
        record = {
            "id": str(uuid4()),
            "name": data.name,
            "email": data.email,
            "company": data.company,
            "interest": data.interest,
            "message": data.message,
            "status": "new",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            response = self.db.table(TABLE).insert(record).execute()
            if response.data:
                row = response.data[0]
                return ContactResponse(**row)
            raise ValueError("Failed to insert contact submission")
        except Exception as e:
            logger.error(f"ContactService.create error: {e}")
            raise

    async def get_all(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
    ) -> tuple[List[ContactResponse], int]:
        """Retrieve paginated contact submissions."""
        query = self.db.table(TABLE).select("*", count="exact")

        if status:
            query = query.eq("status", status)

        offset = (page - 1) * page_size
        query = query.order("created_at", desc=True).range(offset, offset + page_size - 1)

        response = query.execute()
        total = response.count or 0
        rows = [ContactResponse(**row) for row in (response.data or [])]
        return rows, total

    async def update_status(self, contact_id: str, status: str) -> Optional[ContactResponse]:
        """Update the status of a contact submission."""
        response = (
            self.db.table(TABLE)
            .update({"status": status})
            .eq("id", contact_id)
            .execute()
        )
        if response.data:
            return ContactResponse(**response.data[0])
        return None
