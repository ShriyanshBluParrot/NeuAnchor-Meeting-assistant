"""Meeting chat (non-RAG, transcript-in-context).

Reads the transcript from the meeting's MongoDB document and asks Gemini to
answer using only that context. Streams tokens back to the API layer.
"""
from collections.abc import AsyncGenerator

from core import gemini_client
from db import get_meeting


async def _transcript_text(session_id: str) -> str:
    meeting = await get_meeting(session_id)
    if not meeting:
        return ""
    transcript = meeting.get("transcript") or {}
    utterances = transcript.get("utterances") or []
    if utterances:
        return "\n".join(f"{u['speaker']}: {u['text']}" for u in utterances)
    return transcript.get("text", "")


async def answer_stream(session_id: str, question: str) -> AsyncGenerator[str, None]:
    transcript = await _transcript_text(session_id)
    prompt = (
        "You are a helpful assistant answering questions about a meeting. Use ONLY "
        "the transcript below. If the answer is not in it, say you don't know.\n\n"
        f"TRANSCRIPT:\n{transcript}\n\nQUESTION: {question}\n\nANSWER:"
    )
    async for token in gemini_client.stream(prompt, temperature=0.3):
        yield token
