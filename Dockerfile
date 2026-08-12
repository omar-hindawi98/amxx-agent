FROM python:3.11-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml uv.lock* ./
RUN uv sync --extra ollama --dev

COPY src/ src/
COPY tests/ tests/

CMD ["uv", "run", "genai-sidecar"]
