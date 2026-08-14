"""Unit tests for persistent session memory."""

import asyncio
import sys
import time

import pytest


@pytest.fixture(autouse=True)
def fresh_memory(tmp_path):
    # Clear cached modules so each test gets a fresh import.
    for mod in list(sys.modules):
        if mod.startswith("amxmodx_genai"):
            del sys.modules[mod]

    import amxmodx_genai.core.memory as mem

    mem._engine = mem._make_engine(tmp_path / "test_memory.db")

    yield

    for mod in list(sys.modules):
        if mod.startswith("amxmodx_genai"):
            del sys.modules[mod]


def _mem():
    import amxmodx_genai.core.memory as m

    return m


def test_get_empty():
    assert _mem().get("1") == []


def test_update_and_get():
    mem = _mem()
    mem.update("1", "what should I buy?", "Buy AK47.")
    result = mem.get("1")
    assert len(result) == 2
    assert result[0] == {
        "role": "user",
        "content": [{"type": "text", "text": "what should I buy?"}],
    }
    assert result[1] == {"role": "assistant", "content": [{"type": "text", "text": "Buy AK47."}]}


def test_update_accumulates():
    mem = _mem()
    mem.update("1", "first", "response one")
    mem.update("1", "second", "response two")
    assert len(mem.get("1")) == 4


def test_update_caps_at_10_turns():
    # memory_max_messages=10 means 10 conversation turns (20 rows).
    mem = _mem()
    for i in range(15):  # 15 turns = 30 rows, exceeds the 20-row cap
        mem.update("1", f"prompt {i}", f"reply {i}")
    assert len(mem.get("1")) == 20  # 10 turns * 2 rows each


def test_update_trims_oldest():
    mem = _mem()
    for i in range(25):
        mem.update("1", f"prompt {i}", f"reply {i}")
    result = mem.get("1")
    assert result[-1]["content"][0]["text"] == "reply 24"


def test_clear():
    mem = _mem()
    mem.update("1", "q", "a")
    mem.clear("1")
    assert mem.get("1") == []


def test_clear_nonexistent_session():
    _mem().clear("nonexistent")  # should not raise


def test_player_sessions_isolated():
    mem = _mem()
    mem.update("1", "player 1 prompt", "player 1 reply")
    mem.update("2", "player 2 prompt", "player 2 reply")
    assert len(mem.get("1")) == 2
    assert len(mem.get("2")) == 2
    assert mem.get("1")[0]["content"][0]["text"] == "player 1 prompt"


def test_named_session():
    mem = _mem()
    mem.update("ct_team", "team question", "team answer")
    assert mem.get("ct_team") != []
    assert mem.get("1") == []


def test_named_session_independent_of_player():
    mem = _mem()
    mem.update("1", "player prompt", "player reply")
    mem.update("ct_team", "team prompt", "team reply")
    mem.clear("1")
    assert mem.get("1") == []
    assert mem.get("ct_team") != []


def test_get_longterm_empty():
    assert _mem().get_longterm("1") == ""


def test_set_and_get_longterm():
    mem = _mem()
    mem.set_longterm("1", "- Prefers AK47\n- Plays aggressively")
    assert mem.get_longterm("1") == "- Prefers AK47\n- Plays aggressively"


def test_set_longterm_upserts():
    mem = _mem()
    mem.set_longterm("1", "first summary")
    mem.set_longterm("1", "updated summary")
    assert mem.get_longterm("1") == "updated summary"


def test_longterm_independent_of_shortterm():
    mem = _mem()
    mem.set_longterm("1", "some summary")
    mem.clear("1")
    assert mem.get_longterm("1") == "some summary"


def test_longterm_sessions_isolated():
    mem = _mem()
    mem.set_longterm("1", "player 1 summary")
    mem.set_longterm("2", "player 2 summary")
    assert mem.get_longterm("1") == "player 1 summary"
    assert mem.get_longterm("2") == "player 2 summary"


def test_persists_across_reimport(tmp_path):
    db_path = tmp_path / "persist_test.db"
    for mod in list(sys.modules):
        if mod.startswith("amxmodx_genai"):
            del sys.modules[mod]

    import amxmodx_genai.core.memory as mem1

    mem1._engine = mem1._make_engine(db_path)
    mem1.update("42", "hello", "world")

    # Simulate restart: clear modules and re-import with the same DB path.
    for mod in list(sys.modules):
        if mod.startswith("amxmodx_genai"):
            del sys.modules[mod]

    import amxmodx_genai.core.memory as mem2

    mem2._engine = mem2._make_engine(db_path)

    result = mem2.get("42")
    assert len(result) == 2
    assert result[0]["content"][0]["text"] == "hello"


# ---------------------------------------------------------------------------
# Concurrency: multiple asyncio tasks updating the same session_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_updates_same_session_no_data_loss():
    """N concurrent asyncio tasks writing to the same session all complete without error."""
    mem = _mem()
    n = 10

    async def write_turn(i: int) -> None:
        await asyncio.to_thread(mem.update, "shared", f"prompt {i}", f"reply {i}")

    await asyncio.gather(*[write_turn(i) for i in range(n)])

    rows = mem.get("shared")
    # Each write adds 2 rows; trim cap is 40 rows (20 turns).
    # n=10 means 20 rows total which is within cap - all should survive.
    assert len(rows) == n * 2


