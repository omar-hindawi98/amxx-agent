import os
import sys

import pytest


@pytest.fixture(autouse=True)
def fresh_memory(tmp_path):
    db_file = str(tmp_path / "test_memory.db")
    os.environ["GENAI_MEMORY_PATH"] = db_file

    # Force re-import so config and thread-local connections use the new path.
    for mod in list(sys.modules):
        if mod.startswith("amxmodx_genai"):
            del sys.modules[mod]

    yield

    # Cleanup env var; modules will be re-imported fresh next test.
    del os.environ["GENAI_MEMORY_PATH"]
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
    assert result[0] == {"role": "user", "content": [{"text": "what should I buy?"}]}
    assert result[1] == {"role": "assistant", "content": [{"text": "Buy AK47."}]}


def test_update_accumulates():
    mem = _mem()
    mem.update("1", "first", "response one")
    mem.update("1", "second", "response two")
    assert len(mem.get("1")) == 4


def test_update_caps_at_20_messages():
    mem = _mem()
    for i in range(15):
        mem.update("1", f"prompt {i}", f"reply {i}")
    assert len(mem.get("1")) == 20


def test_update_trims_oldest():
    mem = _mem()
    for i in range(15):
        mem.update("1", f"prompt {i}", f"reply {i}")
    result = mem.get("1")
    assert result[-1]["content"][0]["text"] == "reply 14"


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
    db_file = str(tmp_path / "persist_test.db")
    os.environ["GENAI_MEMORY_PATH"] = db_file
    for mod in list(sys.modules):
        if mod.startswith("amxmodx_genai"):
            del sys.modules[mod]

    import amxmodx_genai.core.memory as mem1

    mem1.update("42", "hello", "world")

    # Simulate restart: clear modules and re-import.
    for mod in list(sys.modules):
        if mod.startswith("amxmodx_genai"):
            del sys.modules[mod]

    import amxmodx_genai.core.memory as mem2

    result = mem2.get("42")
    assert len(result) == 2
    assert result[0]["content"][0]["text"] == "hello"
