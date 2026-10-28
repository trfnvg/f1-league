"""Download explicitly selected, freely licensed Commons photos; emit credits JSON.

Development-only: python tools/fetch_calendar_photos.py
Binary assets are downloaded unchanged from Commons (1280px thumbnails).
Review stdout before adding it as league/data/calendar_photos.json.
No network request is ever made by the calendar page or migrations.
"""
import hashlib
import argparse
import html
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
HEADERS = {"User-Agent": "FastlapCalendar/1.0 (https://fastlap.ru; photo attribution)"}


def fetch(url):
    with urlopen(Request(url, headers=HEADERS), timeout=40) as response:
        return response.read()


def main(reuse_existing=False):
    sources = json.loads((Path(__file__).with_name("calendar_photo_sources.json")).read_text())
    manifest = {}
    pairs = list(sources.items())
    for start in range(0, len(pairs), 8):
        batch = pairs[start:start + 8]
        query = urlencode({"action": "query", "format": "json", "prop": "imageinfo",
            "titles": "|".join("File:" + source[0] for _, source in batch),
            "iiprop": "url|extmetadata", "iiurlwidth": 1280,
            "iiextmetadatafilter": "Artist|LicenseShortName|LicenseUrl"})
        data = json.loads(fetch("https://commons.wikimedia.org/w/api.php?" + query))
        pages = {page["title"]: page for page in data["query"]["pages"].values()}
        for key, (title, alt) in batch:
            info = pages["File:" + title]["imageinfo"][0]
            metadata = info["extmetadata"]
            license_name = metadata["LicenseShortName"]["value"]
            if not re.fullmatch(r"CC BY(?:-SA)? [\d.]+|CC0|Public domain", license_name):
                raise ValueError(f"Photo license requires manual review: {key}: {license_name}")
            url = info.get("thumburl", info["url"]).split("?")[0]
            if urlsplit(url).hostname not in ("upload.wikimedia.org", "thumb.wikimedia.org"):
                raise ValueError("Unexpected image host")
            relative = f"league/images/calendar/{key}.jpg"
            target = ROOT / "league" / "static" / relative
            photo = target.read_bytes() if reuse_existing and target.exists() else fetch(url)
            if not photo.startswith(b"\xff\xd8"):
                raise ValueError(f"Not a JPEG: {key}")
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and target.read_bytes() != photo:
                raise ValueError(f"Refusing to overwrite changed photo: {key}")
            target.write_bytes(photo)
            manifest[key] = {"path": relative, "alt": alt,
                "author": html.unescape(re.sub(r"<[^>]+>", "", metadata["Artist"]["value"])).strip(),
                "license": license_name, "license_url": metadata["LicenseUrl"]["value"],
                "source_url": info["descriptionurl"], "download_url": url,
                "sha256": hashlib.sha256(photo).hexdigest()}
            print(f"Downloaded {key}: {len(photo)} bytes", file=sys.stderr, flush=True)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reuse-existing", action="store_true",
        help="Read previously downloaded files and rebuild credits without re-downloading them.")
    main(parser.parse_args().reuse_existing)
