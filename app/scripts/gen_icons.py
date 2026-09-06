#!/usr/bin/env python3
"""Generate ui/components/_icon_data.py — inline-SVG markup for the lucide icons SKUEL uses.

WHY: SKUEL renders icons server-side as inline ``<svg>`` (see ``ui/components/icon.py``)
instead of shipping lucide's runtime ``createIcons()`` DOM scanner. This script harvests
the icon geometry for the names the codebase uses and writes them to a committed Python
module, so the 410 KB lucide JS bundle never reaches the browser.

SOURCE: the vendored UMD bundle ``static/vendor/lucide/lucide.<ver>.min.js`` — the exact
pinned version already in the repo. Its ``icons`` export maps PascalCase names to icon
nodes (``[["path", {"d": "..."}], ...]``). We read it via node (no network, no new dep).
To switch to lucide-static later, change ``load_icon_nodes()`` to read its ``icons/*.svg``.

USAGE:
    uv run python scripts/gen_icons.py          # regenerate after adding/removing icons

HARVEST STRATEGY: with the lucide runtime gone, any name reaching ``Icon()`` must be in
the registry — whether passed directly (``Icon("check")``), via a config field
(``icon="sun"``), or through a wrapper helper (``_icon_ghost_btn("thumbs-up")``). Rather
than enumerate every call shape (whack-a-mole), we include every quoted string literal in
our own source that is a real lucide icon name. See ``scan_used_names`` for the trade-off.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
BUNDLE = next((APP_ROOT / "static/vendor/lucide").glob("lucide.*.min.js"))
OUT = APP_ROOT / "ui/components/_icon_data.py"

# Fallbacks Icon() references directly — always include even if no call site scans them.
SAFELIST = {"help-circle", "circle"}

# Where our own source lives. NOT static/vendor/ — minified bundles are full of
# coincidental single-letter/word matches.
SCAN_GLOBS = ("ui/**/*.py", "adapters/**/*.py", "static/js/**/*.js")

# Any quoted kebab-case literal (e.g. "check", 'chevron-down', "more-horizontal").
LITERAL_RX = re.compile(r"""["']([a-z][a-z0-9]*(?:-[a-z0-9]+)*)["']""")

# Icon-intent string literals — positions where a literal can ONLY be meant as an icon
# name, so a value that is not a real lucide icon is always a typo. Unlike the permissive
# whole-source scan (which keeps only literals that *happen* to be real lucide names), these
# shapes carry intent, so the generator can fail the build instead of silently dropping the
# name and rendering a help-circle fallback at runtime. Four shapes:
#   Icon("name")            the renderer chokepoint
#   icon="name"             config field / keyword argument (DomainConfig, card specs, …)
#   "icon": "name"          dict-entry config (section specs → form_generator → Icon(icon_name))
#   _icon_ghost_btn("name") underscore-prefixed _icon_* wrapper helpers that forward to Icon()
_KEBAB = r"""["']([a-z][a-z0-9]*(?:-[a-z0-9]+)*)["']"""
ICON_INTENT_RX = re.compile(
    rf"""(?:\bIcon\(|\bicon\s*=|["']icon["']\s*:|\b_icon_\w*\()\s*{_KEBAB}"""
)


def _pascal(name: str) -> str:
    """kebab-case -> PascalCase, matching lucide's icons-object keys ('check-circle-2' -> 'CheckCircle2')."""
    return "".join(part[:1].upper() + part[1:] for part in name.split("-"))


def scan_used_names(valid_keys: set[str]) -> set[str]:
    """Every quoted string literal in our source that is a real lucide icon name.

    Harvest-by-validity rather than pattern-matching specific call shapes: with the
    lucide runtime removed, any name reaching Icon() — directly, via a config field
    (icon="..."), or through a wrapper helper (_icon_ghost_btn("thumbs-up")) — must
    be in the registry. Matching real lucide names covers all of those paths at once
    and is robust to new call patterns. Cost: a handful of words that happen to be
    icon names (e.g. "code", "save") get included unused — harmless in a generated file.
    """
    names: set[str] = set(SAFELIST)
    for glob in SCAN_GLOBS:
        for path in APP_ROOT.glob(glob):
            if path.is_file():
                for lit in LITERAL_RX.findall(path.read_text(encoding="utf-8")):
                    if _pascal(lit) in valid_keys:
                        names.add(lit)
    return names


def icon_name_literals() -> dict[str, str]:
    """Map every icon-intent string literal to the source file it appears in.

    Covers the four shapes in ``ICON_INTENT_RX`` — ``Icon("name")``, ``icon="name"``,
    ``"icon": "name"`` and ``_icon_*("name")`` — where a literal can only be meant as an icon name. Dynamic
    forms (``Icon(name)``, ``icon=variable``) are skipped: they can't be validated
    statically. These literals are where a typo slips through unnoticed — the generator
    drops an unknown name, so the icon renders a silent help-circle fallback with no build
    error. Consumed by the build-time check in ``main()`` and by the icon-name unit test,
    which asserts each resolves to a registry key.
    """
    found: dict[str, str] = {}
    for glob in SCAN_GLOBS:
        for path in APP_ROOT.glob(glob):
            if path.is_file():
                for name in ICON_INTENT_RX.findall(path.read_text(encoding="utf-8")):
                    found.setdefault(name, str(path.relative_to(APP_ROOT)))
    return found


def load_icon_nodes() -> dict[str, list[list[object]]]:
    """Read every icon node from the vendored UMD bundle via node (PascalCase keys)."""
    script = (
        f"const l=require({json.dumps(str(BUNDLE))});process.stdout.write(JSON.stringify(l.icons));"
    )
    raw = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout
    return json.loads(raw)


def node_to_markup(node: list[list[object]]) -> str:
    """[['path', {'d': '...'}], ...] -> '<path d="..."/><circle .../>' (leaf children only)."""
    parts: list[str] = []
    for child in node:
        if len(child) > 2:
            raise ValueError(f"nested icon child not supported: {child!r}")
        tag = child[0]
        attrs: dict[str, str] = child[1] if len(child) > 1 else {}  # type: ignore[assignment]
        attr_str = "".join(
            f' {k}="{str(v).replace("&", "&amp;").replace(chr(34), "&quot;")}"'
            for k, v in attrs.items()
        )
        parts.append(f"<{tag}{attr_str}/>")
    return "".join(parts)


def main() -> int:
    all_nodes = load_icon_nodes()
    valid_keys = set(all_nodes)

    # Fail loudly on an icon-intent literal (Icon("…"), icon="…", _icon_*("…")) whose name
    # is not a real lucide icon — otherwise scan_used_names drops it and it renders a silent
    # help-circle fallback.
    unknown = {
        name: src for name, src in icon_name_literals().items() if _pascal(name) not in valid_keys
    }
    if unknown:
        listing = "\n".join(f"  {name!r} — {src}" for name, src in sorted(unknown.items()))
        print(
            f"✗ {len(unknown)} icon-intent literal(s) name a non-existent lucide icon "
            f"(would silently fall back to help-circle):\n{listing}",
            file=sys.stderr,
        )
        return 1

    used = scan_used_names(valid_keys)

    # Every name is valid by construction (scan_used_names filters against all_nodes).
    resolved = {name: node_to_markup(all_nodes[_pascal(name)]) for name in sorted(used)}

    # Double-quote keys so the output is ruff-format-stable (repr would emit
    # single quotes, which the formatter rewrites; markup values keep repr's
    # single quotes because they contain double quotes). Names are simple kebab
    # literals with no quotes, so f-string interpolation is safe.
    body = "".join(f'    "{name}": {markup!r},\n' for name, markup in resolved.items())
    OUT.write_text(
        f'"""Inner SVG markup per lucide icon. GENERATED by scripts/gen_icons.py — do not edit.\n\n'
        f"Source: {BUNDLE.name}. Run ``uv run python scripts/gen_icons.py`` to regenerate.\n"
        f'"""\n\n'
        f"ICON_PATHS: dict[str, str] = {{\n{body}}}\n",
        encoding="utf-8",
    )
    print(f"✓ wrote {OUT.relative_to(APP_ROOT)} with {len(resolved)} icons")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
