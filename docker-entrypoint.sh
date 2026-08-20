#!/usr/bin/env bash
set -e
echo "Running migrations..."
alembic upgrade head
echo "Seeding (idempotent)..."
python scripts/seed.py || true
echo "Starting server..."
exec cascade
