"""Synthetic slow I/O, not connected to Django, the database or S3."""
import threading
import time

lock = threading.Lock()
entered = 0


def application(environ, start_response):
    global entered
    path = environ.get("PATH_INFO")
    if path == "/slow/":
        with lock:
            entered += 1
        time.sleep(3)
    with lock:
        body = str(entered).encode() if path == "/entered/" else b"ok"
    start_response("200 OK", [("Content-Type", "text/plain"),
                              ("Content-Length", str(len(body)))])
    return [body]
