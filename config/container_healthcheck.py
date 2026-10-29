"""Container-local HTTP probe; no Django import, DB, curl, DNS or proxy needed."""
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None


def main():
    try:
        port = int(os.environ.get("PORT") or "8000")
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        print("container_healthcheck: invalid PORT", file=sys.stderr)
        return 1
    request = Request(f"http://127.0.0.1:{port}/health/live/",
                      headers={"Host": "localhost", "User-Agent": "Fastlap-container-health/1"})
    opener = build_opener(ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=3) as response:
            if not 200 <= response.status < 300:
                print(f"container_healthcheck: HTTP {response.status}", file=sys.stderr)
                return 1
    except HTTPError as error:
        print(f"container_healthcheck: HTTP {error.code}", file=sys.stderr)
        return 1
    except (OSError, URLError) as error:
        # Avoid printing environment/proxy values or any response body.
        print(f"container_healthcheck: {type(error).__name__}", file=sys.stderr)
        return 1
    print("container_healthcheck: HTTP 2xx")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
