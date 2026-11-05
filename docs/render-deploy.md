# Render deployment

The native Python runtime is pinned to the latest Python 3.13 patch in
`.python-version`. Render's `PYTHON_VERSION` service environment variable takes
precedence; remove it or set it to a compatible released version if overriding
the file. Django 6 requires Python 3.12 or newer. The Docker runtime continues
to use the supported Python 3.12 image in `Dockerfile`.

For a native Render service, use:

- Build command: `python -m pip install -r requirements.txt`
- Start command: `./start.sh`
- Deploy branch: `main`

The executable startup script applies migrations, collects hashed static assets,
and starts Gunicorn on Render's `PORT`. It logs each startup phase and sends
Gunicorn access/error logs to the service log stream. An error stops startup
before serving a partially initialized release.

Gunicorn configuration is in `config/gunicorn.conf.py`. On a one-core instance,
the defaults are one `gthread` worker and four request threads: Django is loaded
once, and two slow I/O requests do not occupy every request slot. Threads do not
make CPU-bound Python code faster and cannot guarantee health checks under full
saturation. `GUNICORN_WORKERS` (1–8) and `GUNICORN_THREADS` (1–16) can override these
defaults after measuring CPU, RAM and database connection capacity. No new
environment variables are required for deployment.

Worker heartbeat files use `/dev/shm` when available to avoid overlay filesystem
stalls. Logs include worker initialization/ready messages with elapsed time. If
initialization takes over 45 seconds, a stack dump identifies code locations
without printing frame locals or environment variables. A worker timeout also
prints thread locations. These diagnostics distinguish import/startup stalls
from slow requests; a SIGKILL message alone does not prove an out-of-memory kill.

If a deploy fails, inspect the **failed deployment's** build and runtime logs,
not the logs of the older still-running release. A Git push confirms repository
publication only; it does not confirm that Render promoted the new release.

Do not change `DATABASE_URL` or storage credentials to retry a deployment.
