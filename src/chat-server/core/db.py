import asyncio
import asyncpg
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .config import DATABASE_URL

logger = logging.getLogger("chat.db")

pool: Optional[asyncpg.Pool] = None


async def _setup_codecs(conn: asyncpg.Connection):
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )
    await conn.set_type_codec(
        "json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )


async def init_db():
    global pool
    # Retry until TimescaleDB sidecar is ready (both containers start simultaneously)
    for attempt in range(1, 31):
        try:
            pool = await asyncpg.create_pool(
                DATABASE_URL, init=_setup_codecs, min_size=2, max_size=10
            )
            break
        except Exception as exc:
            if attempt == 30:
                raise
            logger.warning("DB not ready (attempt %d/30): %s — retrying in 2s", attempt, exc)
            await asyncio.sleep(2)

    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_sessions (
                session_id  TEXT        PRIMARY KEY,
                subject_id  TEXT        NOT NULL,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                metadata    JSONB       NOT NULL DEFAULT '{}'::jsonb
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_sessions_subject
                ON chat_sessions (subject_id)
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id            BIGSERIAL,
                session_id    TEXT        NOT NULL,
                timestamp     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                direction     TEXT        NOT NULL,
                task_id       TEXT,
                subject_id    TEXT,
                request_json  JSONB,
                response_json JSONB,
                PRIMARY KEY (id, timestamp)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_messages_session
                ON chat_messages (session_id, timestamp)
        """)
        # TimescaleDB hypertable — silently skipped if not available
        try:
            await conn.execute(
                "SELECT create_hypertable('chat_messages', 'timestamp', if_not_exists => TRUE)"
            )
            logger.info("TimescaleDB hypertable ready")
        except Exception as e:
            logger.debug("Hypertable skipped (not TimescaleDB or already plain PG): %s", e)
    logger.info("Database schema ready")


def _row(record: asyncpg.Record) -> Dict[str, Any]:
    d = dict(record)
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return d


async def create_session(session_id: str, subject_id: str, metadata: Dict = None) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO chat_sessions (session_id, subject_id, metadata) VALUES ($1, $2, $3)",
            session_id, subject_id, metadata or {},
        )


async def get_session(session_id: str) -> Optional[Dict]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM chat_sessions WHERE session_id = $1", session_id
        )
        return _row(row) if row else None


async def list_sessions(subject_id: Optional[str] = None) -> List[Dict]:
    async with pool.acquire() as conn:
        if subject_id:
            rows = await conn.fetch(
                "SELECT * FROM chat_sessions WHERE subject_id = $1 ORDER BY created_at DESC",
                subject_id,
            )
        else:
            rows = await conn.fetch(
                "SELECT * FROM chat_sessions ORDER BY created_at DESC LIMIT 500"
            )
        return [_row(r) for r in rows]


async def save_message(
    session_id: str,
    direction: str,
    task_id: Optional[str],
    subject_id: Optional[str],
    request_json: Optional[Dict] = None,
    response_json: Optional[Dict] = None,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO chat_messages
               (session_id, direction, task_id, subject_id, request_json, response_json)
               VALUES ($1, $2, $3, $4, $5, $6)""",
            session_id, direction, task_id, subject_id, request_json, response_json,
        )


async def list_messages(session_id: str) -> List[Dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM chat_messages WHERE session_id = $1 ORDER BY timestamp ASC",
            session_id,
        )
        return [_row(r) for r in rows]


async def close_db():
    global pool
    if pool:
        await pool.close()
        pool = None
