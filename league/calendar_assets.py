"""Local calendar photographs and their original attribution, never remote I/O."""
from functools import lru_cache
import json
from pathlib import Path


@lru_cache(maxsize=1)
def calendar_photos():
    return json.loads((Path(__file__).parent / "data" / "calendar_photos.json").read_text(encoding="utf-8"))
