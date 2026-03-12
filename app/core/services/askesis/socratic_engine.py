"""
Socratic Engine — Pedagogical Move Selection
===============================================

Pure logic service — no I/O. Given the LS bundle, pedagogical intent, ZPD
evidence, and conversation history, produces the right SocraticMove.

Each PedagogicalIntent maps to a specific tutoring strategy with a tailored
system prompt. The engine does NOT call the LLM — it constructs the move
that the pipeline will use for the LLM call.

Key principle: Askesis does not give answers. It asks the user to produce
knowledge. The system prompts are designed accordingly.

See: /docs/architecture/ASKESIS_SOCRATIC_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.models.askesis.pedagogical_intent import PedagogicalIntent
from core.models.askesis.socratic_move import SocraticMove

if TYPE_CHECKING:
    from core.models.askesis.ls_bundle import LSBundle
    from core.models.user.conversation import ConversationSession
    from core.models.zpd.zpd_assessment import ZoneEvidence


class SocraticEngine:
    """Generate pedagogical moves for Socratic tutoring.

    Stateless, pure logic — no I/O, no dependencies. Given the classified
    intent, LS bundle, and ZPD evidence, produces a SocraticMove containing
    the system prompt, curriculum context, and evaluation rubric.

    Usage:
        engine = SocraticEngine()
        move = engine.generate_move(intent, ls_bundle, zone_evidence, ...)
    """

    def generate_move(
        self,
        intent: PedagogicalIntent,
        ls_bundle: LSBundle,
        zone_evidence: dict[str, ZoneEvidence],
        conversation: ConversationSession | None,
        target_ku_uids: list[str],
    ) -> SocraticMove:
        """Generate the Socratic move for a tutoring turn.

        Dispatches to intent-specific builders that construct the system
        prompt, curriculum context, and evaluation rubric.

        Args:
            intent: Classified pedagogical intent for this turn.
            ls_bundle: Complete LS bundle (scoped context).
            zone_evidence: Per-KU engagement evidence from ZPD.
            conversation: Current conversation session (for history).
            target_ku_uids: KU UIDs the question targets.

        Returns:
            SocraticMove ready for the LLM call.
        """
        history = self._extract_history(conversation)
        builders = {
            PedagogicalIntent.ASSESS_UNDERSTANDING: self._build_assess,
            PedagogicalIntent.PROBE_DEEPER: self._build_probe,
            PedagogicalIntent.SCAFFOLD: self._build_scaffold,
            PedagogicalIntent.REDIRECT_TO_CURRICULUM: self._build_redirect,
            PedagogicalIntent.ENCOURAGE_PRACTICE: self._build_encourage,
            PedagogicalIntent.SURFACE_CONNECTION: self._build_surface,
            PedagogicalIntent.OUT_OF_SCOPE: self._build_out_of_scope,
        }
        builder = builders.get(intent, self._build_out_of_scope)
        return builder(ls_bundle, zone_evidence, target_ku_uids, history)

    # =====================================================================
    # INTENT-SPECIFIC BUILDERS
    # =====================================================================

    def _build_assess(
        self,
        ls_bundle: LSBundle,
        zone_evidence: dict[str, ZoneEvidence],
        target_ku_uids: list[str],
        history: tuple[dict, ...],
    ) -> SocraticMove:
        """ASSESS_UNDERSTANDING: Ask user to produce knowledge.

        The LLM receives the curriculum content to evaluate against, but
        the system prompt instructs it NOT to give the answer — only to
        ask the user to explain in their own words.
        """
        ku_names = self._get_ku_names(ls_bundle, target_ku_uids)
        rubric = self._build_rubric(ls_bundle, target_ku_uids)

        return SocraticMove(
            move_type=PedagogicalIntent.ASSESS_UNDERSTANDING,
            system_prompt=(
                "You are a Socratic tutor. The learner has engaged with the "
                "following concepts and you need to assess their understanding. "
                "Do NOT give answers or explain the concepts. Instead, ask the "
                "learner to explain what they know in their own words. Use "
                "open-ended questions like 'Tell me what you understand about...' "
                "or 'How would you explain... to someone new to this?'\n\n"
                f"Concepts to assess: {', '.join(ku_names)}"
            ),
            curriculum_context=ls_bundle.curriculum_context_text,
            target_ku_uids=tuple(target_ku_uids),
            evaluation_rubric=rubric,
            conversation_history=history,
        )

    def _build_probe(
        self,
        ls_bundle: LSBundle,
        zone_evidence: dict[str, ZoneEvidence],
        target_ku_uids: list[str],
        history: tuple[dict, ...],
    ) -> SocraticMove:
        """PROBE_DEEPER: Follow up on claimed mastery.

        The learner has partial evidence (1 signal). Ask a follow-up that
        tests understanding beyond the surface level.
        """
        ku_names = self._get_ku_names(ls_bundle, target_ku_uids)

        return SocraticMove(
            move_type=PedagogicalIntent.PROBE_DEEPER,
            system_prompt=(
                "You are a Socratic tutor. The learner has some familiarity "
                "with these concepts but hasn't demonstrated deep understanding. "
                "Ask a follow-up question that tests understanding beyond "
                "surface-level recognition. Probe for application, nuance, or "
                "connections. Do NOT give the answer.\n\n"
                f"Concepts to probe: {', '.join(ku_names)}"
            ),
            curriculum_context=ls_bundle.curriculum_context_text,
            target_ku_uids=tuple(target_ku_uids),
            conversation_history=history,
        )

    def _build_scaffold(
        self,
        ls_bundle: LSBundle,
        zone_evidence: dict[str, ZoneEvidence],
        target_ku_uids: list[str],
        history: tuple[dict, ...],
    ) -> SocraticMove:
        """SCAFFOLD: Guide toward insight without giving the answer.

        The KU is in the proximal zone — structurally adjacent but not yet
        engaged. The system prompt includes curriculum content so the LLM
        knows what to scaffold toward, but instructs it to ask leading
        questions rather than explain directly.
        """
        ku_names = self._get_ku_names(ls_bundle, target_ku_uids)

        return SocraticMove(
            move_type=PedagogicalIntent.SCAFFOLD,
            system_prompt=(
                "You are a Socratic tutor. The learner is approaching new "
                "concepts they haven't engaged with yet. Guide them toward "
                "understanding through questions, analogies, and step-by-step "
                "reasoning. Do NOT give direct explanations. Ask questions "
                "that lead them to discover the insight themselves.\n\n"
                f"Concepts to scaffold: {', '.join(ku_names)}\n\n"
                "Use the curriculum context below to know what you're "
                "scaffolding toward, but do not simply restate it."
            ),
            curriculum_context=ls_bundle.curriculum_context_text,
            target_ku_uids=tuple(target_ku_uids),
            conversation_history=history,
        )

    def _build_redirect(
        self,
        ls_bundle: LSBundle,
        zone_evidence: dict[str, ZoneEvidence],
        target_ku_uids: list[str],
        history: tuple[dict, ...],
    ) -> SocraticMove:
        """REDIRECT_TO_CURRICULUM: Point to the Article they should read.

        No engagement at all — redirect to the source material. Include
        the Article title and a brief summary to orient the learner.
        """
        # Find Articles linked to the target KUs
        article_refs = []
        for ku_uid in target_ku_uids:
            article = ls_bundle.get_article_for_ku(ku_uid)
            if article:
                article_refs.append(article.title or "Untitled Article")

        if not article_refs:
            # Fall back to all Articles in the bundle
            article_refs = [a.title or "Untitled Article" for a in ls_bundle.articles]

        articles_text = ", ".join(dict.fromkeys(article_refs))

        return SocraticMove(
            move_type=PedagogicalIntent.REDIRECT_TO_CURRICULUM,
            system_prompt=(
                "You are a Socratic tutor. The learner is asking about "
                "concepts they haven't engaged with yet and there is "
                "curriculum content available for them to study. Gently "
                "redirect them to read the relevant material first. Be "
                "encouraging, not dismissive. Give a brief orientation of "
                "what they'll find in the material.\n\n"
                f"Recommended reading: {articles_text}"
            ),
            curriculum_context=ls_bundle.curriculum_context_text,
            target_ku_uids=tuple(target_ku_uids),
            conversation_history=history,
        )

    def _build_encourage(
        self,
        ls_bundle: LSBundle,
        zone_evidence: dict[str, ZoneEvidence],
        target_ku_uids: list[str],
        history: tuple[dict, ...],
    ) -> SocraticMove:
        """ENCOURAGE_PRACTICE: Connect understanding to practice.

        ZoneEvidence shows the learner has conceptual engagement but is
        missing practice signals (habits, tasks). Point them to the
        practice activities in the bundle.
        """
        practice_items = []
        for habit in ls_bundle.habits:
            practice_items.append(f"Habit: {habit.title}")
        for task in ls_bundle.tasks:
            practice_items.append(f"Task: {task.title}")
        for event in ls_bundle.events:
            practice_items.append(f"Event: {event.title}")

        practice_text = (
            "\n".join(practice_items)
            if practice_items
            else "No specific practice activities linked."
        )

        return SocraticMove(
            move_type=PedagogicalIntent.ENCOURAGE_PRACTICE,
            system_prompt=(
                "You are a Socratic tutor. The learner has conceptual "
                "understanding but needs to deepen it through practice. "
                "Acknowledge their understanding, then encourage them to "
                "engage with the practice activities linked to their current "
                "learning step. Explain how practice compounds knowledge.\n\n"
                f"Available practice activities:\n{practice_text}"
            ),
            curriculum_context="",
            target_ku_uids=tuple(target_ku_uids),
            conversation_history=history,
        )

    def _build_surface(
        self,
        ls_bundle: LSBundle,
        zone_evidence: dict[str, ZoneEvidence],
        target_ku_uids: list[str],
        history: tuple[dict, ...],
    ) -> SocraticMove:
        """SURFACE_CONNECTION: Highlight relationships between concepts.

        The question touches multiple edge-connected concepts. Surface the
        semantic relationship and ask the learner to reflect on it.
        """
        # Find edges that connect the target KUs
        relevant_edges: list[dict] = []
        target_set = set(target_ku_uids)
        for edge in ls_bundle.edges:
            if isinstance(edge, dict):
                source = edge.get("source_uid", "")
                target = edge.get("target_uid", "")
                if source in target_set or target in target_set:
                    relevant_edges.append(edge)

        edges_text = ""
        for edge in relevant_edges:
            rel_type = edge.get("relationship_type", "related to")
            evidence = edge.get("evidence", "")
            edges_text += f"- {rel_type}: {evidence}\n"

        return SocraticMove(
            move_type=PedagogicalIntent.SURFACE_CONNECTION,
            system_prompt=(
                "You are a Socratic tutor. The learner's question touches "
                "concepts that are connected in the curriculum. Surface this "
                "connection and ask the learner to reflect on how the concepts "
                "relate. Use the relationship evidence to guide the question.\n\n"
                f"Relationship evidence:\n{edges_text or 'No specific evidence available.'}"
            ),
            curriculum_context=ls_bundle.curriculum_context_text,
            target_ku_uids=tuple(target_ku_uids),
            edges_to_surface=tuple(relevant_edges),
            conversation_history=history,
        )

    def _build_out_of_scope(
        self,
        ls_bundle: LSBundle,
        zone_evidence: dict[str, ZoneEvidence],
        target_ku_uids: list[str],
        history: tuple[dict, ...],
    ) -> SocraticMove:
        """OUT_OF_SCOPE: Question not in the LS bundle.

        Gently redirect the learner to their current focus area.
        """
        ls_title = ls_bundle.learning_step.title or "your current step"
        ls_intent = ls_bundle.learning_step.intent or ""

        return SocraticMove(
            move_type=PedagogicalIntent.OUT_OF_SCOPE,
            system_prompt=(
                "You are a Socratic tutor. The learner asked about something "
                "outside the scope of their current learning step. Acknowledge "
                "their curiosity, but gently redirect them to their current "
                "focus. Be warm, not dismissive.\n\n"
                f"Current learning step: {ls_title}\n"
                f"Step intent: {ls_intent}"
            ),
            curriculum_context="",
            target_ku_uids=(),
            conversation_history=history,
        )

    # =====================================================================
    # HELPERS
    # =====================================================================

    def _get_ku_names(self, ls_bundle: LSBundle, ku_uids: list[str]) -> list[str]:
        """Get KU titles for the given UIDs from the bundle."""
        names = []
        uid_set = set(ku_uids)
        for ku in ls_bundle.kus:
            if ku.uid in uid_set:
                names.append(ku.title or ku.uid)
        return names or ["(unknown concepts)"]

    def _build_rubric(self, ls_bundle: LSBundle, target_ku_uids: list[str]) -> str | None:
        """Build evaluation rubric from learning objectives.

        Uses the bundle's learning_objectives (from Articles). Returns None
        if no objectives are available.
        """
        if not ls_bundle.learning_objectives:
            return None

        # Filter to objectives relevant to target KUs if possible
        # For now, include all bundle objectives — filtering by KU requires
        # structured objectives (Phase 6)
        objectives_text = "\n".join(f"- {obj}" for obj in ls_bundle.learning_objectives)
        return f"Learning objectives to assess against:\n{objectives_text}"

    def _extract_history(self, conversation: ConversationSession | None) -> tuple[dict, ...]:
        """Extract recent conversation turns as dicts for the move."""
        if conversation is None:
            return ()

        turns = getattr(conversation, "turns", [])
        history = []
        # Keep last 6 turns for context
        for turn in turns[-6:]:
            history.append(
                {
                    "role": getattr(turn, "role", "user"),
                    "content": getattr(turn, "content", ""),
                }
            )
        return tuple(history)
