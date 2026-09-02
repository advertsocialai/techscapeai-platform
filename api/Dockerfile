# Container image for the FastAPI backend. Build context is THIS directory.
#
#   docker build -t techscapeai-api ./api
#
# The repo root also carries a Dockerfile whose COPY/CMD paths ("requirements.txt",
# "app.main:app") only resolve when the context is ./api -- there is no app/ at the
# repo root, so building it from the root produces an image that fails at startup.
# This file lives where its paths actually work, so a platform pointed at
# Root Directory = api (Railway, Fly, Cloud Run) builds correctly with no extra config.
#
# Dependencies come from requirements.txt here, NOT pyproject.toml -- pip reads the
# former, Vercel's uv build reads the latter. api/tests/test_dependency_sync.py keeps
# the two from drifting; that drift is what silently shipped an API with no fastapi.
# fastembed IS installed here (wiki semantic search), unlike the serverless bundle.

FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first so the dependency layer caches across source edits.
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
USER appuser

# PORT is injected by the platform (Railway, Cloud Run); 8000 for a bare `docker run`.
ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -fsS "http://localhost:${PORT}/api/health" || exit 1

# Shell form so ${PORT} expands at runtime. Unlike the serverless deployment this
# is a long-lived process, so it can serve the /ws call-feed routes and run the
# webhook worker (ENABLE_WEBHOOK_WORKER=1) -- neither of which works on Vercel.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 2