@pytest.mark.asyncio
async def test_concurrent_updates_different_sessions_isolated():
    """Concurrent writes to different sessions don't bleed data across them."""
    mem = _mem()

    async def write_session(sid: str) -> None:
        for i in range(3):
            await asyncio.to_thread(mem.update, sid, f"p{i}", f"r{i}")

    await asyncio.gather(write_session("alpha"), write_session("beta"), write_session("gamma"))

    assert len(mem.get("alpha")) == 6
    assert len(mem.get("beta")) == 6
    assert len(mem.get("gamma")) == 6
    # Verify no cross-contamination
    for row in mem.get("alpha"):
        assert row["content"][0]["text"].startswith("p") or row["content"][0]["text"].startswith(
            "r"
        )


@pytest.mark.asyncio
async def test_concurrent_read_and_write_same_session():
    """Reads concurrent with writes never raise; result is internally consistent."""
    mem = _mem()
    mem.update("sess", "seed", "seed_reply")
    errors: list[Exception] = []

    async def writer() -> None:
        for i in range(5):
            try:
                await asyncio.to_thread(mem.update, "sess", f"w{i}", f"wr{i}")
            except Exception as exc:
                errors.append(exc)

    async def reader() -> None:
        for _ in range(10):
            try:
                rows = await asyncio.to_thread(mem.get, "sess")
                # row count must always be even (user+assistant pairs)
                assert len(rows) % 2 == 0
            except Exception as exc:
                errors.append(exc)
            await asyncio.sleep(0)

    await asyncio.gather(writer(), reader())
    assert errors == [], f"concurrent read/write raised: {errors}"


# ---------------------------------------------------------------------------
# session_meta: last_seen updated by memory.update
# ---------------------------------------------------------------------------


def test_update_sets_last_seen():
    from sqlalchemy.orm import Session

    mem = _mem()
    before = time.time()
    mem.update("player1", "hello", "world")
    after = time.time()

    with Session(mem._engine) as db:
        row = db.get(mem._SessionMetaRow, "player1")
    assert row is not None
    assert before <= row.last_seen <= after


def test_update_advances_last_seen():
    mem = _mem()
    mem.update("player1", "first", "one")
    from sqlalchemy.orm import Session

    with Session(mem._engine) as db:
        ts1 = db.get(mem._SessionMetaRow, "player1").last_seen

    mem.update("player1", "second", "two")

    with Session(mem._engine) as db:
        ts2 = db.get(mem._SessionMetaRow, "player1").last_seen

    assert ts2 >= ts1


# ---------------------------------------------------------------------------
# vacuum: removes stale sessions, preserves fresh ones
# ---------------------------------------------------------------------------


def test_vacuum_returns_zero_when_no_sessions():
    assert _mem().vacuum(1) == 0


def test_vacuum_removes_stale_sessions():
    mem = _mem()
    # Write a session then backdate its last_seen to 10 days ago.
    mem.update("old_player", "q", "a")
    from sqlalchemy.orm import Session

    with Session(mem._engine) as db, db.begin():
        row = db.get(mem._SessionMetaRow, "old_player")
        row.last_seen = time.time() - 10 * 86400

    removed = mem.vacuum(5)  # 5-day TTL

    assert removed == 1
    assert mem.get("old_player") == []


def test_vacuum_preserves_fresh_sessions():
    mem = _mem()
    mem.update("fresh_player", "q", "a")

    removed = mem.vacuum(5)  # session was just written, well within TTL

    assert removed == 0
    assert mem.get("fresh_player") != []


def test_vacuum_removes_longterm_for_stale_session():
    mem = _mem()
    mem.update("old_player", "q", "a")
    mem.set_longterm("old_player", "some summary")

    from sqlalchemy.orm import Session

    with Session(mem._engine) as db, db.begin():
        row = db.get(mem._SessionMetaRow, "old_player")
        row.last_seen = time.time() - 10 * 86400

    mem.vacuum(5)

    assert mem.get_longterm("old_player") == ""


def test_vacuum_returns_count_of_removed_sessions():
    mem = _mem()
    for sid in ("old1", "old2", "old3"):
        mem.update(sid, "q", "a")

    cutoff = time.time() - 10 * 86400
    from sqlalchemy.orm import Session

    with Session(mem._engine) as db, db.begin():
        for sid in ("old1", "old2", "old3"):
            db.get(mem._SessionMetaRow, sid).last_seen = cutoff

    assert mem.vacuum(5) == 3


def test_vacuum_mixed_fresh_and_stale():
    mem = _mem()
    mem.update("fresh", "q", "a")
    mem.update("stale", "q", "a")

    from sqlalchemy.orm import Session

    with Session(mem._engine) as db, db.begin():
        db.get(mem._SessionMetaRow, "stale").last_seen = time.time() - 10 * 86400

    removed = mem.vacuum(5)

    assert removed == 1
    assert mem.get("fresh") != []
    assert mem.get("stale") == []
