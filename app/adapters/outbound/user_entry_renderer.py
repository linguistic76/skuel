"""
UserEntry Renderer
==================

Renders a UserEntry to Markdown (.md) — the file a viewer opens from
``GET /gradebook/{uid}/download``, for the owner and for a recipient alike.

Architecture:
    Outbound adapter — transforms a domain model into a presentation format.
    The route handler calls render_user_entry_md() directly; no service
    indirection needed since this is pure presentation.

What it carries:
    The title, the description and the entry's own body (``content``). Never
    ``status`` (the teacher's verdict), ``processed_content``, feedback or the
    exchange — the recipient contract (Submit & Share arc R6, ADR-088 §3) is
    enforced by what this renderer omits, not by who calls it.

See: adapters/outbound/exercise_renderer.py for the exercise worksheet.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.user_entry.user_entry import UserEntry


def render_user_entry_md(entry: UserEntry) -> str:
    """Render one UserEntry as a Markdown document."""
    lines: list[str] = [f"# {entry.title or entry.uid}", ""]
    description = entry.description or entry.summary or ""
    if description:
        lines += [description, ""]
    body = entry.content or ""
    lines.append(body if body else "_No content._")
    return "\n".join(lines).rstrip("\n") + "\n"


def _ascii_slug(text: str) -> str:
    """ASCII letters, digits, ``-`` and ``_`` only; everything else becomes ``-``."""
    return "".join(
        c if (c.isascii() and c.isalnum()) or c in "-_" else "-" for c in text.lower()
    ).strip("-_")


def entry_download_filename(entry: UserEntry) -> str:
    """The ``.md`` filename for an entry — the title slugged to ASCII, then the uid, then a constant.

    A response header is Latin-1 on the wire, so nothing outside ASCII may
    reach it: a title or a uid with no ASCII letters or digits left falls
    through to the next fallback rather than raising when the header is
    encoded (the uid is caller-supplied on the JSON door, so it is slugged too).
    """
    slug = _ascii_slug(entry.title or "") or _ascii_slug(entry.uid)
    return f"entry-{slug}.md" if slug else "entry.md"


__all__ = ["entry_download_filename", "render_user_entry_md"]
