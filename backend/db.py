import datetime as dt

import aiosqlite

from config import get_settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meetings (
    id            TEXT PRIMARY KEY,
    mode          TEXT NOT NULL,              -- 'online' | 'offline'
    status        TEXT NOT NULL,              -- recording | processing | ready | error
    title         TEXT,
    meet_url      TEXT,
    recall_bot_id TEXT,
    gcs_prefix    TEXT,
    error_msg     TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
"""


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


async def init_db() -> None:
    async with aiosqlite.connect(get_settings().db_path) as conn:
        await conn.execute(_SCHEMA)
        await conn.commit()


async def create_meeting(session_id: str, mode: str, status: str, **fields) -> None:
    now = _now()
    cols = ["id", "mode", "status", "created_at", "updated_at"]
    vals = [session_id, mode, status, now, now]
    for k, v in fields.items():
        cols.append(k)
        vals.append(v)
    placeholders = ", ".join("?" for _ in cols)
    sql = f"INSERT INTO meetings ({', '.join(cols)}) VALUES ({placeholders})"
    async with aiosqlite.connect(get_settings().db_path) as conn:
        await conn.execute(sql, vals)
        await conn.commit()


async def update_meeting(session_id: str, **fields) -> None:
    fields["updated_at"] = _now()
    assignments = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [session_id]
    async with aiosqlite.connect(get_settings().db_path) as conn:
        await conn.execute(f"UPDATE meetings SET {assignments} WHERE id = ?", vals)
        await conn.commit()


async def get_meeting(session_id: str) -> dict | None:
    async with aiosqlite.connect(get_settings().db_path) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM meetings WHERE id = ?", (session_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_meeting_by_bot(bot_id: str) -> dict | None:
    async with aiosqlite.connect(get_settings().db_path) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT * FROM meetings WHERE recall_bot_id = ?", (bot_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def list_meetings() -> list[dict]:
    async with aiosqlite.connect(get_settings().db_path) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT * FROM meetings ORDER BY created_at DESC"
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]
