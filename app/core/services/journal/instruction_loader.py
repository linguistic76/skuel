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


def instructions_available() -> bool:
    """Return True when at least the primary instruction file exists."""
    return (INSTRUCTIONS_DIR / _FILES["main"]).exists()
