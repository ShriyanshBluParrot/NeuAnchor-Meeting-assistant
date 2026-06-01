"""Patient records.

A patient is identified by their email (lowercased, trimmed). Meetings link to
a patient via the `patient_email` field on the meeting document; the patient
document itself just stores profile data.
"""
import datetime as dt
import re

from core.mongo_client import get_db

PATIENTS_COLLECTION = "patients"

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalise_email(raw: str) -> str:
    email = (raw or "").strip().lower()
    if not _EMAIL_RE.match(email):
        raise ValueError(f"Invalid email: {raw!r}")
    return email


def collection():
    return get_db()[PATIENTS_COLLECTION]


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


async def ensure_indexes() -> None:
    await collection().create_index("email", unique=True)


async def upsert(email: str, name: str | None = None) -> dict:
    """Insert a new patient or touch an existing one. Returns the patient doc."""
    email = normalise_email(email)
    now = _now()
    update: dict = {"$set": {"updated_at": now}}
    if name is not None:
        update["$set"]["name"] = name.strip() or None
    update["$setOnInsert"] = {"email": email, "created_at": now}
    if name is None:
        # Don't clobber an existing name if the caller didn't pass one.
        update["$setOnInsert"]["name"] = None
    await collection().update_one({"email": email}, update, upsert=True)
    return await collection().find_one({"email": email})


async def get(email: str) -> dict | None:
    return await collection().find_one({"email": normalise_email(email)})


async def list_all() -> list[dict]:
    cursor = collection().find().sort("updated_at", -1)
    return [doc async for doc in cursor]
