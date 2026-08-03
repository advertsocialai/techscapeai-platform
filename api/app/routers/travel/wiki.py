"""Wiki / RAG endpoints — destination, package, policy, SOP, objection knowledge."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.schemas.travel import WikiEntryIn, WikiEntryOut, WikiSearchIn
from app.services.travel import WikiService
from app.core.deps import require_role

router = APIRouter()

# Read = any authenticated user (viewer+). Write = manager+ (== product
# spec's "admin+" — see app/core/deps.py role-mapping note).
_read  = require_role("viewer")
_write = require_role("manager")


@router.get("", response_model=list[WikiEntryOut])
def list_wiki(
    category: str | None = Query(default=None),
    limit:    int        = Query(default=100, ge=1, le=500),
    user: dict = Depends(_read),
):
    return WikiService().list(UUID(user["business_id"]), category=category, limit=limit)


@router.post("", response_model=WikiEntryOut, status_code=status.HTTP_201_CREATED)
def create_wiki(payload: WikiEntryIn, user: dict = Depends(_write)):
    return WikiService().create(UUID(user["business_id"]), payload.model_dump())


@router.post("/bulk", status_code=status.HTTP_201_CREATED)
def bulk_create_wiki(entries: list[WikiEntryIn], user: dict = Depends(_write)):
    n = WikiService().bulk_create(UUID(user["business_id"]), [e.model_dump() for e in entries])
    return {"created": n}


@router.post("/search", response_model=list[WikiEntryOut])
def search_wiki(payload: WikiSearchIn, user: dict = Depends(_read)):
    return WikiService().search(
        UUID(user["business_id"]),
        query=payload.query, category=payload.category, limit=payload.limit,
    )


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_wiki(entry_id: UUID, user: dict = Depends(_write)):
    ok = WikiService().delete(entry_id, UUID(user["business_id"]))
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Wiki entry not found")
    return None
