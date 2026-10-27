"""Render the vector brand mark to browser and Apple icon fallbacks.

Development only: requires Playwright (Chromium) and Pillow.
Run from any directory: python scripts/build_brand_icons.py
"""
import io
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright


def build():
    root = Path(__file__).resolve().parents[1] / "league/static/league"
    svg = (root / "favicon.svg").read_text()
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 256, "height": 256}, device_scale_factor=1)
        page.set_content('<style>html,body{margin:0;background:transparent}svg{display:block;width:256px;height:256px}</style>' + svg)
        pixels = page.screenshot(omit_background=True)
        browser.close()
    with Image.open(io.BytesIO(pixels)) as source:
        source.save(root / "favicon.ico", format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])
        for size in (32, 48):
            source.resize((size, size), Image.Resampling.LANCZOS).save(root / f"favicon-{size}.png", optimize=True)
        source.resize((180, 180), Image.Resampling.LANCZOS).save(root / "apple-touch-icon.png", optimize=True)


if __name__ == "__main__":
    build()
