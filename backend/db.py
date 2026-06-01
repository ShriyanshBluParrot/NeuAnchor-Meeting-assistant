"""Meeting state + artifacts, all in one MongoDB document.

Schema (one document per meeting):

    {
      id:             <session-id uuid string>,
      patient_email:  "alice@example.com"  (links to patients collection),
      mode:           "offline" | "online",
      status:         "processing" | "ready" | "error",
      title:          str | None,
      audio_file_id:  ObjectId | None,    # GridFS reference
      transcript:     { text, utterances, speakers } | None,
      summary:        str | None,
      notes:          { action_items, decisions, questions } | None,
      error_msg:      str | None,
      created_at:     datetime,
      updated_at:     datetime,
    }
"""
import datetime as dt

from core.mongo_client import ensure_indexes, meetings


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


async def init_db() -> None:
    """Create indexes once at startup."""
    await ensure_indexes()


async def create_meeting(session_id: str, mode: str, status: str, **fields) -> None:
    doc = {
        "id": session_id,
        "patient_email": None,
        "mode": mode,
        "status": status,
        "title": None,
        "audio_file_id": None,
        "transcript": None,
        "summary": None,
        "notes": None,
        "error_msg": None,
        "created_at": _now(),
        "updated_at": _now(),
        **fields,
    }
    await meetings().insert_one(doc)


async def update_meeting(session_id: str, **fields) -> None:
    fields["updated_at"] = _now()
    await meetings().update_one({"id": session_id}, {"$set": fields})


async def get_meeting(session_id: str) -> dict | None:
    return await meetings().find_one({"id": session_id})


async def list_meetings() -> list[dict]:
    cursor = meetings().find().sort("created_at", -1)
    return [doc async for doc in cursor]


async def list_meetings_for_patient(email: str) -> list[dict]:
    cursor = meetings().find({"patient_email": email}).sort("created_at", -1)
    return [doc async for doc in cursor]
