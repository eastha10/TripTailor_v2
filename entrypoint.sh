#!/bin/sh
set -e

if [ -z "$PORT" ]; then
  echo "PORT is required. Cloud Run provides this automatically."
  exit 1
fi

python manage.py migrate --noinput

# Cloud Run: 1 worker + threads. Timeout 0 lets Cloud Run own request deadlines.
exec gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT}" \
  --workers "${GUNICORN_WORKERS:-1}" \
  --threads "${GUNICORN_THREADS:-8}" \
  --timeout "${GUNICORN_TIMEOUT:-0}" \
  --access-logfile - \
  --error-logfile -
