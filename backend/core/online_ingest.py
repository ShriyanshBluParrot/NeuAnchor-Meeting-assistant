"""Ingest a completed Recall.ai recording into the processing pipeline.

Two entry points share the same download-and-process logic:
  - `ingest_and_process` — used by the webhook (push) path
  - `poll_and_process`   — used by the no-webhook (poll) path, which avoids
    needing a public URL / ngrok by checking the bot status on a timer
"""
import asyncio
import logging

import httpx

from core import gcs_client, recall_client
from core.pipeline import run_pipeline
from db import get_meeting_by_bot, update_meeting

logger = logging.getLogger("online_ingest")

# Terminal Recall.ai bot states.
_DONE_STATES = {"done", "analysis_done", "media_expired"}
_FATAL_STATES = {"fatal", "error"}


def _status_code(bot: dict) -> str:
    status = bot.get("status_changes") or []
    if status:
        return (status[-1].get("code") or "").lower()
    # newer API shape
    return (bot.get("status") or {}).get("code", "").lower()


def _fatal_detail(bot: dict) -> str:
    """Human-readable reason for a fatal bot, from its last status change."""
    status = bot.get("status_changes") or []
    if status:
        last = status[-1]
        sub = last.get("sub_code") or ""
        msg = last.get("message") or ""
        detail = " - ".join(p for p in (sub, msg) if p)
        return detail or "fatal"
    return "fatal"


async def ingest_and_process(bot_id: str) -> None:
    meeting = await get_meeting_by_bot(bot_id)
    if not meeting:
        logger.warning("Ingest for unknown bot %s", bot_id)
        return
    session_id = meeting["id"]
    try:
        bot = await recall_client.get_bot(bot_id)
        audio_url = recall_client.extract_audio_url(bot)
        if not audio_url:
            raise RuntimeError("No audio URL in completed bot")

        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.get(audio_url)
            resp.raise_for_status()
            audio_bytes = resp.content

        await gcs_client.upload_bytes(session_id, "audio.wav", audio_bytes, "audio/wav")
        await run_pipeline(session_id)
    except Exception as exc:
        logger.exception("Failed ingesting bot %s", bot_id)
        await update_meeting(session_id, status="error", error_msg=str(exc))


async def poll_and_process(
    bot_id: str, interval: int = 20, timeout: int = 4 * 60 * 60
) -> None:
    """Poll the bot until its recording is ready, then process it.

    Lets the online flow work without a public webhook URL. `timeout` caps the
    wait at 4 hours so a stuck bot doesn't poll forever.
    """
    meeting = await get_meeting_by_bot(bot_id)
    if not meeting:
        return
    session_id = meeting["id"]
    waited = 0
    while waited < timeout:
        try:
            bot = await recall_client.get_bot(bot_id)
            code = _status_code(bot)
            if code in _DONE_STATES or recall_client.extract_audio_url(bot):
                await ingest_and_process(bot_id)
                return
            if code in _FATAL_STATES:
                await update_meeting(
                    session_id,
                    status="error",
                    error_msg=f"Recall.ai bot fatal: {_fatal_detail(bot)}",
                )
                return
        except Exception:
            logger.exception("Poll error for bot %s", bot_id)
        await asyncio.sleep(interval)
        waited += interval

    await update_meeting(
        session_id, status="error", error_msg="Timed out waiting for recording"
    )
