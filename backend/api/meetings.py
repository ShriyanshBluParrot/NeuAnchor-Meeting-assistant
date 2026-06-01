import os
import tempfile
import uuid

from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core import patients, storage
from core.pipeline import run_pipeline
from db import create_meeting, get_meeting, list_meetings, update_meeting

router = APIRouter(prefix="/meetings", tags=["meetings"])


class StartResponse(BaseModel):
    session_id: str


def _to_jsonable(meeting: dict | None) -> dict | None:
    """ObjectIds / datetimes don't serialise — flatten them for JSON output."""
    if not meeting:
        return meeting
    out = {k: v for k, v in meeting.items() if k != "_id"}
    if isinstance(out.get("audio_file_id"), ObjectId):
        out["audio_file_id"] = str(out["audio_file_id"])
    return out


# ─── Upload (used by the Chrome extension for tab, mic, and file modes) ──────
@router.post("/upload", response_model=StartResponse)
async def upload_recording(
    background: BackgroundTasks,
    email: str = Form(...),
    file: UploadFile = File(...),
):
    """Accept an audio file plus a patient email, persist it to GridFS, link
    it to the patient (creating the patient on first sight), and kick off the
    processing pipeline.

    The upload is streamed to a local temp file in 1 MB chunks so a multi-hour
    meeting doesn't have to fit in RAM, then streamed from disk into GridFS.
    """
    try:
        normalised_email = patients.normalise_email(email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Create the patient record if this email is new; touch updated_at otherwise.
    await patients.upsert(normalised_email)

    session_id = str(uuid.uuid4())
    tmp_path = os.path.join(tempfile.gettempdir(), f"{session_id}_upload")
    content_type = file.content_type or "audio/webm"

    try:
        with open(tmp_path, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                out.write(chunk)

        await create_meeting(
            session_id,
            mode="offline",
            status="processing",
            patient_email=normalised_email,
        )
        audio_id = await storage.upload_audio(session_id, tmp_path, content_type)
        await update_meeting(session_id, audio_file_id=audio_id)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    background.add_task(run_pipeline, session_id)
    return StartResponse(session_id=session_id)


# ─── Read endpoints ───────────────────────────────────────────────────────────
@router.get("/{session_id}/status")
async def meeting_status(session_id: str):
    meeting = await get_meeting(session_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Unknown session")
    return {"status": meeting["status"], "error_msg": meeting.get("error_msg")}


@router.get("/{session_id}")
async def meeting_detail(session_id: str):
    """Full meeting payload: transcript + summary + notes + audio URL."""
    meeting = await get_meeting(session_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Unknown session")
    meeting_json = _to_jsonable(meeting)
    return {
        "meeting": meeting_json,
        "transcript": meeting.get("transcript"),
        "summary": meeting.get("summary"),
        "notes": meeting.get("notes"),
        # Convenience: frontend can drop this straight into <audio src=...>.
        "audio_url": (
            f"/meetings/{session_id}/audio" if meeting.get("audio_file_id") else None
        ),
    }


@router.get("/{session_id}/transcript")
async def meeting_transcript(session_id: str):
    """Just the speaker-labelled transcript object.

    Returns
    -------
        { "text": "...", "speakers": [...], "utterances": [{speaker, text, start_ms, end_ms}] }
    """
    meeting = await get_meeting(session_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Unknown session")
    transcript = meeting.get("transcript")
    if not transcript:
        raise HTTPException(
            status_code=409,
            detail=f"Transcript not available yet (status={meeting['status']})",
        )
    return transcript


@router.get("/{session_id}/summary")
async def meeting_summary(session_id: str):
    """Just the Gemini-generated summary text + the meeting title."""
    meeting = await get_meeting(session_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Unknown session")
    if not meeting.get("summary"):
        raise HTTPException(
            status_code=409,
            detail=f"Summary not available yet (status={meeting['status']})",
        )
    return {"title": meeting.get("title"), "summary": meeting["summary"]}


@router.get("/{session_id}/notes")
async def meeting_notes(session_id: str):
    """Just the structured notes (action items / decisions / open questions)."""
    meeting = await get_meeting(session_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Unknown session")
    if not meeting.get("notes"):
        raise HTTPException(
            status_code=409,
            detail=f"Notes not available yet (status={meeting['status']})",
        )
    return meeting["notes"]


@router.get("/{session_id}/audio")
async def meeting_audio(session_id: str):
    """Stream the GridFS audio binary so the UI can play / download it."""
    meeting = await get_meeting(session_id)
    if not meeting or not meeting.get("audio_file_id"):
        raise HTTPException(status_code=404, detail="No audio for this meeting")

    stream = await storage.open_audio_stream(meeting["audio_file_id"])
    content_type = (
        (stream.metadata or {}).get("content_type") if stream.metadata else None
    ) or "audio/webm"

    async def iterator():
        while True:
            chunk = await stream.readchunk()
            if not chunk:
                break
            yield chunk

    return StreamingResponse(iterator(), media_type=content_type)


@router.get("")
async def all_meetings(
    limit: int = 25,
    offset: int = 0,
    status: str | None = None,
    patient_email: str | None = None,
):
    """Paginated meeting list. Returns compact items (no transcript)."""
    from core.mongo_client import meetings as meetings_col

    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    q: dict = {}
    if status:
        q["status"] = status
    if patient_email:
        q["patient_email"] = patient_email.strip().lower()

    total = await meetings_col().count_documents(q)
    cursor = (
        meetings_col().find(q).sort("created_at", -1).skip(offset).limit(limit)
    )
    items = []
    async for m in cursor:
        items.append(
            {
                "id": m["id"],
                "patient_email": m.get("patient_email"),
                "mode": m.get("mode"),
                "status": m["status"],
                "title": m.get("title"),
                "created_at": m["created_at"],
                "updated_at": m.get("updated_at"),
                "error_msg": m.get("error_msg"),
            }
        )
    return {"items": items, "total": total, "limit": limit, "offset": offset}
