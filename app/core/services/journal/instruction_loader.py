"""Instruction file loader for the DNWF journal workflow.

Reads the instruction files from data/instructions/ and composes
stage-specific system prompts. Files are admin-visible only; never
exposed to the journal user.

Stage system prompt composition:
    Stage 1 (Scribe):          dnwf 1.md
    Stage 2 (Thought Partner): dnwf 1.md + Stance+Direction + roles+interventions + user context
    Stage 3 (What Is Related): dnwf 1.md + user context

JournalMode nudges the companion's flavour for the conversational prompts
(discussion_system_prompt / follow_up_system_prompt). The three DNWF stage
functions (stage1/2/3_system_prompt) are mode-invariant — mode selection
determines which stage runs, not how it runs.

Conversational bases (ADR-081 D1): the discussion / follow-up base voice is a
committed default FLOOR (guaranteed present, per mode) with an optional
founder-local override file in data/instructions/
(``journals.discussion.{mode}.md`` / ``journals.follow_up.{mode}.md``).
Override present and non-blank → it replaces the floor; absent → the floor.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Final

from core.utils.logging import get_logger

if TYPE_CHECKING:
    from core.models.enums.user_enums import JournalMode

_logger = get_logger("skuel.services.journal.instruction_loader")

_APP_ROOT: Final = Path(__file__).resolve().parent.parent.parent.parent
INSTRUCTIONS_DIR: Final = _APP_ROOT / "data" / "instructions"

_FILES: Final[dict[str, str]] = {
    "main": "dnwf 1.md",
    "stance": "Stance + Direction.md",
    "roles": "roles interventions.md",
    "style": "dnwf style guide.md",
    "shortcodes": "inline_metadata_ie_short_codes.md",
}


def _load(key: str) -> str:
    path = INSTRUCTIONS_DIR / _FILES[key]
    if not path.exists():
        if key == "main":
            _logger.warning(
                "DNWF primary instruction file missing: %s — "
                "Stage 1/2/3 will run without structured prompts. "
                "Populate data/instructions/ from your local copy.",
                path,
            )
        return ""
    return path.read_text(encoding="utf-8")


def _resolve_contained(filename: str) -> Path | None:
    """Resolve ``filename`` inside ``INSTRUCTIONS_DIR`` — or ``None`` on traversal.

    THE single containment guard for every by-name read from the instructions
    dir (``load_named_instruction`` and the ADR-081 override reader). Traversal
    out of the dir is always an attack or a bug, so it warns regardless of
    which caller hit it.
    """
    candidate = (INSTRUCTIONS_DIR / filename).resolve()
    try:
        candidate.relative_to(INSTRUCTIONS_DIR.resolve())
    except ValueError:
        _logger.warning("Path traversal attempt blocked: %r", filename)
        return None
    return candidate


def load_named_instruction(filename: str) -> str | None:
    """Read a user-named instruction file from ``INSTRUCTIONS_DIR`` — or ``None``.

    The named-file counterpart to the fixed ``_FILES`` registry above: the DNWF
    stage prompts compose known files, while the batch upload/folder pipeline
    lets the form select a file by name. Same directory, one loading home. The
    containment guard blocks path traversal out of the instructions dir; a
    missing file degrades to ``None`` (the pipeline runs uninstructed).
    """
    candidate = _resolve_contained(filename)
    if candidate is None:
        return None
    if not candidate.is_file():
        _logger.warning("Instruction file not found: %s", candidate)
        return None
    return candidate.read_text(encoding="utf-8")


def _load_optional_override(filename: str) -> str | None:
    """Read an optional founder-local override file — ``None`` when absent or blank.

    The ADR-081 D1 override reader: absence is the NORMAL state (the committed
    floor serves), so a miss is silent — unlike ``load_named_instruction``,
    which warns because a *named* file was expected. Blank/whitespace content
    also degrades to ``None`` so a stray empty file can never blank a floor.
    """
    candidate = _resolve_contained(filename)
    if candidate is None or not candidate.is_file():
        return None
    content = candidate.read_text(encoding="utf-8")
    return content if content.strip() else None


def stage1_system_prompt() -> str:
    """System prompt for Stage 1 — Scribe."""
    return _load("main")


def stage2_system_prompt(
    user_context_summary: str, canon_context: str = "", vault_context: str = ""
) -> str:
    """System prompt for Stage 2 — Thought Partner.

    ``canon_context`` (when non-empty) is the ``CanonContext.to_prompt_block()``
    of summoned canon passages, appended as its own section — same mechanism as
    the user-context block. ``vault_context`` is the vault dial's counterpart
    (canon P3), appended after the canon block.
    """
    parts = [
        _load("main"),
        _load("stance"),
        _load("roles"),
        _load("shortcodes"),
    ]
    if user_context_summary:
        parts.append(f"## Current User Context\n\n{user_context_summary}")
    if canon_context:
        parts.append(canon_context)
    if vault_context:
        parts.append(vault_context)
    return "\n\n---\n\n".join(p for p in parts if p.strip())


def stage3_system_prompt(
    user_context_summary: str, canon_context: str = "", vault_context: str = ""
) -> str:
    """System prompt for Stage 3 — What Is Related.

    ``canon_context`` (when non-empty) is the ``CanonContext.to_prompt_block()``
    of summoned canon passages, appended as its own section. ``vault_context``
    is the vault dial's counterpart (canon P3), appended after the canon block.
    """
    parts = [_load("main")]
    if user_context_summary:
        parts.append(f"## Current User Context\n\n{user_context_summary}")
    if canon_context:
        parts.append(canon_context)
    if vault_context:
        parts.append(vault_context)
    return "\n\n---\n\n".join(p for p in parts if p.strip())


def discussion_system_prompt(
    user_context_summary: str,
    mode: "JournalMode | None" = None,
    canon_context: str = "",
    vault_context: str = "",
) -> str:
    """System prompt for the FIRST message of an open journal discussion.

    The discussion-first counterpart to ``standard_system_prompt`` (removed): a
    typed entry opens a conversation the *user* leads, not a fixed analysis
    template. Same family as ``follow_up_system_prompt`` — a companion voice
    with no imposed headings — but framed as an opening turn rather than a
    continuation. Mode nudges flavour (scribe-close / connector / thought
    partner) without becoming the frame.

    ``canon_context`` (when non-empty) is ``CanonContext.to_discussion_block()``
    — discussion is a quote-on-demand surface (ADR-076), so the model may name
    and quote the shelf. ``vault_context`` is the vault dial's counterpart
    (canon P3), appended after the canon block. UserContext is always-on
    grounding (what makes the companion *theirs*); canon/vault are FOUNDER dials
    the route gates server-side.
    """
    from core.models.enums.user_enums import JournalMode

    resolved = mode if mode is not None else JournalMode.default()
    parts = [_discussion_base(resolved)]
    if user_context_summary:
        parts.append(f"## User's Active Context\n\n{user_context_summary}")
    if canon_context:
        parts.append(canon_context)
    if vault_context:
        parts.append(vault_context)
    return "\n\n".join(parts)


# Committed default FLOOR for the opening-turn discussion base, keyed by
# JournalMode.value (ADR-081 D1) — guaranteed present so the companion is
# never uninstructed; a founder-local journals.discussion.{mode}.md overrides.
_DISCUSSION_BASE_DEFAULTS: Final[dict[str, str]] = {
    "scribe": (
        "You are a faithful thinking companion opening a conversation. The user has "
        "written to you — respond directly and conversationally, staying close to their "
        "voice and language. Follow their lead: clarify, reflect back, or help them find "
        "words for what they're reaching toward. No headers, no analysis template, no "
        "advice they didn't ask for."
    ),
    "what_is_related": (
        "You are a knowledge companion opening a conversation. The user has written to "
        "you — respond directly and conversationally. Where it helps *them*, draw a "
        "connection to what they already know, care about, or are working on. Follow "
        "their lead rather than mapping everything. No headers, no analysis template."
    ),
    "thought_partner": (
        "You are a thoughtful journal companion opening a conversation. The user has written "
        "to you — respond directly and conversationally, engaging with what they've actually "
        "raised. Let them lead: expand a point, offer a gentle challenge, draw a connection, "
        "or reflect back what you're noticing. No headers, no fresh analysis structure, no "
        "forced conclusions. Keep an honest, attentive, respectful tone."
    ),
}


def _discussion_base(mode: "JournalMode") -> str:
    """Opening-turn discussion base — committed floor, optional authored override (ADR-081 D1)."""
    override = _load_optional_override(f"journals.discussion.{mode.value}.md")
    return override if override is not None else _DISCUSSION_BASE_DEFAULTS[mode.value]


def follow_up_system_prompt(
    user_context_summary: str,
    mode: "JournalMode | None" = None,
    canon_context: str = "",
    vault_context: str = "",
) -> str:
    """System prompt for a follow-up turn in a journal conversation.

    Uses a follow-up-specific base that omits any structural formatting rules
    (e.g. '# What is Emerging') so the LLM responds conversationally rather
    than re-running its analysis template.

    ``canon_context`` (when non-empty) is ``CanonContext.to_discussion_block()``
    — the follow-up is the quote-on-demand surface (ADR-076), so the model may
    name and quote the shelf passages, not merely infuse them. ``vault_context``
    is the vault dial's counterpart (canon P3), appended after the canon block.
    """
    from core.models.enums.user_enums import JournalMode

    resolved = mode if mode is not None else JournalMode.default()
    base = _follow_up_base(resolved)
    parts = [base]
    if user_context_summary:
        parts.append(f"## User's Active Context\n\n{user_context_summary}")
    if canon_context:
        parts.append(canon_context)
    if vault_context:
        parts.append(vault_context)
    return "\n\n".join(parts)


# Committed default FLOOR for the follow-up base, keyed by JournalMode.value
# (ADR-081 D1) — a founder-local journals.follow_up.{mode}.md overrides.
_FOLLOW_UP_BASE_DEFAULTS: Final[dict[str, str]] = {
    "scribe": (
        "You are a faithful scribe continuing a conversation. The user has reviewed "
        "your previous record and is following up.\n\n"
        "Respond directly to their question or correction. If they want a revision, "
        "make it. If they're asking about a choice you made, explain it briefly. "
        "Keep the same close, faithful, non-interpretive stance — no headers, no analysis."
    ),
    "what_is_related": (
        "You are a knowledge connector continuing a conversation. The user has read "
        "your previous connections and is following up.\n\n"
        "Respond directly to their question or reaction. Expand a specific connection, "
        "drop one that doesn't land, or surface a new one they've prompted. "
        "No new full connection maps — just the thread they've pulled."
    ),
    "thought_partner": (
        "You are a thoughtful journal companion continuing a conversation. The user has "
        "read your previous response and is following up.\n\n"
        "Respond directly and conversationally — no headers, no fresh analysis structure. "
        "Engage with what they've raised: expand a point, offer a challenge, draw a "
        "connection, or reflect back what you're noticing. Keep the same honest, "
        "attentive, respectful tone."
    ),
}


def _follow_up_base(mode: "JournalMode") -> str:
    """Follow-up base — committed floor, optional authored override (ADR-081 D1)."""
    override = _load_optional_override(f"journals.follow_up.{mode.value}.md")
    return override if override is not None else _FOLLOW_UP_BASE_DEFAULTS[mode.value]


def journal_mode_addendum(mode: "JournalMode") -> str:
    """Function addendum injected into upload-pipeline LLM prompts (LLM_SUMMARY / TRANSCRIBE_AND_STRUCTURE)."""
    from core.models.enums.user_enums import JournalMode

    if mode is JournalMode.SCRIBE:
        return "Process this as Stage 1 — Scribe: produce a faithful structural record."
    if mode is JournalMode.WHAT_IS_RELATED:
        return (
            "Process this as Stage 3 — What Is Related: identify connections to existing knowledge."
        )
    # THOUGHT_PARTNER
    return "Process this as Stage 2 — Thought Partner: identify patterns, tensions, and what is emerging."
