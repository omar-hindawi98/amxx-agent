"""Pydantic models for the plugin wire protocol."""

from pydantic import BaseModel, field_validator


class ToolDef(BaseModel):
    """A plugin tool registration received from the game server."""

    name: str
    description: str
    params: list[dict] | None = None


class QueryMsg(BaseModel):
    """A query request from a plugin."""

    player: int = -1
    session_id: str = ""
    prompt: str = ""
    plugin: str = ""
    system: str = ""
    tools: list[ToolDef] = []
    skills: list[str] = []

    @field_validator("prompt", "system", mode="before")
    @classmethod
    def _strip(cls, v: object) -> str:
        """Strip leading/trailing whitespace from text fields."""
        return (v or "").strip()  # type: ignore[return-value]


class ClearMemoryMsg(BaseModel):
    """A request to clear and summarize a session's short-term memory."""

    player: int = -1
    session_id: str = ""
