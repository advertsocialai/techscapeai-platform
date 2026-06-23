"""Business contacts — CRUD + bulk CSV import."""
import csv
import io
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.schemas.techscape import ContactIn, ContactOut
from app.services.techscape import ContactService

from ._deps import require_business

router = APIRouter()


@router.get("", response_model=list[ContactOut])
def list_contacts(biz: dict = Depends(require_business),
                  search: str | None = None, limit: int = 200):
    return ContactService().list(UUID(biz["id"]), search=search, limit=limit)


@router.post("", response_model=ContactOut, status_code=status.HTTP_201_CREATED)
def upsert_contact(payload: ContactIn, biz: dict = Depends(require_business)):
    return ContactService().upsert(UUID(biz["id"]), payload.model_dump(exclude_none=True))


@router.get("/{contact_id}", response_model=ContactOut)
def get_contact(contact_id: UUID, biz: dict = Depends(require_business)):
    row = ContactService().get(contact_id, UUID(biz["id"]))
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return row


@router.put("/{contact_id}", response_model=ContactOut)
def update_contact(contact_id: UUID, payload: ContactIn,
                   biz: dict = Depends(require_business)):
    row = ContactService().update(contact_id, UUID(biz["id"]),
                                   payload.model_dump(exclude_none=True))
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return row


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contact(contact_id: UUID, biz: dict = Depends(require_business)):
    if not ContactService().delete(contact_id, UUID(biz["id"])):
        raise HTTPException(status.HTTP_404_NOT_FOUND)


@router.post("/import")
async def import_contacts_csv(
    file: UploadFile = File(...),
    biz: dict = Depends(require_business),
):
    """
    Bulk import contacts from a CSV upload. Supported columns (any order):
      name, email, phone, preferred_channel, tags

    `tags` may be a comma- or pipe-separated string (or omitted).
    Lines without an email AND without a phone are skipped.
    """
    if file.content_type and "csv" not in file.content_type:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            "expected text/csv upload")

    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(raw))
    if not reader.fieldnames:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "empty CSV")

    fields = {f.lower().strip() for f in reader.fieldnames}
    if not ({"email", "phone"} & fields):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "CSV must include at least an email or phone column")

    svc = ContactService()
    imported, skipped = 0, 0
    business_id = UUID(biz["id"])
    for row in reader:
        clean = {k.lower().strip(): (v.strip() if isinstance(v, str) else v)
                 for k, v in row.items()}
        email = clean.get("email") or None
        phone = clean.get("phone") or None
        if not email and not phone:
            skipped += 1
            continue
        tags_raw = clean.get("tags") or ""
        tags = [t for t in (tags_raw.replace("|", ",").split(",")) if t.strip()]
        payload = {
            "email":             email,
            "phone":             phone,
            "name":              clean.get("name") or None,
            "preferred_channel": clean.get("preferred_channel") or None,
            "tags":              tags,
            "metadata":          {},
        }
        try:
            svc.upsert(business_id, payload)
            imported += 1
        except Exception:
            skipped += 1
    return {"imported": imported, "skipped": skipped}
