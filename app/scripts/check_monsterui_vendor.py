#!/usr/bin/env python3
"""Verify MonsterUI vendor files match the installed package's HEADER_URLS.

Part of the quality gate: catches the case where 'uv upgrade monsterui'
was run but './dev sync-monsterui-vendor' was not.

Exit 0: all files present. Exit 1: files missing (run sync-monsterui-vendor).
"""

import sys
from pathlib import Path

try:
    from monsterui.core import HEADER_URLS
except ImportError:
    print("❌ monsterui not installed — run: uv sync")
    sys.exit(1)

VENDOR_DIR = Path(__file__).parent.parent / "static" / "vendor" / "monsterui"


def main() -> int:
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

    print(f"✅ MonsterUI vendor files present ({len(HEADER_URLS)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
