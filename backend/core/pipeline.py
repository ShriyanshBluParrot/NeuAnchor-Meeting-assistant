"""End-to-end processing pipeline.

Runs after `audio.wav` is in GCS (from either the online or offline path).
Transcribes, summarises, extracts notes, and indexes the transcript for RAG,
writing every artifact back to GCS and tracking status in SQLite.
"""
import asyncio
import logging
import os
import tempfile

from core import gcs_client, summarizer, transcriber
from db import update_meeting

logger = logging.getLogger("pipeline")


async def run_pipeline(session_id: str) -> None:
    audio_path = os.path.join(tempfile.gettempdir(), f"{session_id}_audio")
    try:
        await update_meeting(session_id, status="processing")

        # Download the audio locally and let AssemblyAI upload it directly.
        # Avoids GCS signed URLs, which require a private key (ADC has none).
        await gcs_client.download_to_file(session_id, "audio.wav", audio_path)
        transcript = await transcriber.transcribe(audio_path)
        await gcs_client.upload_json(session_id, "transcript.json", transcript)

        flat = transcriber.diarized_text(transcript)

        title, summary, notes = await asyncio.gather(
            summarizer.generate_title(flat),
            summarizer.generate_summary(flat),
            summarizer.generate_notes(flat),
        )

        await asyncio.gather(
            gcs_client.upload_text(session_id, "summary.txt", summary),
            gcs_client.upload_json(session_id, "notes.json", notes),
        )

        await update_meeting(session_id, status="ready", title=title)
        logger.info("Pipeline complete for %s", session_id)
    except Exception as exc:  # surface failure to the UI rather than dying silently
        logger.exception("Pipeline failed for %s", session_id)
        await update_meeting(session_id, status="error", error_msg=str(exc))
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)
