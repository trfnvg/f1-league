"""Small-instance defaults: one application copy, bounded concurrent I/O."""
import faulthandler
import os
import sys
import time


def positive_int(name, default, maximum):
    value = int(os.environ.get(name, str(default)))
    if not 1 <= value <= maximum:
        raise ValueError(f"{name} must be between 1 and {maximum}")
    return value


bind = f"0.0.0.0:{os.environ.get('PORT') or '8000'}"
workers = positive_int("GUNICORN_WORKERS", 1, 8)
worker_class = "gthread"
threads = positive_int("GUNICORN_THREADS", 4, 16)
timeout = 120
accesslog = "-"
errorlog = "-"
# Heartbeat metadata must not wait for a busy container overlay filesystem.
worker_tmp_dir = "/dev/shm" if os.path.isdir("/dev/shm") else None


def post_fork(server, worker):
    worker.fastlap_boot_started = time.monotonic()
    server.log.info("Fastlap worker initialization started (pid:%s)", worker.pid)
    # If Django initialization stalls, log code locations, never frame locals
    # (which could contain credentials). Cancel after successful initialization.
    faulthandler.dump_traceback_later(45, file=sys.stderr)


def post_worker_init(worker):
    faulthandler.cancel_dump_traceback_later()
    worker.log.info("Fastlap worker ready in %.2fs (pid:%s)",
                    time.monotonic() - worker.fastlap_boot_started, worker.pid)


def worker_abort(worker):
    worker.log.error("Fastlap worker timed out; thread locations follow (no locals)")
    faulthandler.dump_traceback(file=sys.stderr, all_threads=True)
