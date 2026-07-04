"""
MOC body-link extraction — the ``moc: true`` edge pass, parse side.
===================================================================

``moc: true`` in the frontmatter of ANY ingestible file has exactly one
effect: the file's body links become ``(entity)-[:ORGANIZES {order}]->(target)``
edges to each link target that resolves to an already-ingested entity. This
module is the pure parse half: it turns a markdown body into an ordered,
deduplicated list of *path suffixes* ready for resolution against
``IngestionMetadata.file_path`` (the tracker's path→uid mapping).

Both Obsidian link styles are recognized:

- Wiki-links: ``[[target]]``, ``[[target|alias]]``, ``[[target#heading]]``
- Markdown links: ``[label](target.md)`` — URL-encoded paths (``%20``) are
  decoded; external URLs, image embeds (``![...]``), and non-``.md`` targets
  are skipped.

Order is document position (0-based, first occurrence wins on duplicates) —
it becomes the ``order`` property on each ORGANIZES edge, mirroring the
``order_property`` machinery rel-config list fields use.

MOC identity stays emergent: nothing reads the ``moc`` field back — a node is
a MOC because it has ORGANIZES edges. The field only triggers this pass at
ingestion time.

See: /docs/patterns/UNIFIED_INGESTION_GUIDE.md § MOC files
"""

from __future__ import annotations

import re
from urllib.parse import unquote

# Wiki-link: [[target]], [[target|alias]], [[target#heading]].
_WIKI_LINK_RE = re.compile(r"\[\[([^\[\]]+)\]\]")

# Markdown link: [label](target). The negative lookbehind skips image embeds
# (![alt](img.png)); the target group tolerates one level of parentheses so
# filenames like "theme(s) background.md" parse whole instead of truncating
# at the first ")".
_MD_LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(((?:[^()]|\([^()]*\))*)\)")

# One combined scan preserves document position across both link styles.
_ANY_LINK_RE = re.compile(f"{_WIKI_LINK_RE.pattern}|{_MD_LINK_RE.pattern}")

_EXTERNAL_TARGET_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")  # scheme: (http:, mailto:, ...)


def _suffix_from_wiki_target(raw: str) -> str | None:
    """Path suffix for a wiki-link target, or None when the link names no note."""
    target = raw.split("|", 1)[0].split("#", 1)[0].strip()
    if not target:
        return None  # [[#heading]] / [[|alias]] — no note named
    if not target.endswith(".md"):
        target += ".md"
    return f"/{target}"


def _suffix_from_md_target(raw: str) -> str | None:
    """Path suffix for a markdown-link target, or None when it isn't a vault note."""
    target = raw.strip()
    if not target or _EXTERNAL_TARGET_RE.match(target):
        return None
    # Fragment split happens BEFORE decoding — a literal '#' in a vault
    # filename arrives URL-encoded (%23), so this only strips real anchors.
    target = unquote(target.split("#", 1)[0]).strip()
    if not target:
        return None
    target = target.removeprefix("./")
    # ".." segments can't be matched as a path suffix without knowing the
    # source file's location — skip (personal posture: silently; content
    # posture never authors relative-parent links).
    if ".." in target.split("/"):
        return None
    if not target.endswith(".md"):
        # A non-.md extension is an attachment (image/pdf), not a note.
        last_segment = target.rsplit("/", 1)[-1]
        if "." in last_segment:
            return None
        target += ".md"
    return f"/{target}"


def extract_moc_link_suffixes(body: str | None) -> list[str]:
    """Ordered, deduplicated path suffixes for every note link in ``body``.

    Each suffix is ``/{relative-note-path}.md`` — the form matched against
    the canonical absolute ``IngestionMetadata.file_path`` with ``ENDS WITH``
    at resolution time. Position in the returned list IS the edge ``order``
    (first occurrence wins for duplicated links).

    An empty/None body returns ``[]`` — the edge pass still runs with an
    empty target list so an emptied MOC drops its stale edges.
    """
    if not body:
        return []

    suffixes: list[str] = []
    seen: set[str] = set()
    for match in _ANY_LINK_RE.finditer(body):
        wiki_target, md_target = match.group(1), match.group(2)
        suffix = (
            _suffix_from_wiki_target(wiki_target)
            if wiki_target is not None
            else _suffix_from_md_target(md_target or "")
        )
        if suffix is not None and suffix not in seen:
            seen.add(suffix)
            suffixes.append(suffix)
    return suffixes


__all__ = ["extract_moc_link_suffixes"]
