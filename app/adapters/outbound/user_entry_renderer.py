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


def entry_download_filename(entry: UserEntry) -> str:
    """The ``.md`` filename for an entry — its title slugged to ASCII, the uid when nothing is left.

    A response header is Latin-1 on the wire, so every character outside ASCII
    letters and digits becomes ``-`` (a CJK or Cyrillic title collapses to the
    uid rather than raising when the header is encoded).
    """
    safe_title = "".join(
        c if (c.isascii() and c.isalnum()) or c in "-_" else "-"
        for c in (entry.title or entry.uid).lower()
    ).strip("-")
    return f"entry-{safe_title or entry.uid}.md"


__all__ = ["entry_download_filename", "render_user_entry_md"]
