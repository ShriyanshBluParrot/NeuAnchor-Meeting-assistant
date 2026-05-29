"""Meeting summarisation and structured note extraction with Gemini 2.5 Pro."""
import json

from google.genai import types

from config import get_settings
from core.gemini_client import get_client

_TITLE_PROMPT = (
    "Generate a short, professional meeting title (max 8 words) for the transcript "
    "below. Return only the title, nothing else.\n\nTRANSCRIPT:\n{text}"
)

_SUMMARY_PROMPT = (
    "You are an expert meeting summariser. Read the speaker-labelled transcript and "
    "write a concise, professional summary in bullet points. Capture the main topics, "
    "outcomes, and overall purpose.\n\nTRANSCRIPT:\n{text}"
)

_NOTES_PROMPT = (
    "From the meeting transcript below, extract structured notes. Return ONLY JSON "
    "matching this shape:\n"
    '{{"action_items": [{{"task": str, "owner": str, "deadline": str}}], '
    '"decisions": [str], "questions": [str]}}\n'
    "Use an empty string when an owner or deadline is unknown. Return an empty list "
    "for a category with no items.\n\nTRANSCRIPT:\n{text}"
)


async def _generate(prompt: str, *, temperature: float, as_json: bool = False) -> str:
    settings = get_settings()
    config = types.GenerateContentConfig(temperature=temperature)
    if as_json:
        config.response_mime_type = "application/json"

    resp = await get_client().aio.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
        config=config,
    )
    return resp.text or ""


async def generate_title(text: str) -> str:
    out = await _generate(_TITLE_PROMPT.format(text=text[:4000]), temperature=0.3)
    return out.strip().strip('"')


async def generate_summary(text: str) -> str:
    return await _generate(_SUMMARY_PROMPT.format(text=text), temperature=0.3)


async def generate_notes(text: str) -> dict:
    raw = await _generate(_NOTES_PROMPT.format(text=text), temperature=0.2, as_json=True)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {}
    return {
        "action_items": data.get("action_items", []),
        "decisions": data.get("decisions", []),
        "questions": data.get("questions", []),
    }
