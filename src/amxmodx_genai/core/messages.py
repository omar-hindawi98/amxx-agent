"""Pydantic models for the plugin wire protocol."""

from pydantic import BaseModel, Field, field_validator

# Generous but bounded limits to prevent abuse via the TCP socket.
_MAX_SESSION_ID = 256
_MAX_PROMPT = 8192
_MAX_SYSTEM = 32768


class ToolDef(BaseModel):
    """A plugin tool registration received from the game server."""

    name: str
    description: str
    params: list[dict] | None = None


class QueryMsg(BaseModel):
    """A query request from a plugin."""

    player: int = -1
    session_id: str = Field(default="", max_length=_MAX_SESSION_ID)
    prompt: str = Field(default="", max_length=_MAX_PROMPT)
    plugin: str = ""
    system: str = Field(default="", max_length=_MAX_SYSTEM)
    tools: list[ToolDef] = []
    skills: list[str] = []
    no_memory: bool = False

    @field_validator("prompt", "system", mode="before")
    @classmethod
    def _strip(cls, v: object) -> str:
        """Strip leading/trailing whitespace from text fields."""
        return (v or "").strip()  # type: ignore[return-value]


class ClearMemoryMsg(BaseModel):
    """A request to clear and summarize a session's short-term memory."""

    player: int = -1
    session_id: str = Field(default="", max_length=_MAX_SESSION_ID)


class ClearLongtermMsg(BaseModel):
    """A request to discard a session's long-term summary without touching short-term memory."""

    player: int = -1
    session_id: str = Field(default="", max_length=_MAX_SESSION_ID)
