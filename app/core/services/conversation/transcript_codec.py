"""Transcript + source-selection codecs and export rendering (ADR-078).

The persistence contracts of the discussion store live HERE, beside
``ConversationService`` — not in route files:

- ``transcript_json`` — the ephemeral client-side conversation accumulator
  (ordered ``{"role", "content"}`` objects, ADR-078 §5). Parsed/serialized by
  ``parse_transcript`` / ``serialize_transcript``; folded into store-shaped
  ``(user, assistant)`` pairs by ``transcript_to_pairs`` at *Save*.
- ``source_selection`` — the stored grounding-dial JSON
  (``{"canon": [...], "canon_on": bool, "vault": bool}``, ADR-078 §3).
  One writer (``build_source_selection``), one reader
  (``parse_source_selection``) — routes never hand-assemble the shape.
- Markdown export (ADR-078 §8) — ``render_discussion_markdown`` +
  ``safe_export_filename`` produce the user-ownable transcript download.

All functions are pure (no I/O) and fail-soft on malformed input: a forged or
truncated field degrades to "nothing", never to an exception.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from core.models.conversation import ROLE_ASSISTANT, ROLE_USER

if TYPE_CHECKING:
    from core.models.conversation import ConversationTurn


def build_source_selection(
    canon_book_uids: list[str], summon_canon: bool, summon_vault: bool
) -> str:
    """Serialize the current source dials to the stored ``source_selection`` JSON.

    Shape: ``{"canon": [uid, …], "canon_on": bool, "vault": bool}`` (ADR-078 §3).
    The book *scope* is kept independent of the *dial* so an ungrounded save
    still records the session's book scope (mirrors the follow-up write, #635 P2).
    """
    return json.dumps(
        {
            "canon": list(canon_book_uids),
            "canon_on": bool(summon_canon),
            "vault": bool(summon_vault),
        }
    )


def parse_source_selection(raw: str) -> tuple[list[str], bool, bool]:
    """Parse a stored ``source_selection`` JSON → (canon book uids, canon on, vault on).

    Fail-soft: a malformed / empty value restores nothing. Back-compat: pre-PR3
    sessions carry no ``canon_on`` — infer it from a non-empty book list.
    """
    try:
        data = json.loads(raw) if raw else {}
    except ValueError, TypeError:
        return [], False, False
    if not isinstance(data, dict):
        return [], False, False
    raw_canon = data.get("canon")
    canon = [str(u) for u in raw_canon if isinstance(u, str)] if isinstance(raw_canon, list) else []
    canon_on = bool(data.get("canon_on", bool(canon)))
    vault = bool(data.get("vault"))
    return canon, canon_on, vault


def parse_transcript(raw: str) -> list[tuple[str, str]]:
    """Parse the ephemeral ``transcript_json`` field → ordered ``(role, content)``.

    Fail-soft: a malformed / empty value is an empty transcript. Only the two
    known roles survive, so a hand-forged field can never inject arbitrary turn
    shapes.
    """
    try:
        data = json.loads(raw) if raw else []
    except ValueError, TypeError:
        return []
    if not isinstance(data, list):
        return []
    out: list[tuple[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role in (ROLE_USER, ROLE_ASSISTANT) and isinstance(content, str):
            out.append((role, content))
    return out


def serialize_transcript(items: list[tuple[str, str]]) -> str:
    """Serialize an ordered ``(role, content)`` sequence to the ``transcript_json`` field."""
    return json.dumps([{"role": role, "content": content} for role, content in items])


def transcript_to_pairs(items: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Fold an ordered ``(role, content)`` transcript into ``(user, assistant)`` pairs.

    The ephemeral transcript is always grown one ``user``→``assistant`` pair at a
    time, so a straight two-step fold is faithful; a stray/half turn is skipped
    rather than paired with a mismatched neighbour (defensive against a forged
    field). Used only at *Save* — the write path into the store (ADR-078 §5).
    """
    pairs: list[tuple[str, str]] = []
    index = 0
    while index + 1 < len(items):
        if items[index][0] == ROLE_USER and items[index + 1][0] == ROLE_ASSISTANT:
            pairs.append((items[index][1], items[index + 1][1]))
            index += 2
        else:
            index += 1
    return pairs


def render_follow_up_context(items: list[tuple[str, str]]) -> tuple[str, str]:
    """Reconstruct ``(original_entry, ai_response)`` for ``run_follow_up`` from turns.

    Shared by both memory models (ADR-078): the Neo4j turn history (saved,
    session-backed) and the client-side ``transcript_json`` accumulator
    (ephemeral, unsaved) both flatten to the same ``(role, content)`` sequence,
    so context is rebuilt identically from one source of truth. ``ai_response``
    is the most recent assistant turn (the "previous response"); ``original_entry``
    is a rendered transcript of everything before it.
    """
    if not items:
        return "", ""
    split = len(items)
    ai_response = ""
    for index in range(len(items) - 1, -1, -1):
        if items[index][0] == ROLE_ASSISTANT:
            ai_response = items[index][1]
            split = index
            break
    rendered = "\n\n".join(
        f"# {'You' if role == ROLE_USER else 'Journal'}\n\n{content}"
        for role, content in items[:split]
    )
    return rendered, ai_response


def history_to_follow_up_context(turns: list[ConversationTurn]) -> tuple[str, str]:
    """``render_follow_up_context`` over a saved session's stored turns."""
    return render_follow_up_context([(turn.role, turn.content) for turn in turns])


def render_discussion_markdown(title: str, turns: list[ConversationTurn]) -> str:
    """Render a discussion to a markdown transcript for export (ADR-078 §8).

    A user-ownable copy — NOT a vault read-back folder (ADR-073 has none).
    """
    lines = [f"# {title or 'Discussion'}", ""]
    for turn in turns:
        lines.append(f"## {'You' if turn.role == ROLE_USER else 'Journal'}")
        lines.append("")
        lines.append(turn.content)
        lines.append("")
    return "\n".join(lines)


def safe_export_filename(title: str) -> str:
    """A safe ``.md`` download filename derived from the discussion title."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", (title or "discussion").strip()).strip("-")
    return f"{slug[:60] or 'discussion'}.md"


__all__ = [
    "build_source_selection",
    "history_to_follow_up_context",
    "parse_source_selection",
    "parse_transcript",
    "render_discussion_markdown",
    "render_follow_up_context",
    "safe_export_filename",
    "serialize_transcript",
    "transcript_to_pairs",
]
