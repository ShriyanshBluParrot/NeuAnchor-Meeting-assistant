"""Meeting summarisation and structured note extraction with Gemini 2.5 Pro."""
import json

from core import gemini_client

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
    "From the transcript below, extract structured notes. Return ONLY JSON "
    "matching this shape:\n"
    '{{"action_items": [{{"task": str, "owner": str, "deadline": str}}], '
    '"decisions": [str], "questions": [str]}}\n\n'
    "Definitions (be generous — populate every category whenever possible):\n"
    " - action_items: explicit tasks, follow-ups, or concrete next steps that anyone "
    "needs to do. If the transcript is informational/educational, include "
    "recommended actions or things the listener is encouraged to try.\n"
    " - decisions: explicit decisions made, OR key takeaways / conclusions / "
    "important facts asserted by the speakers. For educational content, include "
    "the main concepts being defined.\n"
    " - questions: open questions raised, OR questions the content explicitly "
    "answers. For tutorials, list the implicit questions the content addresses "
    '(e.g. "What is X?", "How does Y work?").\n\n'
    "Use an empty string when an owner or deadline is unknown. Return empty "
    "lists ONLY if the transcript is truly empty or unintelligible. Aim for "
    "at least 1-3 entries per category for any meaningful transcript.\n\n"
    "TRANSCRIPT:\n{text}"
)


async def generate_title(text: str) -> str:
    out = await gemini_client.generate(
        _TITLE_PROMPT.format(text=text[:4000]), temperature=0.3
    )
    return out.strip().strip('"')


async def generate_summary(text: str) -> str:
    return await gemini_client.generate(
        _SUMMARY_PROMPT.format(text=text), temperature=0.3
    )


async def generate_notes(text: str) -> dict:
    raw = await gemini_client.generate(
        _NOTES_PROMPT.format(text=text), temperature=0.2, json_mode=True
    )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {}
    return {
        "action_items": data.get("action_items", []),
        "decisions": data.get("decisions", []),
        "questions": data.get("questions", []),
    }
