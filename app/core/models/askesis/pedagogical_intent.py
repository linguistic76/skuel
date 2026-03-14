"""
Pedagogical Intent - Socratic Move Classification
===================================================

Replaces retrieval-oriented intent ("what to fetch") with pedagogical intent
("what Socratic move to make"). Each intent maps to a specific tutoring
strategy via GuidanceMode in the ResponseGenerator.

The existing QueryIntent enum (in core/models/query_types.py) remains for
the legacy RAG pipeline. PedagogicalIntent is used exclusively by the new
LS-scoped Socratic pipeline.

See: /docs/architecture/ASKESIS_SOCRATIC_ARCHITECTURE.md
"""

from enum import StrEnum


class PedagogicalIntent(StrEnum):
    """Classification of pedagogical move for Socratic tutoring.

    Each value maps to a distinct tutoring strategy in the ResponseGenerator:

    ASSESS_UNDERSTANDING — Ask user to produce knowledge. Does NOT give answers.
        System prompt: "Ask the user to explain [X] in their own words."
        Triggered when: KU has confirmed ZoneEvidence (2+ signals).

    PROBE_DEEPER — Follow-up on claimed mastery. Tests deeper understanding.
        System prompt: "Ask a follow-up that tests understanding beyond surface."
        Triggered when: KU in current zone with 1 signal (partial evidence).

    SCAFFOLD — Guide toward insight without giving the answer.
        System prompt: "Ask questions that lead toward [insight] step by step."
        Triggered when: KU in proximal zone (structurally adjacent, not engaged).

    REDIRECT_TO_CURRICULUM — Point user to the Lesson/KU they need to read.
        Response: "Before we explore [X], read [Lesson title]."
        Triggered when: KU not yet engaged and has curriculum content available.

    ENCOURAGE_PRACTICE — Connect understanding to Habit/Task/Event practice.
        Response: "You understand [X] conceptually. Deepen it through [practice]."
        Triggered when: ZoneEvidence shows missing practice signals.

    SURFACE_CONNECTION — Surface semantic relationships between bundle entities.
        Response: "Did you notice that [A] and [B] are connected?"
        Triggered when: Question touches concepts connected by edges in bundle.

    OUT_OF_SCOPE — Question is not about content in the current LS bundle.
        Response: "That's outside your current focus. Your LS is about [intent]."
        Triggered when: No bundle entity matches the question.
    """

    ASSESS_UNDERSTANDING = "assess_understanding"
    PROBE_DEEPER = "probe_deeper"
    SCAFFOLD = "scaffold"
    REDIRECT_TO_CURRICULUM = "redirect_to_curriculum"
    ENCOURAGE_PRACTICE = "encourage_practice"
    SURFACE_CONNECTION = "surface_connection"
    OUT_OF_SCOPE = "out_of_scope"
