"""Boot the real start.sh/Gunicorn against a fresh, temporary database only.

No Timeweb credentials, Docker daemon, live users or production database needed.
Usage: python tests/startup_smoke.py
"""
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix="fastlap-startup-smoke-") as directory:
        path = Path(directory)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        # Deliberately configure public domains only, just like Timeweb env.
        # Loopback probes must still work; arbitrary public Hosts must not.
        env = {"PATH": str(Path(sys.executable).parent) + os.pathsep + os.defpath,
            "DATABASE_URL": f"sqlite:///{path / 'isolated.sqlite3'}", "DEBUG": "False",
            "SECRET_KEY": secrets.token_urlsafe(50), "ALLOWED_HOSTS": "fastlap.ru,www.fastlap.ru",
            "PORT": str(port), "USE_S3": "False", "SENTRY_DSN": "",
            "MEDIA_ROOT": str(path / "media"), "EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend"}
        log_path = path / "startup.log"
        with log_path.open("w+") as log:
            process = subprocess.Popen(["sh", str(ROOT / "start.sh")], cwd=ROOT,
                env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise AssertionError("Startup exited before serving HTTP")
                    try:
                        with urlopen(f"http://127.0.0.1:{port}/health/live/", timeout=1) as response:
                            if response.status == 200:
                                break
                    except (OSError, URLError):
                        time.sleep(.15)
                else:
                    raise AssertionError("Startup didn't become healthy")
                for host in ("localhost", "127.0.0.1", "fastlap.ru"):
                    for route in ("/health/live/", "/health/ready/", "/", "/calendar/"):
                        request = Request(f"http://127.0.0.1:{port}{route}", headers={"Host": host})
                        with urlopen(request, timeout=5) as response:
                            assert response.status == 200, (host, route, response.status)
                            assert response.headers.get("X-Request-ID"), (host, route)
                try:
                    urlopen(Request(f"http://127.0.0.1:{port}/health/live/",
                        headers={"Host": "untrusted.invalid"}), timeout=5)
                except HTTPError as error:
                    assert error.code == 400, error.code
                else:
                    raise AssertionError("Unexpected Host was accepted")
                print("Startup smoke OK: real migrations, collectstatic, Gunicorn, loopback/public hosts, home/calendar and both health routes.")
            except BaseException:
                log.flush()
                print("Synthetic startup log (no live credentials):", file=sys.stderr)
                print(log_path.read_text()[-12000:], file=sys.stderr)
                raise
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=5)


if __name__ == "__main__":
    main()
