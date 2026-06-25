# Single image for both control-plane tiers; the command selects the role:
#   web    -> python -m cleanroom.control.server.http   (streamable-HTTP MCP + OAuth)
#   worker -> python -m cleanroom.control.worker         (claims queued runs)
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install the package + server extra (mcp, uvicorn, starlette, pyjwt[crypto], httpx)
# and the base deps (psycopg, numpy). Copy only what the build needs first for caching.
COPY pyproject.toml ./
COPY cleanroom ./cleanroom
COPY sql ./sql
RUN pip install ".[server]"

# Run as non-root.
RUN useradd --create-home --uid 10001 app && chown -R app:app /app
USER app

EXPOSE 8000
ENV HOST=0.0.0.0 PORT=8000

# Default to the web tier; the worker service overrides `command`.
CMD ["python", "-m", "cleanroom.control.server.http"]
