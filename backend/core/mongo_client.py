"""Shared MongoDB connection.

One async client per process (motor handles its own connection pool), exposed
via small accessor helpers so the rest of the code never has to know about
collection names or GridFS plumbing.
"""
from functools import lru_cache

from motor.motor_asyncio import (
    AsyncIOMotorClient,
    AsyncIOMotorDatabase,
    AsyncIOMotorGridFSBucket,
)

from config import get_settings

MEETINGS_COLLECTION = "meetings"
GRIDFS_BUCKET_NAME = "audio"  # produces audio.files / audio.chunks


@lru_cache
def get_client() -> AsyncIOMotorClient:
    settings = get_settings()
    if not settings.mongo_uri:
        raise RuntimeError("MONGO_URI is not set")
    return AsyncIOMotorClient(settings.mongo_uri)


def get_db() -> AsyncIOMotorDatabase:
    return get_client()[get_settings().mongo_db_name]


def meetings():
    return get_db()[MEETINGS_COLLECTION]


def gridfs() -> AsyncIOMotorGridFSBucket:
    return AsyncIOMotorGridFSBucket(get_db(), bucket_name=GRIDFS_BUCKET_NAME)


async def ensure_indexes() -> None:
    """Idempotent index setup. Called once at startup."""
    await meetings().create_index("id", unique=True)
    await meetings().create_index("created_at")
    await meetings().create_index([("patient_email", 1), ("created_at", -1)])

    # Patient index (defined here so all index creation runs in one place).
    from core.patients import ensure_indexes as ensure_patient_indexes
    await ensure_patient_indexes()
