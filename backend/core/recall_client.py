"""Recall.ai meeting bot integration.

Sends a bot into a Google Meet to record it. The bot waits in the lobby until
the host admits it, records the meeting, and Recall.ai fires webhooks as the
bot's status changes. When recording is complete we fetch the bot to obtain the
downloadable audio/video URL.

API reference: https://docs.recall.ai
"""
import httpx

from config import get_settings


def _base_url() -> str:
    return f"https://{get_settings().recall_region}.recall.ai/api/v1"


def _headers() -> dict:
    return {
        "Authorization": f"Token {get_settings().recall_api_key}",
        "Content-Type": "application/json",
    }


async def create_bot(meet_url: str, bot_name: str = "Meeting Assistant") -> dict:
    """Dispatch a bot to the meeting. Returns the created bot object (incl. id)."""
    settings = get_settings()
    payload = {
        "meeting_url": meet_url,
        "bot_name": bot_name,
        # Ask Recall to produce a downloadable recording once the call ends.
        "recording_config": {
            "audio_mixed_raw": {},
        },
    }
    # Sign the bot in (required for sign-in-only Google Meet calls).
    if settings.recall_google_login_group_id:
        payload["google_meet"] = {
            "google_login_group_id": settings.recall_google_login_group_id,
            "login_required": True,
        }
    if settings.webhook_base_url:
        payload["webhooks"] = [
            {
                "events": ["bot.done", "bot.fatal"],
                "url": f"{settings.webhook_base_url.rstrip('/')}/webhook/recall",
            }
        ]

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{_base_url()}/bot/", json=payload, headers=_headers()
        )
        resp.raise_for_status()
        return resp.json()


async def get_bot(bot_id: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{_base_url()}/bot/{bot_id}/", headers=_headers())
        resp.raise_for_status()
        return resp.json()


def extract_audio_url(bot_data: dict) -> str | None:
    """Pull the downloadable mixed-audio URL from a completed bot object."""
    recordings = bot_data.get("recordings") or []
    for rec in recordings:
        media = rec.get("media_shortcuts") or {}
        mixed = media.get("audio_mixed") or {}
        data = mixed.get("data") or {}
        url = data.get("download_url")
        if url:
            return url
    return None
