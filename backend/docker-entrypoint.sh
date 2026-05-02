#!/bin/sh
set -e
cd /app
python3 -m alembic upgrade head
exec "$@"
