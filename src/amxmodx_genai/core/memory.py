"""Persistent per-session memory.

Conversation turns are stored in a SQLite database so they survive sidecar
restarts. Sessions are keyed by arbitrary string IDs chosen by the plugin:
player index string ("3"), team name ("ct_team"), or any custom key.

Two tiers:
- Short-term (sessions table): raw message turns, capped at GENAI_MEMORY_MAX_MESSAGES. Cleared on clear().
- Long-term (longterm table): LLM-generated summary from past sessions. Survives clear().
"""

import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Integer, String, Text, create_engine, delete, event, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from amxmodx_genai.config import settings


class _Base(DeclarativeBase):
    pass


class _SessionRow(_Base):
    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(String, primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)


class _LongtermRow(_Base):
    __tablename__ = "longterm"

    session_id: Mapped[str] = mapped_column(String, primary_key=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


def _make_engine(path: Path | None = None):
    """Create and initialize the SQLite database engine."""
    p = path or settings.memory_path
    p.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{p}", connect_args={"timeout": 10})

    @event.listens_for(engine, "connect")
    def _set_wal(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA journal_mode=WAL")

    @event.listens_for(engine, "begin")
    def _begin_immediate(conn):
        # BEGIN IMMEDIATE serializes concurrent writers at the SQLite level so
        # the read-then-write seq computation in update() is atomic.
        conn.exec_driver_sql("BEGIN IMMEDIATE")

    _Base.metadata.create_all(engine)
    return engine


try:
    _engine = _make_engine()
except Exception as exc:
    raise RuntimeError(
        f"Failed to initialize memory database at {settings.memory_path}: {exc}"
    ) from exc


def get(session_id: str) -> list[dict]:
    """Return all short-term message turns for session_id, oldest first."""
    with Session(_engine) as db:
        rows = db.scalars(
            select(_SessionRow)
            .where(_SessionRow.session_id == session_id)
            .order_by(_SessionRow.seq)
        ).all()
        return [{"role": r.role, "content": json.loads(r.content)} for r in rows]


def update(session_id: str, prompt: str, response: str) -> None:
    """Append a user/assistant turn and trim the session to memory_max_messages rows."""
    with Session(_engine) as db, db.begin():
        max_seq = db.scalar(
            select(_SessionRow.seq)
            .where(_SessionRow.session_id == session_id)
            .order_by(_SessionRow.seq.desc())
            .limit(1)
        )
        next_seq = (max_seq if max_seq is not None else -1) + 1
        db.add(
            _SessionRow(
                session_id=session_id,
                seq=next_seq,
                role="user",
                content=json.dumps([{"type": "text", "text": prompt}]),
            )
        )
        db.add(
            _SessionRow(
                session_id=session_id,
                seq=next_seq + 1,
                role="assistant",
                content=json.dumps([{"type": "text", "text": response}]),
            )
        )
        keep_seqs = db.scalars(
            select(_SessionRow.seq)
            .where(_SessionRow.session_id == session_id)
            .order_by(_SessionRow.seq.desc())
            .limit(settings.memory_max_messages * 2)
        ).all()
        db.execute(
            delete(_SessionRow)
            .where(_SessionRow.session_id == session_id)
            .where(_SessionRow.seq.not_in(keep_seqs))
        )


def clear(session_id: str) -> None:
    """Delete all short-term turns for session_id."""
    with Session(_engine) as db, db.begin():
        db.execute(delete(_SessionRow).where(_SessionRow.session_id == session_id))


def get_longterm(session_id: str) -> str:
    """Return the long-term summary for session_id, or empty string if none."""
    with Session(_engine) as db:
        row = db.get(_LongtermRow, session_id)
        return row.summary if row else ""


def set_longterm(session_id: str, summary: str) -> None:
    """Upsert the long-term summary for session_id."""
    with Session(_engine) as db, db.begin():
        row = db.get(_LongtermRow, session_id)
        now = datetime.now(UTC).isoformat(timespec="seconds")
        if row:
            row.summary = summary
            row.updated_at = now
        else:
            db.add(_LongtermRow(session_id=session_id, summary=summary, updated_at=now))


def clear_longterm(session_id: str) -> None:
    """Delete the long-term summary for session_id, if any."""
    with Session(_engine) as db, db.begin():
        row = db.get(_LongtermRow, session_id)
        if row:
            db.delete(row)
