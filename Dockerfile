FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends tzdata && \
    rm -rf /var/lib/apt/lists/*

# Pin the uv version (matches the local dev environment).
COPY --from=ghcr.io/astral-sh/uv:0.12.11 /uv /usr/local/bin/uv

# Run the app as a non-root user.
RUN useradd --create-home --uid 1000 appuser

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen

COPY --chown=appuser:appuser . .

USER appuser

CMD ["sh", "-c", "uv run --no-sync alembic upgrade head && exec /app/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000"]
