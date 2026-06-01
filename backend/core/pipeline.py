"""End-to-end processing pipeline (MongoDB version).

Runs after the audio file is in GridFS. Transcribes, summarises, extracts
notes, and writes every artifact back into the meeting document.
"""
import asyncio
import logging
import os
import tempfile

from core import storage, summarizer, transcriber
from db import get_meeting, update_meeting

logger = logging.getLogger("pipeline")


async def run_pipeline(session_id: str) -> None:
    audio_path = os.path.join(tempfile.gettempdir(), f"{session_id}_audio")
    try:
        # Clear any error from a previous attempt (e.g. retry after a 503).
        await update_meeting(session_id, status="processing", error_msg=None)
        meeting = await get_meeting(session_id)
        if not meeting or not meeting.get("audio_file_id"):
            raise RuntimeError("meeting has no audio file")

        # Pull the audio out of GridFS into a local temp file so AssemblyAI's
        # uploader can stream it.
        await storage.download_audio_to_file(meeting["audio_file_id"], audio_path)

        transcript = await transcriber.transcribe(audio_path)
        await update_meeting(session_id, transcript=transcript)

        flat = transcriber.diarized_text(transcript)
        title, summary, notes = await asyncio.gather(
            summarizer.generate_title(flat),
            summarizer.generate_summary(flat),
            summarizer.generate_notes(flat),
        )

        await update_meeting(
            session_id,
            title=title,
            summary=summary,
            notes=notes,
            status="ready",
        )
        logger.info("Pipeline complete for %s", session_id)
    except Exception as exc:
        logger.exception("Pipeline failed for %s", session_id)
        await update_meeting(session_id, status="error", error_msg=str(exc))
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)
