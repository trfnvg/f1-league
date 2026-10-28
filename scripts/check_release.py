"""Read-only post-deployment probe. Never sends login data or writes to the site."""
import argparse
import json
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def check(base_url):
    url = urlsplit(base_url)
    if (url.scheme not in {"http", "https"} or not url.netloc or url.username or url.password
            or url.path not in {"", "/"} or url.query or url.fragment):
        raise SystemExit("Provide only the site origin, e.g. https://fastlap.ru")
    for path in ("/health/live/", "/health/ready/"):
        request = Request(base_url.rstrip("/") + path, headers={"User-Agent": "Fastlap-release-check/1"})
        with urlopen(request, timeout=10) as response:
            assert response.status == 200 and urlsplit(response.url).path == path, "Unexpected response/redirect"
            assert json.loads(response.read(1024)) == {"status": "ok"}, "Unexpected health response"
            assert response.headers.get("X-Request-ID"), "Missing request ID"
        print(path + " OK")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("origin")
    check(parser.parse_args().origin)
