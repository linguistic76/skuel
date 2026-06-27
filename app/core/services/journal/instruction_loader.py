"""Instruction file loader for the DNWF journal workflow.

Reads the instruction files from data/instructions/ and composes
stage-specific system prompts. Files are admin-visible only; never
exposed to the journal user.

Stage system prompt composition:
    Stage 1 (Scribe):         dnwf 1.md
    Stage 2 (Thought Partner): dnwf 1.md + Stance+Direction + roles+interventions + user context
    Stage 3 (What Is Related): dnwf 1.md + user context

Mode modifiers (JournalMode) adjust tone/approach for standard_system_prompt
and stage2_system_prompt. Stage 1 (Scribe) and Stage 3 (graph connections)
are structural and mode-invariant.
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


def stage1_system_prompt() -> str:
    """System prompt for Stage 1 — Scribe."""
    return _load("main")


def stage2_system_prompt(user_context_summary: str, mode: "JournalMode | None" = None) -> str:
    """System prompt for Stage 2 — Thought Partner, optionally shaped by JournalMode."""
    parts = [
        _load("main"),
        _load("stance"),
        _load("roles"),
        _load("shortcodes"),
    ]
    if user_context_summary:
        parts.append(f"## Current User Context\n\n{user_context_summary}")
    if mode is not None:
        modifier = _mode_modifier(mode)
        if modifier:
            parts.append(f"## Response Mode\n\n{modifier}")
    return "\n\n---\n\n".join(p for p in parts if p.strip())


def stage3_system_prompt(user_context_summary: str) -> str:
    """System prompt for Stage 3 — What Is Related."""
    parts = [_load("main")]
    if user_context_summary:
        parts.append(f"## Current User Context\n\n{user_context_summary}")
    return "\n\n---\n\n".join(p for p in parts if p.strip())


def standard_system_prompt(user_context_summary: str, mode: "JournalMode | None" = None) -> str:
    """System prompt for the STANDARD tier — single motivating response.

    Builds a self-contained prompt (no file dependency) that instructs the LLM
    to respond as a journal companion in the requested mode. Mode shapes tone
    and structure; all modes connect the entry to active context.
    """
    from core.models.enums.user_enums import JournalMode

    resolved = mode if mode is not None else JournalMode.default()
    base = _standard_base_for_mode(resolved)
    if user_context_summary:
        base += f"\n\n## User's Active Context\n\n{user_context_summary}"
    return base


def _standard_base_for_mode(mode: "JournalMode") -> str:
    from core.models.enums.user_enums import JournalMode

    if mode is JournalMode.DIRECT:
        return (
            "You are a direct, no-nonsense journal companion. When the user shares their "
            "daily note, respond concisely and with purpose — three tight paragraphs max:\n\n"
            "1. Name 1-2 clear patterns or insights in what they wrote. No meandering.\n\n"
            "2. Connect those patterns to their active goals, tasks, and habits (listed below "
            "if present). Be specific — name the actual goal or task. Be forward-looking. "
            "If no active context is provided, skip this step entirely.\n\n"
            "3. Close with 2-3 concrete next actions they could take today or this week. "
            "Make them actionable, not aspirational.\n\n"
            "Tone: clear, honest, respectful. No fluff, no filler. Write like a smart colleague "
            "who has read the note once and has useful things to say."
        )
    if mode is JournalMode.JESTER:
        return (
            "You are a witty, irreverent journal companion with genuine warmth underneath. "
            "When the user shares their daily note, respond with humour and a light touch — "
            "a sharp metaphor, a surprising angle, a line that makes them smile. "
            "The substance is still there: connect to their real goals and context, reflect "
            "something true about what they wrote. But wear it lightly. "
            "A well-placed observation is worth three earnest paragraphs.\n\n"
            "Rules: be funny, not dismissive. Playful, not glib. If you can land a good joke "
            "and still be useful, do both. End with the 'What this connects to' section only "
            "if you have at least two specific connections worth naming — skip it rather than "
            "listing generic topics.\n\n"
            "Tone: warm, witty, a little irreverent. Write like a brilliant friend who happens "
            "to find this all mildly absurd — and who is still very much on your side."
        )
    # REFLECTIVE (default)
    return (
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


def journal_mode_addendum(mode: "JournalMode") -> str:
    """Mode addendum for injection into upload-pipeline LLM prompts (LLM_SUMMARY / TRANSCRIBE_AND_STRUCTURE).

    Delegates to the same modifier used by the FOUNDER stage2 prompt.
    """
    return _mode_modifier(mode)


def _mode_modifier(mode: "JournalMode") -> str:
    """Short addendum appended to FOUNDER stage2 prompts to shape response tone."""
    from core.models.enums.user_enums import JournalMode

    if mode is JournalMode.DIRECT:
        return (
            "Respond in a direct, concise register. Identify patterns quickly, name "
            "specific connections, close with concrete next actions. No meandering."
        )
    if mode is JournalMode.JESTER:
        return (
            "Respond with warmth and wit. Use humour, a good metaphor, or a surprising "
            "angle where it fits. Keep the substance — just wear it lightly."
        )
    # REFLECTIVE — default DNWF tone, no override needed
    return ""
