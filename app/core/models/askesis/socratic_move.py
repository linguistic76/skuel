"""
Socratic Move — Pedagogical Response Configuration
=====================================================

Frozen dataclass representing the output of the SocraticEngine. A SocraticMove
contains everything needed to generate an LLM response for a single Socratic
tutoring turn: the system prompt, curriculum context, evaluation rubric, and
target KUs.

Consumed by: QueryProcessor.process_socratic_turn() → LLM call
Produced by: SocraticEngine.generate_move()

See: /docs/architecture/ASKESIS_SOCRATIC_ARCHITECTURE.md
"""

from __future__ import annotations

from dataclasses import dataclass

from core.models.askesis.pedagogical_intent import PedagogicalIntent


@dataclass(frozen=True)
class SocraticMove:
    """Configuration for a single Socratic tutoring response.

    The SocraticEngine produces a SocraticMove; the pipeline uses it to
    construct the LLM call. The move_type determines the tutoring strategy,
    the system_prompt guides the LLM's response style, and curriculum_context
    provides the relevant Article content.

    Fields
    ------
    move_type : PedagogicalIntent
        Which Socratic strategy to apply.

    system_prompt : str
        Guides the LLM's response style for this turn.

    curriculum_context : str
        Relevant Article content / KU descriptions for the LLM to reference.
        For ASSESS_UNDERSTANDING, this is withheld from the user-facing
        response — the LLM uses it only to evaluate, not to give answers.

    target_ku_uids : tuple[str, ...]
        KU UIDs this move targets. Used for tracking and ZPD feedback.

    evaluation_rubric : str | None
        For ASSESS: learning objectives to check the user's response against.
        None when structured objectives are not yet available.

    edges_to_surface : tuple[dict, ...]
        For SURFACE_CONNECTION: semantic relationships to highlight.

    conversation_history : tuple[dict, ...]
        Recent turns for context continuity in multi-turn conversations.
    """

    move_type: PedagogicalIntent
    system_prompt: str
    curriculum_context: str
    target_ku_uids: tuple[str, ...] = ()
    evaluation_rubric: str | None = None
    edges_to_surface: tuple[dict, ...] = ()
    conversation_history: tuple[dict, ...] = ()
