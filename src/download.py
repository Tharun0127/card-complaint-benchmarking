"""Download the CFPB narratives archive files that cover 2023 onward.

Files are saved to data/raw/ and skipped if already present with the expected size.
The CFPB CDN returns 403 for requests without an Accept header, so one is always sent.
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

from config import ARCHIVE_BASE_URL, ARCHIVE_FILES, RAW_DIR

CHUNK = 1 << 20
HEADERS = {"User-Agent": "card-complaint-benchmarking/1.0", "Accept": "*/*"}


def remote_size(url: str) -> int | None:
    req = urllib.request.Request(url, headers={**HEADERS, "Range": "bytes=0-0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        content_range = resp.headers.get("Content-Range", "")
    if "/" in content_range:
        return int(content_range.rsplit("/", 1)[1])
    return None


def download_one(name: str, dest_dir: Path = RAW_DIR) -> Path:
    url = f"{ARCHIVE_BASE_URL}/{name}"
    dest = dest_dir / name
    expected = remote_size(url)
    if dest.exists() and expected is not None and dest.stat().st_size == expected:
        print(f"skip  {name} ({expected / 1e6:.0f} MB, already downloaded)")
        return dest

    tmp = dest.with_suffix(".part")
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as out:
        while chunk := resp.read(CHUNK):
            out.write(chunk)
    if expected is not None and tmp.stat().st_size != expected:
        raise IOError(f"{name}: got {tmp.stat().st_size} bytes, expected {expected}")
    tmp.replace(dest)
    print(f"done  {name} ({dest.stat().st_size / 1e6:.0f} MB)")
    return dest


def main() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for name in ARCHIVE_FILES:
        download_one(name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
