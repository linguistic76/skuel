"""Instruction file loader for the DNWF journal workflow.

Reads the instruction files from data/instructions/ and composes
stage-specific system prompts. Files are admin-visible only; never
exposed to the journal user.

Stage system prompt composition:
    Stage 1 (Scribe):         dnwf 1.md
    Stage 2 (Thought Partner): dnwf 1.md + Stance+Direction + roles+interventions + user context
    Stage 3 (What Is Related): dnwf 1.md + user context
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from core.utils.logging import get_logger

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


def stage1_system_prompt() -> str:
    """System prompt for Stage 1 — Scribe."""
    return _load("main")


def stage2_system_prompt(user_context_summary: str) -> str:
    """System prompt for Stage 2 — Thought Partner."""
    parts = [
        _load("main"),
        _load("stance"),
        _load("roles"),
        _load("shortcodes"),
    ]
    if user_context_summary:
        parts.append(f"## Current User Context\n\n{user_context_summary}")
    return "\n\n---\n\n".join(p for p in parts if p.strip())


def stage3_system_prompt(user_context_summary: str) -> str:
    """System prompt for Stage 3 — What Is Related."""
    parts = [_load("main")]
    if user_context_summary:
        parts.append(f"## Current User Context\n\n{user_context_summary}")
    return "\n\n---\n\n".join(p for p in parts if p.strip())


def standard_system_prompt(user_context_summary: str) -> str:
    """System prompt for the STANDARD tier — single motivating response.

    Builds a self-contained prompt (no file dependency) that instructs the LLM
    to respond as a warm journal companion, connect the entry to the user's active
    context, and close with a graph-suggestion section only when context is present.
    """
    base = (
        "You are a thoughtful journal companion. When the user shares their daily note, "
        "respond in a single warm message that does three things:\n\n"
        "1. Acknowledge what they wrote with genuine attention — reflect one or two "
        "threads that stand out, without summarising the whole note back to them.\n\n"
        "2. Connect their reflections to their active goals, tasks, and habits (provided "
        "below if present). Name specifics. Be encouraging and forward-looking — this is "
        "a partner who wants them to succeed, not a critic.\n\n"
        "3. End with a short section titled 'What this connects to' that proposes 2-4 "
        "knowledge threads or concepts their journal touches. Frame these as invitations "
        "to explore, not commands. Only include this section if you can name at least two "
        "specific connections — omit it entirely rather than give vague or generic ones.\n\n"
        "Tone: warm, honest, encouraging. No stage structure, no clinical language. "
        "Write as a knowledgeable friend who pays close attention."
    )
    if user_context_summary:
        base += f"\n\n## User's Active Context\n\n{user_context_summary}"
    return base
