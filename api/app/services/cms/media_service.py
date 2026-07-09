"""
CMS media service — uploads to the `cms-media` Storage bucket and
records a row in cms.media. This is the "import image in backend ->
serve on frontend" flow.
"""
from datetime import datetime, timezone
from typing import Any, Optional

from app.database.connection import get_supabase_admin
from app.services.cms.base import cms_db

MEDIA_BUCKET = "cms-media"


class MediaService:
    async def upload(
        self,
        filename: str,
        data: bytes,
        content_type: Optional[str],
        alt_text: str = "",
        caption: str = "",
    ) -> dict[str, Any]:
        path = f"{datetime.now(timezone.utc):%Y/%m}/{filename}"
        # Storage lives on the default client (not schema-scoped).
        storage = get_supabase_admin().storage.from_(MEDIA_BUCKET)
        storage.upload(
            path,
            data,
            file_options={
                "content-type": content_type or "application/octet-stream",
                "upsert": "true",
            },
        )
        public_url = storage.get_public_url(path)
        row = {
            "storage_path": path,
            "public_url": public_url,
            "alt_text": alt_text or None,
            "caption": caption or None,
            "mime_type": content_type,
            "size_bytes": len(data),
        }
        res = cms_db().table("media").insert(row).execute()
        return res.data[0]

    async def list_media(self, limit: int = 50) -> list[dict[str, Any]]:
        res = (
            cms_db().table("media").select("*")
            .order("created_at", desc=True).limit(limit).execute()
        )
        return res.data or []
