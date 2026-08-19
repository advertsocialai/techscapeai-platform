#!/usr/bin/env bash
# Development server runner
set -e

echo "Starting TechScape AI backend..."


uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload \
    --log-level info
