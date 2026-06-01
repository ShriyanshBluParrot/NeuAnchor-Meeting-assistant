"""Patient read + edit endpoints."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core import patients
from db import list_meetings_for_patient

router = APIRouter(prefix="/patients", tags=["patients"])


class NameUpdate(BaseModel):
    name: str


def _to_jsonable_patient(p: dict | None) -> dict | None:
    if not p:
        return p
    return {k: v for k, v in p.items() if k != "_id"}


def _to_jsonable_meeting(m: dict) -> dict:
    return {k: v for k, v in m.items() if k != "_id" and k != "audio_file_id"} | (
        {"audio_file_id": str(m["audio_file_id"])} if m.get("audio_file_id") else {}
    )


@router.get("")
async def list_patients(limit: int = 25, offset: int = 0, search: str | None = None):
    """Paginated patient list. Each row includes meeting_count and last_meeting_at.

    Query params:
      limit  — page size (1-100, default 25)
      offset — skip N
      search — case-insensitive substring match on email or name
    """
    from core.mongo_client import meetings as meetings_col

    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    q: dict = {}
    if search:
        rx = {"$regex": search.strip(), "$options": "i"}
        q["$or"] = [{"email": rx}, {"name": rx}]

    coll = patients.collection()
    total = await coll.count_documents(q)
    cursor = coll.find(q).sort("updated_at", -1).skip(offset).limit(limit)

    items = []
    async for p in cursor:
        # Aggregate meeting_count + last_meeting_at via the existing index.
        count = await meetings_col().count_documents({"patient_email": p["email"]})
        last = (
            await meetings_col()
            .find({"patient_email": p["email"]})
            .sort("created_at", -1)
            .limit(1)
            .to_list(1)
        )
        items.append(
            _to_jsonable_patient(p)
            | {
                "meeting_count": count,
                "last_meeting_at": last[0]["created_at"] if last else None,
            }
        )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/{email}")
async def get_patient(email: str):
    """Patient record + chronological list of their meetings (newest first)."""
    try:
        normalised = patients.normalise_email(email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    patient = await patients.get(normalised)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    meetings = await list_meetings_for_patient(normalised)
    return {
        "patient": _to_jsonable_patient(patient),
        "meetings": [
            {
                "id": m["id"],
                "title": m.get("title"),
                "status": m["status"],
                "created_at": m["created_at"],
                "summary": m.get("summary"),
            }
            for m in meetings
        ],
    }


@router.patch("/{email}")
async def update_patient_name(email: str, body: NameUpdate):
    """Set or update the display name for a patient."""
    try:
        normalised = patients.normalise_email(email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    patient = await patients.get(normalised)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    updated = await patients.upsert(normalised, name=body.name)
    return _to_jsonable_patient(updated)
