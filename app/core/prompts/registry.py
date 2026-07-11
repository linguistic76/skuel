"""
Prompt Registry
===============

Lazy-loading registry for LLM prompt templates stored in core/prompts/templates/.

Usage:
    from core.prompts import PROMPT_REGISTRY

    # Render a template directly
    prompt = PROMPT_REGISTRY.render("activity_feedback", time_period="7d", ...)

    # Get the template object (e.g. to access .content directly)
    template = PROMPT_REGISTRY.get("activity_feedback")

Available templates (core/prompts/templates/):
    activity_feedback             — Activity coaching feedback for ProgressReportGenerator
    journal_activity              — EnrichmentMode.ACTIVITY_TRACKING — structures daily activity entries (LLM_SUMMARY / TRANSCRIBE_AND_STRUCTURE pipelines)
    journal_articulation          — EnrichmentMode.IDEA_ARTICULATION — develops idea entries from raw transcripts
    journal_exploration           — EnrichmentMode.CRITICAL_THINKING — organizes critical thinking / exploration entries
    entry_response                — Reflective response to a journal entry (EntryReportService, ADR-069)
    dsl_domain_recognition        — Full domain recognition prompt for LLMDSLBridgeService
    dsl_domain_recognition_compact — Compact domain recognition prompt for LLMDSLBridgeService
    askesis_guided_redirect       — DIRECT/REDIRECT_TO_CURRICULUM system prompt
    askesis_guided_out_of_scope   — DIRECT/OUT_OF_SCOPE system prompt
    askesis_guided_assess         — SOCRATIC/ASSESS_UNDERSTANDING system prompt
    askesis_guided_probe          — SOCRATIC/PROBE_DEEPER system prompt
    askesis_guided_scaffold       — EXPLORATORY/SCAFFOLD system prompt
    askesis_guided_connection     — EXPLORATORY/SURFACE_CONNECTION system prompt
    askesis_guided_practice       — ENCOURAGING/ENCOURAGE_PRACTICE system prompt
    askesis_guided_direct         — DIRECT baseline system prompt
    askesis_journal_reflection    — Askesis journal-reflection turn
    askesis_ku_bridge             — Askesis Ku-bridge turn
    askesis_scaffold_entry        — Askesis scaffolded-entry turn
    askesis_socratic_turn         — Askesis Socratic turn
    prereq_edge_judge             — Ku-pair prerequisite classification (PrereqSuggestionService)
    entry_ku_grounding_judge      — Entry→Ku engagement filter (EntryGroundingService)
"""

from pathlib import Path

from core.prompts.prompt_template import PromptTemplate


class PromptRegistry:
    """Lazy-loading cache of PromptTemplate objects.

    Templates are loaded on first access and cached for the lifetime of the process.
    A missing template file raises FileNotFoundError immediately — missing templates
    are programming errors, not domain failures.
    """

    def __init__(self, templates_dir: Path) -> None:
        self._templates_dir = templates_dir
        self._cache: dict[str, PromptTemplate] = {}

    def get(self, template_id: str) -> PromptTemplate:
        """Lazy-load and cache a template by ID.

        Args:
            template_id: Logical name (maps to {template_id}.md in templates dir)

        Returns:
            Loaded and cached PromptTemplate

        Raises:
            FileNotFoundError: When the template file does not exist
        """
        if template_id not in self._cache:
            path = self._templates_dir / f"{template_id}.md"
            if not path.exists():
                raise FileNotFoundError(f"Prompt template not found: {template_id!r}")
            content = path.read_text(encoding="utf-8")
            self._cache[template_id] = PromptTemplate(template_id=template_id, content=content)
        return self._cache[template_id]

    def render(self, template_id: str, **kwargs: str) -> str:
        """Render a template with the given placeholder values.

        Convenience wrapper for get(template_id).render(**kwargs).

        Args:
            template_id: Logical name of the template
            **kwargs: Placeholder values

        Returns:
            Rendered prompt string
        """
        return self.get(template_id).render(**kwargs)


PROMPT_REGISTRY = PromptRegistry(Path(__file__).parent / "templates")
