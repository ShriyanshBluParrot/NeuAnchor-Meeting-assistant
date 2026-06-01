"""Gemini REST API client (Google AI Studio API key).

We call the REST API directly with httpx instead of the google-genai SDK —
the SDK has session-lifecycle bugs that surface inconsistently in async/
threaded contexts. The REST surface is small and stable.

Adds two pieces of resilience around Google's intermittent capacity issues:

  1. Retry on transient errors (429 / 5xx) with exponential backoff.
  2. Fall back to a cheaper / more-available model (default: gemini-2.5-flash)
     after the primary model keeps failing.

Get a key at https://aistudio.google.com/apikey.
"""
import asyncio
import json
import random

import httpx

from config import get_settings

_BASE = "https://generativelanguage.googleapis.com/v1beta"

# Models tried in order. The first that succeeds wins. The fallback is much
# more reliably available than `gemini-2.5-pro` and produces near-identical
# meeting summaries, so the user almost never notices.
_FALLBACK_MODEL = "gemini-2.5-flash"

_TRANSIENT_STATUSES = {408, 425, 429, 500, 502, 503, 504}
_MAX_RETRIES_PER_MODEL = 4  # ~1+2+4+8 ≈ 15s of waiting at worst


def _key() -> str:
    key = get_settings().gemini_api_key
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set "
            "(get one at https://aistudio.google.com/apikey)"
        )
    return key


def _build_body(prompt: str, *, temperature: float, json_mode: bool) -> dict:
    body: dict = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature},
    }
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"
    return body


def _extract_text(payload: dict) -> str:
    for cand in payload.get("candidates") or []:
        content = cand.get("content") or {}
        for part in content.get("parts") or []:
            t = part.get("text")
            if t:
                return t
    return ""


def _models_to_try() -> list[str]:
    primary = get_settings().gemini_model
    return [primary] if primary == _FALLBACK_MODEL else [primary, _FALLBACK_MODEL]


async def _post_with_retry(
    client: httpx.AsyncClient, url: str, params: dict, body: dict
) -> httpx.Response:
    last: httpx.Response | None = None
    for attempt in range(_MAX_RETRIES_PER_MODEL):
        resp = await client.post(url, params=params, json=body)
        if resp.status_code < 400 or resp.status_code not in _TRANSIENT_STATUSES:
            return resp
        last = resp
        # Exponential backoff with a touch of jitter so concurrent retries don't
        # all hit the same instant.
        delay = (2**attempt) + random.uniform(0, 0.3)
        await asyncio.sleep(delay)
    return last  # caller decides whether to fail or try a different model


async def generate(prompt: str, *, temperature: float = 0.3, json_mode: bool = False) -> str:
    body = _build_body(prompt, temperature=temperature, json_mode=json_mode)
    last_error = "no models attempted"
    async with httpx.AsyncClient(timeout=120) as client:
        for model in _models_to_try():
            url = f"{_BASE}/models/{model}:generateContent"
            resp = await _post_with_retry(client, url, {"key": _key()}, body)
            if resp.status_code < 400:
                return _extract_text(resp.json())
            last_error = f"{model} → {resp.status_code}: {resp.text[:200]}"
            # Try the fallback model on transient failures; on hard 4xx (auth,
            # bad request) the other model would just give the same error.
            if resp.status_code not in _TRANSIENT_STATUSES:
                break
    raise RuntimeError(f"Gemini failed: {last_error}")


async def stream(prompt: str, *, temperature: float = 0.3):
    body = _build_body(prompt, temperature=temperature, json_mode=False)
    last_error = "no models attempted"
    async with httpx.AsyncClient(timeout=300) as client:
        for model in _models_to_try():
            url = f"{_BASE}/models/{model}:streamGenerateContent"
            # Connection + first byte attempt with retry/backoff. Once we're
            # streaming we don't retry mid-response (we'd have to start over).
            for attempt in range(_MAX_RETRIES_PER_MODEL):
                try:
                    async with client.stream(
                        "POST",
                        url,
                        params={"key": _key(), "alt": "sse"},
                        json=body,
                    ) as resp:
                        if (
                            resp.status_code >= 400
                            and resp.status_code in _TRANSIENT_STATUSES
                        ):
                            last_error = (
                                f"{model} → {resp.status_code}: "
                                f"{(await resp.aread()).decode()[:200]}"
                            )
                            await asyncio.sleep((2**attempt) + random.uniform(0, 0.3))
                            continue
                        if resp.status_code >= 400:
                            body_text = (await resp.aread()).decode()
                            raise RuntimeError(
                                f"Gemini {resp.status_code}: {body_text}"
                            )
                        async for line in resp.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            payload = line[len("data:"):].strip()
                            if not payload or payload == "[DONE]":
                                continue
                            try:
                                text = _extract_text(json.loads(payload))
                            except json.JSONDecodeError:
                                continue
                            if text:
                                yield text
                        return  # successful stream
                except RuntimeError:
                    raise
                except Exception as exc:
                    last_error = f"{model} → exception: {exc}"
                    await asyncio.sleep((2**attempt) + random.uniform(0, 0.3))
    raise RuntimeError(f"Gemini stream failed: {last_error}")
