"""
Prompt Template
===============

Frozen dataclass representing a named LLM prompt template loaded from a .md file.

See: core/prompts/registry.py
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptTemplate:
    """Immutable prompt template loaded from a .md file.

    Args:
        template_id: Logical identifier (matches filename without .md extension)
        content: Raw template string, may contain {placeholder} substitution keys
    """

    template_id: str
    content: str

    def render(self, **kwargs: str) -> str:
        """Substitute placeholders and return the rendered prompt string.

        Args:
            **kwargs: Placeholder values (e.g. content="...", stats_json="...")

        Returns:
            Rendered prompt with all {placeholder} values substituted
        """
        return self.content.format(**kwargs)
