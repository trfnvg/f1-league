#!/usr/bin/env sh
set -e

export PYTHONUNBUFFERED=1
startup_stage='Python runtime'
trap 'startup_status=$?; if [ "$startup_status" -ne 0 ]; then printf "Fastlap startup failed: stage=%s exit_code=%s\n" "$startup_stage" "$startup_status" >&2; fi' 0

printf '%s\n' 'Starting Fastlap: Python runtime'
python --version

# Roll back the newly introduced strict audit gate. Keep the audit as a
# separate operator/CI command; do not make legacy key strength an outage.
# Still refuse an implicit SQLite DB after the repository DB was removed.
startup_stage='database configuration'
case "${DATABASE_URL:-}" in
    *[![:space:]]*) ;;
    *) printf '%s\n' 'DATABASE_URL is missing; refusing to create an empty local database.' >&2; exit 1 ;;
esac

startup_stage='database migrations'
printf '%s\n' 'Applying database migrations'
python manage.py migrate --noinput
startup_stage='static assets'
printf '%s\n' 'Collecting static assets'
python manage.py collectstatic --noinput

startup_stage='Gunicorn'
printf 'Starting Gunicorn on 0.0.0.0:%s\n' "${PORT:-8000}"
exec python -m gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-8000}" --workers 2 --timeout 120 --access-logfile - --access-logformat 'request_id=%({x-request-id}o)s method=%(m)s status=%(s)s duration=%(L)s' --error-logfile - --capture-output
