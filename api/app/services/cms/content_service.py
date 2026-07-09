"""
CMS content service — pages, posts (blog + research), jobs, applications.

Thin data-access methods over the cms schema. Routers stay skinny and
call these, matching the ContactService pattern in this codebase.
"""
from datetime import datetime, timezone
from typing import Any, Optional

from app.schemas.cms import JobCreate, PageCreate, PostCreate
from app.services.cms.base import cms_db


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CMSService:
    # ── Pages ───────────────────────────────────────────────────────
    async def get_page(self, slug: str) -> Optional[dict[str, Any]]:
        res = (
            cms_db().table("pages").select("*")
            .eq("slug", slug).eq("status", "published")
            .maybe_single().execute()
        )
        return res.data if res else None

    async def upsert_page(self, payload: PageCreate) -> dict[str, Any]:
        row = payload.model_dump(mode="json", exclude_none=True)
        if row.get("status") == "published" and not row.get("published_at"):
            row["published_at"] = _now_iso()
        res = cms_db().table("pages").upsert(row, on_conflict="slug").execute()
        return res.data[0]

    # ── Posts (blog + research) ─────────────────────────────────────
    async def list_posts(
        self,
        content_type: Optional[str] = None,
        tag: Optional[str] = None,
        category: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        q = (
            cms_db().table("blog_posts")
            .select("*", count="exact")
            .eq("status", "published")
        )
        if content_type:
            q = q.eq("content_type", content_type)
        if category:
            q = q.eq("category_id", category)
        if tag:
            q = q.contains("tags", [tag])
        start = (page - 1) * page_size
        res = q.order("published_at", desc=True).range(start, start + page_size - 1).execute()
        return res.data or [], (res.count or 0)

    async def get_post(self, slug: str) -> Optional[dict[str, Any]]:
        res = (
            cms_db().table("blog_posts").select("*")
            .eq("slug", slug).eq("status", "published")
            .maybe_single().execute()
        )
        return res.data if res else None

    async def upsert_post(self, payload: PostCreate) -> dict[str, Any]:
        row = payload.model_dump(mode="json", exclude_none=True)
        if row.get("status") == "published" and not row.get("published_at"):
            row["published_at"] = _now_iso()
        res = cms_db().table("blog_posts").upsert(row, on_conflict="slug").execute()
        return res.data[0]

    # ── Jobs ────────────────────────────────────────────────────────
    async def list_jobs(self, department: Optional[str] = None) -> list[dict[str, Any]]:
        q = cms_db().table("jobs").select("*").eq("status", "published")
        if department:
            q = q.eq("department", department)
        res = q.order("posted_at", desc=True).execute()
        return res.data or []

    async def get_job(self, slug: str) -> Optional[dict[str, Any]]:
        res = (
            cms_db().table("jobs").select("*")
            .eq("slug", slug).eq("status", "published")
            .maybe_single().execute()
        )
        return res.data if res else None

    async def upsert_job(self, payload: JobCreate) -> dict[str, Any]:
        row = payload.model_dump(mode="json", exclude_none=True)
        if row.get("status") == "published" and not row.get("posted_at"):
            row["posted_at"] = _now_iso()
        res = cms_db().table("jobs").upsert(row, on_conflict="slug").execute()
        return res.data[0]

    async def create_application(
        self, job_slug: str, data: dict[str, Any], ip: Optional[str], ua: Optional[str]
    ) -> bool:
        job = (
            cms_db().table("jobs").select("id")
            .eq("slug", job_slug).eq("status", "published")
            .maybe_single().execute()
        )
        if not job or not job.data:
            return False
        row = dict(data)
        row["job_id"] = job.data["id"]
        row["ip_address"] = ip
        row["user_agent"] = ua
        cms_db().table("job_applications").insert(row).execute()
        return True

    # ── Settings + sitemap ──────────────────────────────────────────
    async def get_setting(self, key: str) -> Optional[dict[str, Any]]:
        res = cms_db().table("site_settings").select("*").eq("key", key).maybe_single().execute()
        return res.data if res else None

    async def sitemap_urls(self) -> dict[str, list[dict[str, Any]]]:
        c = cms_db()
        pages = c.table("pages").select("slug,updated_at").eq("status", "published").execute()
        posts = (
            c.table("blog_posts").select("slug,updated_at,content_type")
            .eq("status", "published").execute()
        )
        jobs = c.table("jobs").select("slug,updated_at").eq("status", "published").execute()
        return {
            "pages": pages.data or [],
            "posts": posts.data or [],
            "jobs": jobs.data or [],
        }

    # ── Delete (admin) ──────────────────────────────────────────────
    async def delete_row(self, table: str, row_id: str) -> None:
        cms_db().table(table).delete().eq("id", row_id).execute()
