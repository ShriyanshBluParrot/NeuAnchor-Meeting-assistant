"""Admin-panel endpoints.

These are read-only aggregations + paginated listings tailored for an admin
dashboard. They never return audio binaries or the full transcript body —
they're designed to be fast and small so the frontend can render a clean
overview page.
"""
from fastapi import APIRouter

from core.mongo_client import meetings as meetings_col
from core.patients import collection as patients_col

router = APIRouter(prefix="/admin", tags=["admin"])


def _to_jsonable(doc: dict | None) -> dict | None:
    if not doc:
        return doc
    out = {k: v for k, v in doc.items() if k != "_id"}
    if out.get("audio_file_id") is not None:
        out["audio_file_id"] = str(out["audio_file_id"])
    return out


def _meeting_summary(m: dict) -> dict:
    """Compact representation of a meeting for list views (no transcript)."""
    return {
        "id": m["id"],
        "patient_email": m.get("patient_email"),
        "mode": m.get("mode"),
        "status": m["status"],
        "title": m.get("title"),
        "created_at": m["created_at"],
        "updated_at": m.get("updated_at"),
        "error_msg": m.get("error_msg"),
    }


@router.get("/dashboard")
async def dashboard():
    """One-call payload for the admin overview / home page.

    Returns
    -------
        {
          "totals": {
            "patients": int,
            "meetings": int
          },
          "meetings_by_status": { "ready": N, "processing": N, "error": N, ... },
          "recent_meetings":   list of 10 newest meetings (compact, no transcript),
          "recent_patients":   list of 5 newest patients
        }
    """
    total_patients = await patients_col().count_documents({})
    total_meetings = await meetings_col().count_documents({})

    # Group meetings by status.
    status_pipeline = [
        {"$group": {"_id": "$status", "count": {"$sum": 1}}}
    ]
    by_status: dict[str, int] = {}
    async for row in meetings_col().aggregate(status_pipeline):
        by_status[row["_id"]] = row["count"]

    # Recent meetings (compact).
    recent_meetings_cur = meetings_col().find().sort("created_at", -1).limit(10)
    recent_meetings = [_meeting_summary(m) async for m in recent_meetings_cur]

    # Recent patients.
    recent_patients_cur = patients_col().find().sort("created_at", -1).limit(5)
    recent_patients = [_to_jsonable(p) async for p in recent_patients_cur]

    return {
        "totals": {"patients": total_patients, "meetings": total_meetings},
        "meetings_by_status": by_status,
        "recent_meetings": recent_meetings,
        "recent_patients": recent_patients,
    }
