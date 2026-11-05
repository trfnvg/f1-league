from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import runpy
import socket
import subprocess
import sys
import time
from unittest.mock import patch
from urllib.request import ProxyHandler, build_opener

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/gunicorn.conf.py"


class GunicornConfigTests(SimpleTestCase):
    def test_small_server_defaults_and_explicit_overrides(self):
        with patch.dict(os.environ, {}, clear=True):
            config = runpy.run_path(str(CONFIG))
        self.assertEqual((config["workers"], config["threads"], config["worker_class"]),
                         (1, 4, "gthread"))
        self.assertEqual(config["bind"], "0.0.0.0:8000")
        with patch.dict(os.environ, {"GUNICORN_WORKERS": "2", "GUNICORN_THREADS": "3",
                                     "PORT": "8012"}, clear=True):
            config = runpy.run_path(str(CONFIG))
        self.assertEqual((config["workers"], config["threads"]), (2, 3))
        self.assertEqual(config["bind"], "0.0.0.0:8012")

    def test_invalid_resource_limits_fail_clearly(self):
        for name, value in (("GUNICORN_WORKERS", "0"), ("GUNICORN_THREADS", "100")):
            with self.subTest(name=name), patch.dict(os.environ, {name: value}, clear=True):
                with self.assertRaisesRegex(ValueError, name):
                    runpy.run_path(str(CONFIG))

    def test_health_responds_while_two_requests_wait_for_io(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = os.environ.copy()
        env.update(GUNICORN_WORKERS="1", GUNICORN_THREADS="4")
        process = subprocess.Popen([
            sys.executable, "-m", "gunicorn", "--config", str(CONFIG),
            "--bind", f"127.0.0.1:{port}", "--pythonpath", str(ROOT / "tests"),
            "gunicorn_probe_app:application",
        ], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        def get(path):
            with build_opener(ProxyHandler({})).open(
                    f"http://127.0.0.1:{port}{path}", timeout=5) as response:
                return response.read()

        try:
            deadline = time.monotonic() + 10
            while True:
                try:
                    get("/health/live/")
                    break
                except OSError:
                    if process.poll() is not None or time.monotonic() >= deadline:
                        self.fail("Synthetic Gunicorn server did not start")
                    time.sleep(0.05)
            with ThreadPoolExecutor(max_workers=2) as pool:
                slow = [pool.submit(get, "/slow/") for _ in range(2)]
                deadline = time.monotonic() + 2
                while get("/entered/") != b"2":
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(0.02)
                before = time.monotonic()
                self.assertEqual(get("/health/live/"), b"ok")
                self.assertLess(time.monotonic() - before, 1)
                self.assertTrue(all(not task.done() for task in slow))
                for task in slow:
                    self.assertEqual(task.result(timeout=5), b"ok")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
