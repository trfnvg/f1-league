"""Pack generated PNGs as pixel-identical lossless WebP (no resize/quantization)."""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("generated_dir", type=Path)
    parser.add_argument("--preview", type=Path, help="Optional contact sheet for visual review")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "docs/tetris-gp-art-manifest.json").read_text())
    destination = root / "league/static/league/images/tetris-gp"
    destination.mkdir(parents=True, exist_ok=True)
    sheet = Image.new("RGB", (1600, 1160), "#0b111c") if args.preview else None
    painter = ImageDraw.Draw(sheet) if sheet else None
    font = ImageFont.load_default(size=18)
    for index, venue in enumerate(manifest["venues"]):
        source = args.generated_dir / venue["source"]
        target = destination / f'{venue["id"]}-retro-v1.webp'
        with Image.open(source) as original:
            rgb = original.convert("RGB")
            rgb.save(target, "WEBP", lossless=True, method=6, exact=True)
            with Image.open(target) as packed:
                assert packed.size == rgb.size, f"Resized image: {target}"
                assert packed.convert("RGB").tobytes() == rgb.tobytes(), f"Lossy image: {target}"
            print(f"{venue['id']}: {rgb.width}x{rgb.height}, {target.stat().st_size:,} bytes; identical RGB")
            if sheet:
                x, y = (index % 4) * 400, (index // 4) * 386
                preview = rgb.copy()
                preview.thumbnail((392, 344), Image.Resampling.LANCZOS)
                sheet.paste(preview, (x + 4, y + 26))
                painter.text((x + 8, y + 3), venue["id"].upper(), font=font, fill="#dbe5ef")
    if sheet:
        sheet.save(args.preview)


if __name__ == "__main__":
    main()
