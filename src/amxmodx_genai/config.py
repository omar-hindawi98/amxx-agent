import os
from pathlib import Path

HOST = os.environ.get("GENAI_HOST", "127.0.0.1")
PORT = int(os.environ.get("GENAI_PORT", "27016"))
MODEL = os.environ.get("GENAI_MODEL", "claude-haiku-4-5-20251001")
TOKENS = int(os.environ.get("GENAI_TOKENS", "512"))

# Backend: "anthropic" (default) or "ollama"
BACKEND = os.environ.get("GENAI_BACKEND", "anthropic")
OLLAMA_HOST = os.environ.get("GENAI_OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("GENAI_OLLAMA_MODEL", "llama3.2:1b")

MEMORY_PATH = Path(
    os.environ.get(
        "GENAI_MEMORY_PATH", str(Path.home() / ".local" / "share" / "amxmodx_genai" / "memory.db")
    )
)

# Directory scanned for plugin-registered skills (<plugin>__<skill>/SKILL.md)
SKILLS_PATH = Path(os.environ.get("GENAI_SKILLS_PATH", "./skills"))
