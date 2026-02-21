#!/usr/bin/env sh
set -e

echo "=== PWD & FILES ==="
pwd
ls -la

echo "=== ENV ==="
echo "PORT=${PORT:-8000}"
echo "DEBUG=${DEBUG:-<unset>}"
echo "ALLOWED_HOSTS=${ALLOWED_HOSTS:-<unset>}"
echo "SECRET_KEY is set? -> ${SECRET_KEY:+yes}"

echo "=== DJANGO CHECK ==="
python manage.py check || true

echo "=== SKIP MIGRATIONS FOR NOW ==="
# python manage.py migrate --noinput
# python manage.py collectstatic --noinput

echo "=== START GUNICORN ==="
exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 120