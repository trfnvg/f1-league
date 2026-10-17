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

If a deploy fails, inspect the **failed deployment's** build and runtime logs,
not the logs of the older still-running release. A Git push confirms repository
publication only; it does not confirm that Render promoted the new release.

Do not change `DATABASE_URL` or storage credentials to retry a deployment.
