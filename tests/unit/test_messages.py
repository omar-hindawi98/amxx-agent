"""Unit tests for wire protocol Pydantic models."""

import pytest
from pydantic import ValidationError

from amxmodx_genai.core.messages import ClearMemoryMsg, QueryMsg, ToolDef

# ---------------------------------------------------------------------------
# ToolDef
# ---------------------------------------------------------------------------


def test_tooldef_required_fields():
    t = ToolDef(name="get_map", description="Returns current map")
    assert t.name == "get_map"
    assert t.description == "Returns current map"
    assert t.params is None


def test_tooldef_with_params():
    t = ToolDef(name="kick", description="Kick player", params=[{"name": "id", "type": "integer"}])
    assert t.params == [{"name": "id", "type": "integer"}]


def test_tooldef_missing_name_raises():
    with pytest.raises(ValidationError):
        ToolDef(description="no name")


def test_tooldef_missing_description_raises():
    with pytest.raises(ValidationError):
        ToolDef(name="no_desc")


# ---------------------------------------------------------------------------
# QueryMsg defaults
# ---------------------------------------------------------------------------


def test_querymsg_defaults():
    q = QueryMsg()
    assert q.player == -1
    assert q.session_id == ""
    assert q.prompt == ""
    assert q.plugin == ""
    assert q.system == ""
    assert q.tools == []
    assert q.skills == []


def test_querymsg_full():
    q = QueryMsg(
        player=3,
        session_id="ct_team",
        prompt="hello",
        plugin="myplugin",
        system="You are helpful.",
        tools=[{"name": "get_map", "description": "Map name"}],
        skills=["search"],
    )
    assert q.player == 3
    assert q.session_id == "ct_team"
    assert q.prompt == "hello"
    assert q.plugin == "myplugin"
    assert q.system == "You are helpful."
    assert len(q.tools) == 1
    assert isinstance(q.tools[0], ToolDef)
    assert q.skills == ["search"]


# ---------------------------------------------------------------------------
# QueryMsg._strip validator
# ---------------------------------------------------------------------------


def test_querymsg_prompt_stripped():
    q = QueryMsg(prompt="  hello world  ")
    assert q.prompt == "hello world"


def test_querymsg_system_stripped():
    q = QueryMsg(system="\n  be nice \n")
    assert q.system == "be nice"


def test_querymsg_none_prompt_becomes_empty():
    q = QueryMsg(prompt=None)
    assert q.prompt == ""


def test_querymsg_none_system_becomes_empty():
    q = QueryMsg(system=None)
    assert q.system == ""


def test_querymsg_whitespace_only_prompt_becomes_empty():
    q = QueryMsg(prompt="   ")
    assert q.prompt == ""


# ---------------------------------------------------------------------------
# QueryMsg.tools - nested ToolDef validation
# ---------------------------------------------------------------------------


def test_querymsg_tools_validated_as_tooldef():
    q = QueryMsg(tools=[{"name": "x", "description": "y"}])
    assert isinstance(q.tools[0], ToolDef)


def test_querymsg_invalid_tool_raises():
    with pytest.raises(ValidationError):
        QueryMsg(tools=[{"name": "missing_description"}])


# ---------------------------------------------------------------------------
# QueryMsg.model_validate from dict (wire format)
# ---------------------------------------------------------------------------


def test_querymsg_model_validate():
    raw = {"type": "query", "player": 2, "prompt": " hi ", "session_id": "2"}
    q = QueryMsg.model_validate(raw)
    assert q.player == 2
    assert q.prompt == "hi"
    assert q.session_id == "2"


# ---------------------------------------------------------------------------
# ClearMemoryMsg
# ---------------------------------------------------------------------------


def test_clearmemorymsg_defaults():
    c = ClearMemoryMsg()
    assert c.player == -1
    assert c.session_id == ""


def test_clearmemorymsg_from_dict():
    c = ClearMemoryMsg.model_validate({"type": "clear_memory", "player": 5, "session_id": "5"})
    assert c.player == 5
    assert c.session_id == "5"


def test_clearmemorymsg_extra_fields_ignored():
    c = ClearMemoryMsg.model_validate({"player": 1, "session_id": "1", "unknown": "ignored"})
    assert c.player == 1
