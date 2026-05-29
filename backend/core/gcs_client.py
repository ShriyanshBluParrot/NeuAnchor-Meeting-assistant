import asyncio
import json
from functools import lru_cache

from google.cloud import storage

from config import get_settings


@lru_cache
def _client() -> storage.Client:
    settings = get_settings()
    return storage.Client(project=settings.gcp_project_id)


def _bucket():
    return _client().bucket(get_settings().gcs_bucket_name)


def prefix_for(session_id: str) -> str:
    return f"gs://{get_settings().gcs_bucket_name}/meetings/{session_id}/"


# Use a chunked, resumable upload for any blob over ~5 MB so a slow network
# can't drop a long meeting recording. Generous timeout for the same reason.
_UPLOAD_CHUNK = 5 * 1024 * 1024
_UPLOAD_TIMEOUT = 600  # seconds


async def upload_file(session_id: str, name: str, local_path: str) -> str:
    """Upload a local file to meetings/<session_id>/<name>. Returns gs:// URI."""
    def _do():
        blob = _bucket().blob(
            f"meetings/{session_id}/{name}", chunk_size=_UPLOAD_CHUNK
        )
        blob.upload_from_filename(local_path, timeout=_UPLOAD_TIMEOUT)
        return f"gs://{get_settings().gcs_bucket_name}/{blob.name}"

    return await asyncio.to_thread(_do)


async def upload_bytes(session_id: str, name: str, data: bytes, content_type: str) -> str:
    def _do():
        blob = _bucket().blob(
            f"meetings/{session_id}/{name}", chunk_size=_UPLOAD_CHUNK
        )
        blob.upload_from_string(
            data, content_type=content_type, timeout=_UPLOAD_TIMEOUT
        )
        return f"gs://{get_settings().gcs_bucket_name}/{blob.name}"

    return await asyncio.to_thread(_do)


async def upload_text(session_id: str, name: str, text: str) -> str:
    return await upload_bytes(session_id, name, text.encode("utf-8"), "text/plain")


async def upload_json(session_id: str, name: str, obj) -> str:
    payload = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
    return await upload_bytes(session_id, name, payload, "application/json")


async def download_to_file(session_id: str, name: str, local_path: str) -> str:
    """Download an artifact to a local path. Returns the path."""
    def _do():
        blob = _bucket().blob(f"meetings/{session_id}/{name}")
        blob.download_to_filename(local_path)
        return local_path

    return await asyncio.to_thread(_do)


async def download_text(session_id: str, name: str) -> str:
    def _do():
        blob = _bucket().blob(f"meetings/{session_id}/{name}")
        return blob.download_as_text()

    return await asyncio.to_thread(_do)


async def download_json(session_id: str, name: str):
    raw = await download_text(session_id, name)
    return json.loads(raw)


async def exists(session_id: str, name: str) -> bool:
    def _do():
        return _bucket().blob(f"meetings/{session_id}/{name}").exists()

    return await asyncio.to_thread(_do)


async def signed_url(session_id: str, name: str, minutes: int = 60) -> str:
    """Generate a temporary read URL for an artifact (e.g. the audio file)."""
    from datetime import timedelta

    def _do():
        blob = _bucket().blob(f"meetings/{session_id}/{name}")
        return blob.generate_signed_url(expiration=timedelta(minutes=minutes), method="GET")

    return await asyncio.to_thread(_do)
