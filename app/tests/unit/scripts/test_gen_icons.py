"""Every icon-intent literal must resolve to a real entry in the committed registry.

With the lucide runtime gone (#452), an unknown icon name no longer fails anywhere — it
renders a silent ``help-circle`` fallback. ``scripts/gen_icons.py`` harvests names
permissively (keeps only literals that *are* real lucide icons), so a typo'd name is
dropped from ``ICON_PATHS`` instead of erroring. This test closes that gap in CI: it scans
the same source globs for icon-intent literals — ``Icon("name")``, ``icon="name"`` config
fields, and ``_icon_*("name")`` wrapper helpers — and asserts each name is a key in the
committed ``ICON_PATHS``.

It validates against the *committed* registry (not the lucide bundle), so it needs neither
node nor the vendored bundle, and it also catches the second failure mode — a valid icon
name added in code but the registry not regenerated.
"""

from __future__ import annotations

import sys
from pathlib import Path

# scripts/ has no __init__.py — add it to sys.path for import (matches test_lint_skuel.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from gen_icons import icon_name_literals  # type: ignore[import-not-found]

from ui.components._icon_data import ICON_PATHS


def test_icon_intent_literals_resolve_to_registry() -> None:
    """No icon-intent literal may silently fall back to help-circle."""
    unknown = {
        name: src for name, src in icon_name_literals().items() if name not in ICON_PATHS
    }
    assert not unknown, (
        "Icon-intent literals name an icon missing from ICON_PATHS (renders a silent "
        "help-circle fallback). Fix the name if it's a typo, or run "
        "`uv run python scripts/gen_icons.py` if it's a real lucide icon:\n"
        + "\n".join(f"  {name!r} — {src}" for name, src in sorted(unknown.items()))
    )
