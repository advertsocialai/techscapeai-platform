"""Wiki / RAG endpoints — destination, package, policy, SOP, objection knowledge."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.schemas.travel import WikiEntryIn, WikiEntryOut, WikiSearchIn
from app.services.travel import WikiService
from app.routers.techscape._deps import require_business

router = APIRouter()


@router.get("", response_model=list[WikiEntryOut])
def list_wiki(
    category: str | None = Query(default=None),
    limit:    int        = Query(default=100, ge=1, le=500),
    biz: dict = Depends(require_business),
):
    return WikiService().list(UUID(biz["id"]), category=category, limit=limit)


@router.post("", response_model=WikiEntryOut, status_code=status.HTTP_201_CREATED)
def create_wiki(payload: WikiEntryIn, biz: dict = Depends(require_business)):
    return WikiService().create(UUID(biz["id"]), payload.model_dump())


@router.post("/bulk", status_code=status.HTTP_201_CREATED)
def bulk_create_wiki(entries: list[WikiEntryIn], biz: dict = Depends(require_business)):
    n = WikiService().bulk_create(UUID(biz["id"]), [e.model_dump() for e in entries])
    return {"created": n}


@router.post("/search", response_model=list[WikiEntryOut])
def search_wiki(payload: WikiSearchIn, biz: dict = Depends(require_business)):
    return WikiService().search(
        UUID(biz["id"]),
        query=payload.query, category=payload.category, limit=payload.limit,
    )


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_wiki(entry_id: UUID, biz: dict = Depends(require_business)):
    ok = WikiService().delete(entry_id, UUID(biz["id"]))
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Wiki entry not found")
    return None
