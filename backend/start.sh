#!/bin/bash
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Seeding test accounts..."
python -m app.db.seed

echo "Starting uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
