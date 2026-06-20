#!/usr/bin/env python3
"""Verify MonsterUI vendor files match the installed package's HEADER_URLS.

Part of the quality gate: catches the case where 'uv upgrade monsterui'
was run but './dev sync-monsterui-vendor' was not.

Detection strategy: compare current HEADER_URLS against the lockfile written
by the last sync. URL drift (same key, different CDN path) means the installed
package changed but the vendor files were not re-downloaded.

Exit 0: lockfile present, URLs match, all files on disk.
Exit 1: lockfile absent, URL drift, or files missing — run sync-monsterui-vendor.
"""

import json
import sys
from pathlib import Path

try:
    from monsterui.core import HEADER_URLS
except ImportError:
    print("❌ monsterui not installed — run: uv sync")
    sys.exit(1)

VENDOR_DIR = Path(__file__).parent.parent / "static" / "vendor" / "monsterui"
LOCK_FILE = VENDOR_DIR / "monsterui.lock"


def main() -> int:
    if not LOCK_FILE.exists():
        print("❌ monsterui.lock missing — run: ./dev sync-monsterui-vendor")
        return 1

    locked: dict[str, str] = json.loads(LOCK_FILE.read_text())

    drifted = {name: url for name, url in HEADER_URLS.items() if locked.get(name) != url}
    if drifted:
        print(
            "❌ MonsterUI package upgraded without syncing vendor files — run: ./dev sync-monsterui-vendor"
        )
        for name, url in drifted.items():
            print(f"   {name}: locked={locked.get(name)!r}  current={url!r}")
        return 1

    missing = []
    for name, url in HEADER_URLS.items():
        ext = "css" if url.rsplit("?", 1)[0].endswith(".css") else "js"
        if not (VENDOR_DIR / f"{name}.{ext}").exists():
            missing.append(f"{name}.{ext}")

    if missing:
        print("❌ MonsterUI vendor files missing — run: ./dev sync-monsterui-vendor")
        for f in missing:
            print(f"   static/vendor/monsterui/{f}")
        return 1

    print(f"✅ MonsterUI vendor files present and in sync ({len(HEADER_URLS)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
