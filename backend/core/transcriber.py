"""Speech-to-text via AssemblyAI with speaker diarization.

Uses AssemblyAI's REST API directly (instead of the Python SDK) so we control
the exact request body — the SDK's bundled `speech_model` enum lags behind the
API, which now requires models like `universal-2`. Speaker labels let us tell
participants apart for both in-person and remote meetings.
"""
import asyncio

import httpx

from config import get_settings

_BASE = "https://api.assemblyai.com/v2"
_POLL_INTERVAL = 5
_POLL_TIMEOUT = 4 * 60 * 60  # 4 hours — long meetings can take a while
_UPLOAD_CHUNK = 5 * 1024 * 1024  # 5 MB streaming chunks


def _headers() -> dict:
    return {"authorization": get_settings().assemblyai_api_key}


async def _file_chunks(path: str):
    """Async generator yielding the file's bytes in chunks, so a multi-hour
    recording doesn't have to fit in memory during the AssemblyAI upload."""
    f = await asyncio.to_thread(open, path, "rb")
    try:
        while True:
            chunk = await asyncio.to_thread(f.read, _UPLOAD_CHUNK)
            if not chunk:
                return
            yield chunk
    finally:
        await asyncio.to_thread(f.close)


async def _upload(client: httpx.AsyncClient, audio_path: str) -> str:
    resp = await client.post(
        f"{_BASE}/upload", headers=_headers(), content=_file_chunks(audio_path)
    )
    resp.raise_for_status()
    return resp.json()["upload_url"]


async def transcribe(audio_path: str) -> dict:
    """Transcribe a local audio file. Returns a structured transcript dict."""
    settings = get_settings()

    # Generous per-request timeout — the upload step alone can take many
    # minutes on a slow link with a multi-hour recording.
    async with httpx.AsyncClient(timeout=3600) as client:
        audio_url = await _upload(client, audio_path)

        create = await client.post(
            f"{_BASE}/transcript",
            headers=_headers(),
            json={
                "audio_url": audio_url,
                "speaker_labels": True,
                # API requires `speech_models` as a non-empty list (speech_model
                # singular is deprecated). Valid: universal-3-pro, universal-2.
                "speech_models": [
                    m.strip()
                    for m in settings.assemblyai_speech_model.split(",")
                    if m.strip()
                ],
            },
        )
        if create.status_code >= 400:
            raise RuntimeError(f"AssemblyAI {create.status_code}: {create.text}")
        transcript_id = create.json()["id"]

        waited = 0
        while waited < _POLL_TIMEOUT:
            poll = await client.get(
                f"{_BASE}/transcript/{transcript_id}", headers=_headers()
            )
            poll.raise_for_status()
            data = poll.json()
            status = data.get("status")
            if status == "completed":
                break
            if status == "error":
                raise RuntimeError(f"AssemblyAI failed: {data.get('error')}")
            await asyncio.sleep(_POLL_INTERVAL)
            waited += _POLL_INTERVAL
        else:
            raise RuntimeError("AssemblyAI transcription timed out")

    utterances = [
        {
            "speaker": f"Speaker {u['speaker']}",
            "text": u["text"],
            "start_ms": u.get("start"),
            "end_ms": u.get("end"),
        }
        for u in (data.get("utterances") or [])
    ]
    return {
        "text": data.get("text") or "",
        "utterances": utterances,
        "speakers": sorted({u["speaker"] for u in utterances}),
    }


def diarized_text(transcript: dict) -> str:
    """Render utterances as `Speaker A: ...` lines for LLM consumption."""
    lines = [f"{u['speaker']}: {u['text']}" for u in transcript.get("utterances", [])]
    return "\n".join(lines) if lines else transcript.get("text", "")
