"""
Vault-relative path rendering for user-facing sync messages.

Vault sync stats (``VaultSyncStats.errors``/``.warnings``) reach the HTMX
fragment and the JSON API verbatim — an absolute host filesystem path in
those strings is an information leak on any hosted deployment.

Policy (2026-07-05 vault security arc, PR 5): user-facing strings render
paths relative to the vault root (or bare basename when outside it); full
absolute detail is logged at the emitting site instead. Log statements keep
absolute paths deliberately — never sanitize those.
"""

from __future__ import annotations

from pathlib import Path


def display_path(path: str | Path, root: Path) -> str:
    """Render ``path`` for a user-facing message: vault-relative, never absolute.

    Returns the path relative to the resolved ``root`` when it is under it,
    else just the basename — an absolute host path never escapes.
    """
    resolved = Path(path).resolve()
    resolved_root = root.resolve()
    if resolved.is_relative_to(resolved_root):
        return str(resolved.relative_to(resolved_root))
    return resolved.name


def strip_root_prefix(text: str, root: Path) -> str:
    """Remove the resolved ``root``'s absolute prefix from free-form ``text``.

    Pragmatic sanitizer for error messages that embed paths (OSError text,
    bridge-adapter errors, flattened ingest error dicts): ``<root>/…`` becomes
    vault-relative and a bare ``<root>`` becomes ``<vault>``. The bar is that
    no user-facing stats string contains the vault root's absolute prefix.
    """
    root_str = str(root.resolve())
    return text.replace(root_str + "/", "").replace(root_str, "<vault>")
