"""Build web-sized copies of approved slot art; originals remain untouched.

Developer-only tool: run with a Python environment containing Pillow.
"""
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1] / "league/static/league/images/vegas"
ASSETS = {
    "meme-symbols-v4": (1200, 1200),
    "pepper-russell-v1": (512, 768),
    "ferrari-tractor-v1": (512, 512),
    "strip-v3": (1440, 960),
    "strip-mobile-v3": (900, 1350),
}

if __name__ == "__main__":
    before = after = 0
    for name, size in ASSETS.items():
        source, target = ROOT / f"{name}.png", ROOT / f"{name}-web.webp"
        with Image.open(source) as image:
            image.thumbnail(size, Image.Resampling.LANCZOS)
            image.save(target, "WEBP", quality=88, method=6)
        before += source.stat().st_size
        after += target.stat().st_size
        print(f"{target.name}: {target.stat().st_size:,} bytes")
    print(f"Total: {before:,} -> {after:,} bytes ({100*(1-after/before):.1f}% smaller)")
