#!/bin/sh
set -e

if [ -z "$PORT" ]; then
  echo "PORT is required. Cloud Run provides this automatically."
  exit 1
fi

python manage.py migrate --noinput

exec gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT}" \
  --workers "${GUNICORN_WORKERS:-2}" \
  --timeout "${GUNICORN_TIMEOUT:-60}" \
  --access-logfile - \
  --error-logfile -
