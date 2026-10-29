#!/usr/bin/env sh
set -e

export PYTHONUNBUFFERED=1
# Never replace the live PostgreSQL database with an empty local SQLite file.
case "${DATABASE_URL:-}" in
    *[![:space:]]*) ;;
    *) printf '%s\n' 'DATABASE_URL is missing; startup stopped without changing data.' >&2; exit 1 ;;
esac

printf '%s\n' 'Starting Fastlap: Python runtime'
python --version
printf '%s\n' 'Applying database migrations'
python manage.py migrate --noinput
printf '%s\n' 'Collecting static assets'
python manage.py collectstatic --noinput

printf '%s\n' 'Starting Gunicorn'
exec python -m gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-8000}" --workers 2 --timeout 120 --access-logfile - --error-logfile -
