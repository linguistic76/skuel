"""
Response Generator - Action, Response, and Guided Prompt Generation
=====================================================================

Generates suggested actions, responses, and guided system prompts based on
context, intent, and pedagogical guidance mode.

Responsibilities:
- Build LLM-friendly context from UserContext
- Generate suggested actions based on intent and context
- Generate context-aware responses
- Build guided system prompts for Socratic tutoring (absorbed from SocraticEngine)

Architecture:
- Uses UserContext as primary input
- Uses QueryIntent for intent-specific logic
- Uses GuidanceDetermination for pedagogical prompt generation
- Returns structured data for API responses

January 2026: Extracted from QueryProcessor as part of Askesis design improvement.
March 2026: Absorbed SocraticEngine prompt builders — single response service.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.askesis.pedagogical_intent import PedagogicalIntent
from core.models.query_types import QueryIntent
from core.models.relationship_names import RelationshipName
from core.prompts import PROMPT_REGISTRY
from core.services.askesis.grounding_projection import render_askesis_grounding
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from core.models.askesis.ps_bundle import PsBundle
    from core.services.askesis.intent_classifier import GuidanceDetermination
    from core.services.canon import CanonContext
    from core.services.user import UserContext

logger = get_logger(__name__)


class ResponseGenerator:
    """
    Generate actions, responses, and guided prompts based on context and intent.

    This service handles response generation:
    - Build LLM-friendly context from UserContext
    - Generate suggested next actions
    - Generate context-aware responses
    - Build guided system prompts for Socratic tutoring

    Architecture:
    - Uses UserContext (~240 fields) as input
    - Uses QueryIntent for intent-specific logic
    - Uses GuidanceDetermination for pedagogical prompt generation
    - Returns structured dicts for API responses
    """

    def __init__(self) -> None:
        """Initialize response generator."""
        logger.info("ResponseGenerator initialized")

    def build_llm_context(
        self,
        user_context: UserContext,
        ps_bundle: PsBundle | None = None,
    ) -> str:
        """
        Render the facet/context-aware user-state block for the LLM prompt.

        The learner grounding is the ASKESIS_GROUNDING_FIELDS projection
        (ADR-082 D2) — the same curated block the guided branch carries, in
        place of the pre-ADR-082 intent-selected UserContext dump. Workload
        and alert mechanics stay as they were, and when a PsBundle is
        available its curriculum content is appended for grounded responses.

        Args:
            user_context: Rich user context — rendered through the projection
            ps_bundle: Optional PS bundle with curriculum content

        Returns:
            Natural language context string for LLM consumption
        """
        context_parts: list[str] = []

        if grounding := render_askesis_grounding(user_context):
            context_parts.append(grounding)

        # --- Workload & alert mechanics (kept as-is, ADR-082 D2) ---

        context_parts.append("\n--- Workload & Capacity ---")
        context_parts.append(f"Current Workload: {user_context.current_workload_score:.0%}")
        capacity_available = 100 - (user_context.current_workload_score * 100)
        context_parts.append(f"Capacity Available: {capacity_available:.0f}%")

        if user_context.is_blocked or user_context.is_overwhelmed:
            context_parts.append("\n--- Alerts ---")
            if user_context.is_blocked:
                context_parts.append("Blocked by prerequisites")
            if user_context.is_overwhelmed:
                context_parts.append("Workload overwhelming")

        # --- PS Bundle curriculum content ---
        if ps_bundle and ps_bundle.curriculum_context_text:
            context_parts.append("\n--- Curriculum Context ---")
            context_parts.append(ps_bundle.curriculum_context_text)

        from core.constants import AskesisTokenBudget
        from core.utils.text_truncation import truncate_to_budget

        return truncate_to_budget(
            "\n".join(context_parts), AskesisTokenBudget.MAX_LLM_CONTEXT_CHARS
        )

    # ========================================================================
    # GUIDED SYSTEM PROMPT GENERATION (absorbed from SocraticEngine)
    # ========================================================================

    def build_guided_system_prompt(
        self,
        guidance: GuidanceDetermination,
        ps_bundle: PsBundle,
        user_context: UserContext,
        canon_context: CanonContext | None = None,
    ) -> str:
        """Build a system prompt based on the guidance determination.

        Composition (ADR-082 D1/D2): authored stance + grounding projection +
        pedagogy leaf + canon block. The shared ``askesis_stance`` fragment
        (committed floor, founder-overridable like every registry template)
        heads the prompt; ``render_askesis_grounding`` supplies the learner
        block (skeleton contexts render nothing and the block is skipped);
        mode-specific builders supply the pedagogy leaf, with fine-grained
        variation based on guidance.pedagogical_detail.

        Args:
            guidance: GuidanceDetermination with mode and pedagogical detail
            ps_bundle: Complete PS bundle (scoped context)
            user_context: Rich user context — rendered through the explicit
                ASKESIS_GROUNDING_FIELDS projection, never dumped
            canon_context: PS-scoped canon readings (ADR-077) — its teaching
                block is appended to ground guidance in the step's cited
                readings; None or empty passages append nothing. Mode-aware
                framing (Codex #613 P2): DIRECT mode promises answers, so its
                block grounds the answer instead of instructing the model to
                ask a better question.

        Returns:
            System prompt string for the LLM call
        """
        from core.models.enums import GuidanceMode

        builders = {
            GuidanceMode.DIRECT: self._build_direct_prompt,
            GuidanceMode.SOCRATIC: self._build_socratic_prompt,
            GuidanceMode.EXPLORATORY: self._build_exploratory_prompt,
            GuidanceMode.ENCOURAGING: self._build_encouraging_prompt,
        }
        builder = builders.get(guidance.mode, self._build_direct_prompt)
        parts = [PROMPT_REGISTRY.render("askesis_stance")]
        if grounding := render_askesis_grounding(user_context):
            parts.append(grounding)
        parts.append(builder(guidance, ps_bundle))
        prompt = "\n\n".join(parts)
        if canon_context is not None:
            teaching_block = canon_context.to_teaching_block(  # "" when no passages
                preserve_method=guidance.mode is not GuidanceMode.DIRECT
            )
            if teaching_block:
                prompt += "\n\n" + teaching_block
        return prompt

    def _build_direct_prompt(
        self,
        guidance: GuidanceDetermination,
        ps_bundle: PsBundle,
    ) -> str:
        """DIRECT mode: redirect, out-of-scope, or user-overridden direct answers.

        Covers three cases:
        - REDIRECT_TO_CURRICULUM: learner hasn't engaged yet → point to reading
        - OUT_OF_SCOPE: question is outside the current PS → warm redirect
        - All other intents (user selected Direct mode override): answer directly
          from curriculum context without probing

        Templates: askesis_guided_redirect, askesis_guided_out_of_scope,
                   askesis_guided_direct
        """
        if guidance.pedagogical_detail == PedagogicalIntent.REDIRECT_TO_CURRICULUM:
            step_refs = []
            for ku_uid in guidance.target_ku_uids:
                step = ps_bundle.get_step_for_ku(ku_uid)
                if step:
                    step_refs.append(step.title or "Untitled Step")

            if not step_refs:
                step_refs = [a.title or "Untitled Step" for a in ps_bundle.related_steps]

            return PROMPT_REGISTRY.render(
                "askesis_guided_redirect",
                path_steps_text=", ".join(dict.fromkeys(step_refs)),
                resource_refs=self._get_resource_references(ps_bundle),
            )

        if guidance.pedagogical_detail == PedagogicalIntent.OUT_OF_SCOPE:
            return PROMPT_REGISTRY.render(
                "askesis_guided_out_of_scope",
                ls_title=ps_bundle.path_step.title or "your current step",
                ls_intent=ps_bundle.path_step.intent or "",
            )

        # User-selected Direct override for an in-scope intent (e.g. ASSESS_UNDERSTANDING,
        # SCAFFOLD, PROBE_DEEPER). Answer directly rather than pretending it's out-of-scope.
        return PROMPT_REGISTRY.render(
            "askesis_guided_direct",
            ls_title=ps_bundle.path_step.title or "your current step",
            ls_intent=ps_bundle.path_step.intent or "",
        )

    def _build_socratic_prompt(
        self,
        guidance: GuidanceDetermination,
        ps_bundle: PsBundle,
    ) -> str:
        """SOCRATIC mode: assess understanding or probe deeper.

        Covers ASSESS_UNDERSTANDING and PROBE_DEEPER pedagogical intents.
        Templates: askesis_guided_assess, askesis_guided_probe
        """
        concepts = ", ".join(self._get_ku_names(ps_bundle, guidance.target_ku_uids))

        if guidance.pedagogical_detail == PedagogicalIntent.ASSESS_UNDERSTANDING:
            return PROMPT_REGISTRY.render("askesis_guided_assess", concepts=concepts)

        # PROBE_DEEPER
        return PROMPT_REGISTRY.render("askesis_guided_probe", concepts=concepts)

    def _build_exploratory_prompt(
        self,
        guidance: GuidanceDetermination,
        ps_bundle: PsBundle,
    ) -> str:
        """EXPLORATORY mode: scaffold or surface connections.

        Covers SCAFFOLD and SURFACE_CONNECTION pedagogical intents.
        Templates: askesis_guided_scaffold, askesis_guided_connection
        """
        if guidance.pedagogical_detail == PedagogicalIntent.SCAFFOLD:
            concepts = ", ".join(self._get_ku_names(ps_bundle, guidance.target_ku_uids))
            return PROMPT_REGISTRY.render(
                "askesis_guided_scaffold",
                concepts=concepts,
                resource_refs=self._get_resource_references(ps_bundle),
            )

        # SURFACE_CONNECTION
        target_set = set(guidance.target_ku_uids)
        relevant_edges: list[dict] = []
        for edge in ps_bundle.edges:
            if isinstance(edge, dict):
                source = edge.get("source_uid", "")
                target = edge.get("target_uid", "")
                if source in target_set or target in target_set:
                    relevant_edges.append(edge)

        # Render each real lateral edge as a titled pair with its authored
        # evidence: "- Anchor —related to— Breath: <evidence>". An edge
        # authored without evidence renders the titled pair alone (no
        # dangling colon); an edge with no nameable endpoints is skipped —
        # a bare "- related to: " line grounds nothing.
        edge_lines: list[str] = []
        for edge in relevant_edges:
            source_name = edge.get("source_title") or edge.get("source_uid") or ""
            target_name = edge.get("target_title") or edge.get("target_uid") or ""
            if not source_name or not target_name:
                continue
            rel_type = edge.get("relationship_type") or RelationshipName.RELATED_TO.value
            rel_text = str(rel_type).replace("_", " ").lower()
            evidence = edge.get("evidence") or ""
            line = f"- {source_name} —{rel_text}— {target_name}"
            if evidence:
                line += f": {evidence}"
            edge_lines.append(line)

        return PROMPT_REGISTRY.render(
            "askesis_guided_connection",
            edges_text="\n".join(edge_lines) or "No specific evidence available.",
        )

    def _build_encouraging_prompt(
        self,
        guidance: GuidanceDetermination,
        ps_bundle: PsBundle,
    ) -> str:
        """ENCOURAGING mode: connect understanding to practice.

        Covers ENCOURAGE_PRACTICE pedagogical intent.
        Template: askesis_guided_practice
        """
        practice_items = []
        for habit in ps_bundle.habits:
            practice_items.append(f"Habit: {habit.title}")
        for task in ps_bundle.tasks:
            practice_items.append(f"Task: {task.title}")
        for event in ps_bundle.events:
            practice_items.append(f"Event: {event.title}")

        practice_text = (
            "\n".join(practice_items)
            if practice_items
            else "No specific practice activities linked."
        )

        return PROMPT_REGISTRY.render(
            "askesis_guided_practice",
            practice_text=practice_text,
            resource_refs=self._get_resource_references(ps_bundle),
        )

    # ========================================================================
    # PRIVATE - GUIDED PROMPT HELPERS
    # ========================================================================

    def _get_ku_names(self, ps_bundle: PsBundle, ku_uids: list[str]) -> list[str]:
        """Get KU titles for the given UIDs from the bundle."""
        names = []
        uid_set = set(ku_uids)
        for ku in ps_bundle.kus:
            if ku.uid in uid_set:
                names.append(ku.title or ku.uid)
        return names or ["(unknown concepts)"]

    @staticmethod
    def _get_resource_references(ps_bundle: PsBundle) -> str:
        """Format resource references for inclusion in guided prompts.

        Returns a compact summary of cited resources, or empty string if none.
        """
        if not ps_bundle.resources:
            return ""
        refs = [r.explain_existence() for r in ps_bundle.resources]
        return "\nReferenced resources: " + "; ".join(refs)

    def generate_actions(
        self,
        user_context: UserContext,
        intent: QueryIntent,
        relevant_context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        Generate suggested next actions based on context and intent.

        Args:
            user_context: Complete user context
            intent: Query intent
            relevant_context: Retrieved entities

        Returns:
            List of suggested actions with metadata
        """
        actions = []

        # Critical actions first (at_risk_habits is rich-context only)
        if at_risk := user_context.at_risk_habits_or_empty():
            actions.append(
                {
                    "priority": "critical",
                    "action": "reinforce_habits",
                    "description": f"Maintain {len(at_risk)} at-risk habits",
                    "entity_type": "habits",
                    "entity_count": len(at_risk),
                }
            )

        if user_context.overdue_task_uids:
            actions.append(
                {
                    "priority": "high",
                    "action": "complete_overdue",
                    "description": f"Complete {len(user_context.overdue_task_uids)} overdue tasks",
                    "entity_type": "tasks",
                    "entity_count": len(user_context.overdue_task_uids),
                }
            )

        # Intent-specific actions
        if intent == QueryIntent.PREREQUISITE and relevant_context.get("blocked_knowledge"):
            actions.append(
                {
                    "priority": "medium",
                    "action": "learn_prerequisites",
                    "description": "Focus on prerequisite knowledge to unblock learning",
                    "entity_type": "knowledge",
                    "entity_count": relevant_context["blocked_knowledge"],
                }
            )

        elif intent == QueryIntent.PRACTICE and user_context.active_task_uids:
            actions.append(
                {
                    "priority": "medium",
                    "action": "apply_knowledge",
                    "description": "Complete tasks to apply your knowledge",
                    "entity_type": "tasks",
                    "entity_count": len(user_context.active_task_uids),
                }
            )

        elif intent == QueryIntent.HIERARCHICAL and user_context.current_learning_path_uid:
            actions.append(
                {
                    "priority": "medium",
                    "action": "continue_learning_path",
                    "description": "Continue current learning path",
                    "entity_type": "learning_path",
                    "entity_uid": user_context.current_learning_path_uid,
                }
            )

        # Capacity-based actions
        if user_context.current_workload_score < 0.5:
            actions.append(
                {
                    "priority": "low",
                    "action": "add_challenge",
                    "description": "You have capacity for more challenging work",
                    "capacity_available": f"{(1 - user_context.current_workload_score) * 100:.0f}%",
                }
            )

        return actions[:5]  # Return top 5 actions

    def generate_suggested_actions(
        self, _query_message: str, context_data: dict[str, Any], intent: QueryIntent
    ) -> list[dict[str, Any]]:
        """
        Generate suggested actions based on context and intent.

        Args:
            _query_message: User's query (unused - for future use)
            context_data: Retrieved context
            intent: Query intent

        Returns:
            List of suggested actions
        """
        actions = []

        # Rows are ContextRetriever.get_learning_context's dicts ({"uid",
        # "title", ...}), not domain models — attribute access here crashed the
        # first time these branches ever ran (intent activation, 2026-08-31;
        # the classifier had only ever returned SPECIFIC before, so no call had
        # reached them).
        if intent == QueryIntent.HIERARCHICAL:
            learning_paths = context_data.get("learning_paths", [])
            if learning_paths:
                actions.append(
                    {
                        "action": "continue_learning_path",
                        "target": learning_paths[0].get("uid") or None,
                        "description": "Continue your current learning path",
                    }
                )

        elif intent == QueryIntent.PRACTICE:
            tasks = context_data.get("related_tasks", [])
            if tasks:
                actions.append(
                    {
                        "action": "complete_task",
                        "target": tasks[0].get("uid") or None,
                        "description": "Apply knowledge through practical task",
                    }
                )

        return actions
