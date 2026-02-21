#!/usr/bin/env sh
set -eux

echo "=== ENV CHECK ==="
python -V
pwd
ls -la

echo "SECRET_KEY set? -> ${SECRET_KEY:+yes}"
echo "DEBUG -> ${DEBUG:-<unset>}"
echo "ALLOWED_HOSTS -> ${ALLOWED_HOSTS:-<unset>}"

echo "=== DJANGO CHECK ==="
python manage.py check

echo "=== MIGRATE ==="
python manage.py migrate --noinput

echo "=== COLLECTSTATIC ==="
python manage.py collectstatic --noinput

echo "=== START GUNICORN ==="
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2 --timeout 120