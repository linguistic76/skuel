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

Founder-local override (ADR-082 D1): every template id resolves an optional
``data/instructions/{template_id}.md`` BEFORE the committed template — the
ADR-081 authoring approach (committed floor + founder-local override) at the
registry chokepoint. Absence is the normal state; a blank override degrades
to the committed floor; the shared containment guard blocks traversal.

Available templates (core/prompts/templates/):
    activity_feedback             — Activity coaching feedback for ProgressReportGenerator
    journal_activity              — EnrichmentMode.ACTIVITY_TRACKING — structures daily activity entries (LLM_SUMMARY / TRANSCRIBE_AND_STRUCTURE pipelines)
    journal_articulation          — EnrichmentMode.IDEA_ARTICULATION — develops idea entries from raw transcripts
    journal_exploration           — EnrichmentMode.CRITICAL_THINKING — organizes critical thinking / exploration entries
    entry_response                — Reflective response to a journal entry (EntryReportService, ADR-069)
    dsl_domain_recognition        — Full domain recognition prompt for LLMDSLBridgeService
    dsl_domain_recognition_compact — Compact domain recognition prompt for LLMDSLBridgeService
    askesis_stance                — Shared Askesis study-buddy stance — heads BOTH answer branches (ADR-082 D1/D3)
    askesis_tool_selection        — Aggregation tool-selection system prompt (tool-selection first slice)
    askesis_guided_redirect       — DIRECT/REDIRECT_TO_CURRICULUM system prompt
    askesis_guided_out_of_scope   — DIRECT/OUT_OF_SCOPE system prompt
    askesis_guided_assess         — SOCRATIC/ASSESS_UNDERSTANDING system prompt
    askesis_guided_probe          — SOCRATIC/PROBE_DEEPER system prompt
    askesis_guided_scaffold       — EXPLORATORY/SCAFFOLD system prompt
    askesis_guided_connection     — EXPLORATORY/SURFACE_CONNECTION system prompt
    askesis_guided_practice       — ENCOURAGING/ENCOURAGE_PRACTICE system prompt
    askesis_guided_direct         — DIRECT baseline system prompt
    askesis_journal_reflection    — Askesis journal-reflection turn (staged — PLANNED, ADR-082 D4)
    askesis_ku_bridge             — Askesis Ku-bridge turn (staged — PLANNED, ADR-082 D4)
    askesis_scaffold_entry        — Askesis scaffolded-entry turn (staged — PLANNED, ADR-082 D4)
    askesis_socratic_turn         — Askesis Socratic turn (staged — PLANNED, ADR-082 D4)
    prereq_edge_judge             — Ku-pair prerequisite classification (PrereqSuggestionService)
    entry_ku_grounding_judge      — Entry→Ku engagement filter (EntryGroundingService)
"""

import string
from pathlib import Path

from core.prompts.prompt_template import PromptTemplate
from core.utils.instruction_files import INSTRUCTIONS_DIR, load_optional_override
from core.utils.logging import get_logger

_logger = get_logger("skuel.prompts.registry")


def _format_fields(content: str) -> set[str] | None:
    """Root placeholder names ``str.format`` would look up in ``content``.

    ``None`` when the content is not a valid format string (stray unmatched
    brace) — rendering it would raise, so callers treat it as unusable.
    """
    try:
        return {
            field_name.split(".")[0].split("[")[0]
            for _, field_name, _, _ in string.Formatter().parse(content)
            if field_name is not None
        }
    except ValueError:
        return None


class PromptRegistry:
    """Lazy-loading cache of PromptTemplate objects with a founder-local override layer.

    Committed templates are loaded on first access and cached for the lifetime
    of the process. A missing template file raises FileNotFoundError immediately —
    missing templates are programming errors, not domain failures.

    Override resolution (ADR-082 D1): ``get()`` first reads an optional
    ``{overrides_dir}/{template_id}.md`` — present and non-blank replaces the
    committed template; absent or blank falls through to the committed floor.
    Overrides are read fresh on every access (never cached) so founder edits
    land without a restart. An override must preserve the template's
    ``{placeholder}`` keys — it replaces the words, not the render contract:
    one whose placeholder set differs from the committed floor's (or that is
    not a valid format string) degrades to the floor with a warning, because
    ``str.format`` ignores extra kwargs and a missing placeholder would
    silently drop the context the caller computed.
    """

    def __init__(self, templates_dir: Path, overrides_dir: Path | None = None) -> None:
        self._templates_dir = templates_dir
        self._overrides_dir = INSTRUCTIONS_DIR if overrides_dir is None else overrides_dir
        self._cache: dict[str, PromptTemplate] = {}

    def get(self, template_id: str) -> PromptTemplate:
        """Resolve a template by ID — founder-local override first, committed floor second.

        Args:
            template_id: Logical name (maps to {template_id}.md in the overrides
                dir, then the templates dir)

        Returns:
            PromptTemplate — a fresh object when a contract-preserving override
            serves (never cached), the cached committed template otherwise

        Raises:
            FileNotFoundError: When the committed template file does not exist
                (the floor is guaranteed; an override never substitutes for it)
        """
        committed = self._get_committed(template_id)
        override = load_optional_override(self._overrides_dir, f"{template_id}.md")
        if override is not None and self._preserves_render_contract(
            template_id, committed.content, override
        ):
            return PromptTemplate(template_id=template_id, content=override)
        return committed

    def _get_committed(self, template_id: str) -> PromptTemplate:
        if template_id not in self._cache:
            path = self._templates_dir / f"{template_id}.md"
            if not path.exists():
                raise FileNotFoundError(f"Prompt template not found: {template_id!r}")
            content = path.read_text(encoding="utf-8")
            self._cache[template_id] = PromptTemplate(template_id=template_id, content=content)
        return self._cache[template_id]

    @staticmethod
    def _preserves_render_contract(template_id: str, committed: str, override: str) -> bool:
        """True when the override keeps the committed floor's placeholder set."""
        override_fields = _format_fields(override)
        if override_fields is None:
            _logger.warning(
                "Override for %r is not a valid format string — serving the committed floor",
                template_id,
            )
            return False
        committed_fields = _format_fields(committed)
        if override_fields != committed_fields:
            _logger.warning(
                "Override for %r changes the placeholder set (%s vs committed %s) — "
                "serving the committed floor",
                template_id,
                sorted(override_fields),
                sorted(committed_fields or ()),
            )
            return False
        return True

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
