"""Meeting chat (non-RAG, transcript-in-context).

RAG with a vector store is deferred. For now the chat feeds the full transcript
to Gemini as context — meeting transcripts comfortably fit in the model's
context window. The `answer_stream` signature is kept stable so a future vector
retrieval step can slot in without touching the API layer.
"""
from collections.abc import AsyncGenerator

from google.genai import types

from config import get_settings
from core import gcs_client
from core.gemini_client import get_client


async def _transcript_text(session_id: str) -> str:
    data = await gcs_client.download_json(session_id, "transcript.json")
    utterances = data.get("utterances") or []
    if utterances:
        return "\n".join(f"{u['speaker']}: {u['text']}" for u in utterances)
    return data.get("text", "")


async def answer_stream(session_id: str, question: str) -> AsyncGenerator[str, None]:
    transcript = await _transcript_text(session_id)
    prompt = (
        "You are a helpful assistant answering questions about a meeting. Use ONLY "
        "the transcript below. If the answer is not in it, say you don't know.\n\n"
        f"TRANSCRIPT:\n{transcript}\n\nQUESTION: {question}\n\nANSWER:"
    )
    settings = get_settings()

    stream = await get_client().aio.models.generate_content_stream(
        model=settings.gemini_model,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.3),
    )
    async for chunk in stream:
        if chunk.text:
            yield chunk.text
