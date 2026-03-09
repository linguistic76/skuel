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
    journal_activity              — Activity tracking formatter for JournalOutputGenerator
    journal_articulation          — Idea articulation formatter for JournalOutputGenerator
    journal_exploration           — Critical thinking formatter for JournalOutputGenerator
    dsl_domain_recognition        — Full domain recognition prompt for LLMDSLBridgeService
    dsl_domain_recognition_compact — Compact domain recognition prompt for LLMDSLBridgeService
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
