#!/usr/bin/env bash
# Development server runner
set -e

echo "Starting TechScape AI backend..."

# Load .env if present
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload \
    --log-level info
