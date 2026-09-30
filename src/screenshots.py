"""Capture README screenshots of the dashboard with headless Chrome or Edge.

Optional step, not part of run_all.py. Needs Chrome or Edge installed and Pillow.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageChops

from config import DOCS_DIR

BROWSERS = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path("/usr/bin/google-chrome"),
    Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
]
# output name -> (sections to show, window height before trimming, keep at most this many pixels)
SHOTS = {
    "dashboard_benchmark.png": ("head,benchmark", 1500, 1130),
    "dashboard_event_study.png": ("events", 1700, 1700),
    "dashboard_themes.png": ("themes", 1500, 760),
}
WIDTH = 1200


def trim_bottom(img: Image.Image) -> Image.Image:
    """Cut the empty page background below the content."""
    background = Image.new(img.mode, img.size, img.getpixel((2, img.height - 2)))
    box = ImageChops.difference(img, background).getbbox()
    return img.crop((0, 0, img.width, min(img.height, box[3] + 24))) if box else img


def main() -> int:
    browser = next((b for b in BROWSERS if b.exists()), None)
    if browser is None:
        print("No Chrome or Edge found. Screenshots were not taken.")
        return 1
    out_dir = DOCS_DIR / "img"
    out_dir.mkdir(parents=True, exist_ok=True)
    page = (DOCS_DIR / "index.html").resolve().as_uri()
    for name, (sections, height, keep) in SHOTS.items():
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "shot.png"
            subprocess.run(
                [str(browser), "--headless=new", "--disable-gpu", "--hide-scrollbars",
                 "--force-prefers-color-scheme=light", f"--window-size={WIDTH},{height}",
                 "--virtual-time-budget=8000", f"--screenshot={raw}", f"{page}#only={sections}"],
                check=True, capture_output=True, timeout=120)
            img = trim_bottom(Image.open(raw).convert("RGB"))
            img.crop((0, 0, img.width, min(img.height, keep))).save(out_dir / name, optimize=True)
        print(f"wrote docs/img/{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
