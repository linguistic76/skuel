#!/usr/bin/env python3
"""Download MonsterUI vendor files from CDN to static/vendor/monsterui/.

Run after 'uv upgrade monsterui' to keep committed vendor files in sync
with the installed package's HEADER_URLS. Then commit the updated files.

Usage:
    ./dev sync-monsterui-vendor
    uv run python scripts/sync_monsterui_vendor.py
"""

import json
import sys
from pathlib import Path

try:
    import httpx
except ImportError:
    print("httpx not installed — run: uv sync")
    sys.exit(1)

try:
    from monsterui.core import HEADER_URLS
except ImportError:
    print("monsterui not installed — run: uv sync")
    sys.exit(1)

VENDOR_DIR = Path(__file__).parent.parent / "static" / "vendor" / "monsterui"
LOCK_FILE = VENDOR_DIR / "monsterui.lock"


def main() -> int:
    VENDOR_DIR.mkdir(exist_ok=True)

    print(f"Syncing {len(HEADER_URLS)} MonsterUI vendor files...")

    for name, url in HEADER_URLS.items():
        ext = "css" if url.rsplit("?", 1)[0].endswith(".css") else "js"
        fname = VENDOR_DIR / f"{name}.{ext}"
        print(f"  {fname.name}")
        try:
            response = httpx.get(url, follow_redirects=True, timeout=30)
            response.raise_for_status()
            fname.write_bytes(response.content)
        except httpx.HTTPError as e:
            print(f"  ❌ Failed: {e}")
            return 1

    LOCK_FILE.write_text(json.dumps(HEADER_URLS, indent=2) + "\n")
    print(f"\n✅ {len(HEADER_URLS)} files synced + monsterui.lock written")
    print("Commit with:")
    print(
        "  git add app/static/vendor/monsterui/ && git commit -m 'chore: sync monsterui vendor files'"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
