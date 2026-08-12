"""Persistent per-session memory.

Conversation turns are stored in a SQLite database so they survive sidecar
restarts. Sessions are keyed by arbitrary string IDs chosen by the plugin:
player index string ("3"), team name ("ct_team"), or any custom key.

Two tiers:
- Short-term (sessions table): raw message turns, capped at 20. Cleared on clear().
- Long-term (longterm table): LLM-generated summary from past sessions. Survives clear().
"""

import json
import sqlite3
import threading
from datetime import UTC, datetime

from amxmodx_genai.config import MEMORY_PATH

_MAX_MESSAGES = 20
_local = threading.local()
_init_lock = threading.Lock()


def _db() -> sqlite3.Connection:
    if not hasattr(_local, "conn"):
        with _init_lock:
            MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(MEMORY_PATH), timeout=10)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT NOT NULL,
                    seq        INTEGER NOT NULL,
                    role       TEXT NOT NULL,
                    content    TEXT NOT NULL,
                    PRIMARY KEY (session_id, seq)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS longterm (
                    session_id TEXT PRIMARY KEY,
                    summary    TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()
            _local.conn = conn
    return _local.conn


def get(session_id: str) -> list[dict]:
    rows = (
        _db()
        .execute(
            "SELECT role, content FROM sessions WHERE session_id = ? ORDER BY seq",
            (session_id,),
        )
        .fetchall()
    )
    return [{"role": role, "content": json.loads(content)} for role, content in rows]


def update(session_id: str, prompt: str, response: str) -> None:
    db = _db()
    row = db.execute(
        "SELECT COALESCE(MAX(seq), -1) FROM sessions WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    next_seq = row[0] + 1
    with db:
        db.executemany(
            "INSERT INTO sessions (session_id, seq, role, content) VALUES (?, ?, ?, ?)",
            [
                (session_id, next_seq, "user", json.dumps([{"text": prompt}])),
                (session_id, next_seq + 1, "assistant", json.dumps([{"text": response}])),
            ],
        )
        db.execute(
            """
            DELETE FROM sessions
            WHERE session_id = ?
              AND seq NOT IN (
                SELECT seq FROM sessions
                WHERE session_id = ?
                ORDER BY seq DESC
                LIMIT ?
              )
            """,
            (session_id, session_id, _MAX_MESSAGES),
        )


def clear(session_id: str) -> None:
    db = _db()
    with db:
        db.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))


def get_longterm(session_id: str) -> str:
    row = (
        _db().execute("SELECT summary FROM longterm WHERE session_id = ?", (session_id,)).fetchone()
    )
    return row[0] if row else ""


def set_longterm(session_id: str, summary: str) -> None:
    db = _db()
    now = datetime.now(UTC).isoformat(timespec="seconds")
    with db:
        db.execute(
            """
            INSERT INTO longterm (session_id, summary, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET summary = excluded.summary,
                                                  updated_at = excluded.updated_at
            """,
            (session_id, summary, now),
        )
