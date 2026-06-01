"""Audio storage in MongoDB GridFS.

The transcript / summary / notes are embedded directly in the meeting document
(see db.py), so this module only deals with the audio binary.
"""
from bson import ObjectId

from core.mongo_client import gridfs


async def upload_audio(
    session_id: str, local_path: str, content_type: str = "audio/webm"
) -> ObjectId:
    """Stream a local file into GridFS. Returns the GridFS file ObjectId."""
    bucket = gridfs()
    with open(local_path, "rb") as f:
        return await bucket.upload_from_stream(
            f"{session_id}.audio",
            f,
            metadata={"session_id": session_id, "content_type": content_type},
        )


async def upload_audio_bytes(
    session_id: str, data: bytes, content_type: str = "audio/webm"
) -> ObjectId:
    import io

    return await gridfs().upload_from_stream(
        f"{session_id}.audio",
        io.BytesIO(data),
        metadata={"session_id": session_id, "content_type": content_type},
    )


async def download_audio_to_file(audio_file_id: ObjectId, local_path: str) -> str:
    bucket = gridfs()
    with open(local_path, "wb") as f:
        await bucket.download_to_stream(audio_file_id, f)
    return local_path


async def open_audio_stream(audio_file_id: ObjectId):
    """Open a GridFS read stream (used by the audio download endpoint)."""
    return await gridfs().open_download_stream(audio_file_id)


async def delete_audio(audio_file_id: ObjectId) -> None:
    try:
        await gridfs().delete(audio_file_id)
    except Exception:
        # File may already be gone; not worth raising.
        pass
