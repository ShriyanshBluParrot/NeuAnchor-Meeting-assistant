import logging

from fastapi import APIRouter, BackgroundTasks, Request

from core.online_ingest import ingest_and_process
from db import get_meeting_by_bot, update_meeting

router = APIRouter(tags=["webhook"])
logger = logging.getLogger("webhook")


@router.post("/webhook/recall")
async def recall_webhook(request: Request, background: BackgroundTasks):
    """Optional push path. The online flow also polls, so a webhook isn't
    required — but if WEBHOOK_BASE_URL is configured this triggers processing
    immediately instead of waiting for the next poll."""
    payload = await request.json()
    event = payload.get("event", "")
    bot_id = (payload.get("data") or {}).get("bot_id") or payload.get("bot_id")

    if not bot_id:
        return {"ok": True}

    if event in ("bot.done", "done"):
        background.add_task(ingest_and_process, bot_id)
    elif event in ("bot.fatal", "fatal"):
        meeting = await get_meeting_by_bot(bot_id)
        if meeting:
            await update_meeting(
                meeting["id"], status="error", error_msg="Recall.ai bot fatal error"
            )

    return {"ok": True}
