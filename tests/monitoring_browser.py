"""Check real diagnostics JS in Chromium/WebKit; synthetic faults, no production."""
import argparse
import json
from pathlib import Path
from threading import Thread
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from playwright.sync_api import sync_playwright

SCRIPT = Path(__file__).resolve().parents[1] / "league/static/league/browser-errors.js"


def run(engine):
    reports = []
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path == "/static/league/browser-errors.js":
                body, mime = SCRIPT.read_bytes(), "text/javascript"
            else:
                config = json.dumps({"endpoint": "/diagnostics/browser-error/", "csrf": "synthetic-csrf"})
                body = (f'<!doctype html><html><head><script type="application/json" id="browser-monitoring-config">'
                        f'{config}</script><script src="/static/league/browser-errors.js"></script></head>'
                        '<body>Monitoring test</body></html>').encode()
                mime = "text/html"
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            requests.append((self.path, self.headers.get("X-CSRFToken")))
            reports.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(204)
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as pw:
            browser = getattr(pw, engine).launch()
            for width in (390, 1440):
                reports.clear()
                requests.clear()
                page = browser.new_page(viewport={"width": width, "height": 900})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{server.server_port}/?token=private", wait_until="networkidle")
                page.evaluate("""() => {
                  function fault(source, line = 42) {
                    dispatchEvent(new ErrorEvent('error', {
                      filename: source, lineno: line, colno: 3,
                      message: 'SECRET_PASSWORD', error: new TypeError('SECRET_EMAIL')
                    }));
                  }
                  fault('https://extension.invalid/private.js');
                  fault(location.origin + '/accounts/reset/private.js');
                  fault(location.origin + '/static/league/doodle-jump.js?token=SECRET_TOKEN');
                  fault(location.origin + '/static/league/doodle-jump.js?token=SECRET_TOKEN');
                }""")
                page.wait_for_function("() => true")
                # A real rejected Promise exercises browser-specific stack formats.
                page.route("**/static/league/synthetic-fault.js", lambda route: route.fulfill(
                    content_type="text/javascript", body="Promise.reject(new RangeError('SECRET_REJECTION'));"))
                page.evaluate("""() => {
                  const script = document.createElement('script');
                  script.src = '/static/league/synthetic-fault.js'; document.head.append(script);
                }""")
                for _ in range(100):
                    if len(reports) >= 2:
                        break
                    page.wait_for_timeout(20)
                assert len(reports) == 2, reports
                assert reports[1]["kind"] == "unhandledrejection", reports
                page.evaluate("""() => {
                  for (let i=0; i<10; i++) dispatchEvent(new ErrorEvent('error', {
                    filename: location.origin + '/static/league/arcade.js', lineno: i+1,
                    error: new Error('SECRET')
                  }));
                }""")
                for _ in range(100):
                    if len(reports) >= 3:
                        break
                    page.wait_for_timeout(20)
                assert len(reports) == 3, reports
                assert all(report["viewport"] == ("mobile" if width == 390 else "desktop") for report in reports)
                assert all(set(report) == {"asset", "line", "column", "kind", "error_type", "viewport"} for report in reports)
                assert "SECRET" not in json.dumps(reports)
                assert requests == [("/diagnostics/browser-error/", "synthetic-csrf")] * 3
                assert all("SECRET_REJECTION" in error for error in errors), errors
                # Deliberately failed reporting transport must not start a loop.
                page.close()
                page = browser.new_page()
                page.route("**/diagnostics/browser-error/", lambda route: route.abort())
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{server.server_port}/", wait_until="networkidle")
                page.evaluate("""() => dispatchEvent(new ErrorEvent('error', {
                  filename: location.origin + '/static/league/arcade.js', lineno: 1
                }))""")
                page.wait_for_timeout(150)
                assert not errors, errors
                page.close()
            browser.close()
        print(f"Monitoring runtime OK ({engine}): safe fields, deduplication, 3-report cap, rejection stacks, offline transport.")
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", choices=["chromium", "webkit"], default="chromium")
    run(parser.parse_args().browser)
