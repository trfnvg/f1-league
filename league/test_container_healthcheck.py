"""Exercise the actual probe subprocess against local synthetic HTTP servers."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading

from django.test import SimpleTestCase


PROBE = Path(__file__).resolve().parents[1] / "config/container_healthcheck.py"


class ContainerHealthcheckTests(SimpleTestCase):
    def run_probe(self, port):
        return subprocess.run([sys.executable, str(PROBE)], env={
            "PORT": str(port),
            # Deliberately broken proxy: the container-local probe must ignore it.
            "http_proxy": "http://127.0.0.1:1", "HTTP_PROXY": "http://127.0.0.1:1",
            "no_proxy": "", "NO_PROXY": "",
        }, capture_output=True, text=True, timeout=6)

    def test_live_http_status_and_no_redirect_or_proxy(self):
        for status in (200, 204, 302, 400, 404, 500, 503):
            with self.subTest(status=status):
                received = []

                class Handler(BaseHTTPRequestHandler):
                    def do_GET(self):
                        received.append((self.path, self.headers.get("Host")))
                        self.send_response(status)
                        self.send_header("Location", "/other/")
                        self.end_headers()

                    def log_message(self, *args):
                        pass

                server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    result = self.run_probe(server.server_port)
                    self.assertEqual(result.returncode, 0 if status < 300 else 1,
                                     result.stdout + result.stderr)
                    self.assertEqual(received, [("/health/live/", "localhost")])
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)

    def test_closed_port_is_unhealthy(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            # Bound but not listening: connections are refused without a race.
            result = self.run_probe(sock.getsockname()[1])
        self.assertEqual(result.returncode, 1)
        self.assertIn("container_healthcheck:", result.stderr)

    def test_invalid_port_is_unhealthy(self):
        for port in ("invalid", "-1", "0", "65536"):
            with self.subTest(port=port):
                result = self.run_probe(port)
                self.assertEqual(result.returncode, 1)
                self.assertIn("invalid PORT", result.stderr)
