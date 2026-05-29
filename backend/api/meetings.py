import asyncio
import uuid

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from pydantic import BaseModel

from core import gcs_client, recall_client, recorder
from core.online_ingest import poll_and_process
from core.pipeline import run_pipeline
from db import create_meeting, get_meeting, list_meetings, update_meeting

router = APIRouter(prefix="/meetings", tags=["meetings"])


class OnlineRequest(BaseModel):
    meet_url: str


class StartResponse(BaseModel):
    session_id: str


class StopRequest(BaseModel):
    session_id: str


@router.post("/online", response_model=StartResponse)
async def start_online(req: OnlineRequest, background: BackgroundTasks):
    session_id = str(uuid.uuid4())
    try:
        bot = await recall_client.create_bot(req.meet_url)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Recall.ai error: {exc}") from exc

    bot_id = bot.get("id")
    await create_meeting(
        session_id,
        mode="online",
        status="recording",
        meet_url=req.meet_url,
        recall_bot_id=bot_id,
        gcs_prefix=gcs_client.prefix_for(session_id),
    )

    # Poll the bot until its recording is ready — no public webhook required.
    background.add_task(poll_and_process, bot_id)
    return StartResponse(session_id=session_id)


@router.post("/offline/start", response_model=StartResponse)
async def start_offline():
    session_id = str(uuid.uuid4())
    try:
        await asyncio.to_thread(recorder.start_recording, session_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Recorder error: {exc}") from exc

    await create_meeting(
        session_id,
        mode="offline",
        status="recording",
        gcs_prefix=gcs_client.prefix_for(session_id),
    )
    return StartResponse(session_id=session_id)


@router.post("/offline/stop")
async def stop_offline(req: StopRequest, background: BackgroundTasks):
    meeting = await get_meeting(req.session_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Unknown session")
    if not recorder.is_recording(req.session_id):
        raise HTTPException(status_code=409, detail="No active recording")

    wav_path = await asyncio.to_thread(recorder.stop_recording, req.session_id)
    await gcs_client.upload_file(req.session_id, "audio.wav", wav_path)
    await update_meeting(req.session_id, status="processing")

    background.add_task(run_pipeline, req.session_id)
    return {"session_id": req.session_id, "status": "processing"}


@router.post("/upload", response_model=StartResponse)
async def upload_recording(
    background: BackgroundTasks, file: UploadFile = File(...)
):
    """Accept an audio recording (from the browser mic or a pre-recorded file),
    store it in GCS, and run the processing pipeline. Works regardless of where
    the backend runs — the audio is captured client-side.

    The upload is streamed to a local temp file in 1 MB chunks so a multi-hour
    meeting doesn't have to fit in RAM, then handed to the chunked resumable
    GCS uploader.
    """
    import os
    import tempfile

    session_id = str(uuid.uuid4())
    tmp_path = os.path.join(tempfile.gettempdir(), f"{session_id}_upload")

    try:
        with open(tmp_path, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                out.write(chunk)

        await create_meeting(
            session_id,
            mode="offline",
            status="processing",
            gcs_prefix=gcs_client.prefix_for(session_id),
        )
        await gcs_client.upload_file(session_id, "audio.wav", tmp_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    background.add_task(run_pipeline, session_id)
    return StartResponse(session_id=session_id)


@router.get("/{session_id}/status")
async def meeting_status(session_id: str):
    meeting = await get_meeting(session_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Unknown session")
    return {"status": meeting["status"], "error_msg": meeting["error_msg"]}


@router.get("/{session_id}")
async def meeting_detail(session_id: str):
    meeting = await get_meeting(session_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Unknown session")
    if meeting["status"] != "ready":
        return {"meeting": meeting, "transcript": None, "summary": None, "notes": None}

    transcript = await gcs_client.download_json(session_id, "transcript.json")
    summary = await gcs_client.download_text(session_id, "summary.txt")
    notes = await gcs_client.download_json(session_id, "notes.json")
    return {
        "meeting": meeting,
        "transcript": transcript,
        "summary": summary,
        "notes": notes,
    }


@router.get("")
async def all_meetings():
    return await list_meetings()
