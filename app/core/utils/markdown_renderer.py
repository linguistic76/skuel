"""
Markdown Renderer - Server-side markdown to HTML conversion.

Provides consistent markdown rendering for documentation pages
using Python's markdown library with useful extensions.
"""

from functools import lru_cache

import markdown

from core.utils.logging import get_logger

logger = get_logger("skuel.markdown_renderer")


class MarkdownRenderer:
    """
    Server-side markdown to HTML converter.

    Uses Python markdown library with extensions for:
    - Fenced code blocks (```)
    - Tables
    - Table of contents generation
    - Smart lists
    """

    def __init__(self) -> None:
        self.md = markdown.Markdown(
            extensions=[
                "fenced_code",  # Code blocks with ```
                "tables",  # Table support
                "toc",  # Table of contents
                "nl2br",  # Newlines to <br>
                "sane_lists",  # Better list handling
                "attr_list",  # Add attributes to elements
            ],
            extension_configs={
                "toc": {
                    "title": "Contents",
                    "toc_depth": "2-4",
                }
            },
        )

    def render(self, content: str) -> tuple[str, str]:
        """
        Convert markdown to HTML.

        Args:
            content: Markdown string

        Returns:
            Tuple of (html_content, toc_html)
        """
        if not content:
            return "", ""

        try:
            html = self.md.convert(content)
            toc = getattr(self.md, "toc", "")
            self.md.reset()  # Reset state for next conversion
            return html, toc
        except Exception as e:
            logger.error(f"Markdown rendering failed: {e}")
            # Return escaped content as fallback
            return f"<pre>{content}</pre>", ""

    def render_simple(self, content: str) -> str:
        """
        Convert markdown to HTML without TOC.

        Args:
            content: Markdown string

        Returns:
            HTML string
        """
        html, _ = self.render(content)
        return html


# Singleton instance for reuse
_renderer: MarkdownRenderer | None = None


def get_markdown_renderer() -> MarkdownRenderer:
    """Get or create the markdown renderer singleton."""
    global _renderer
    if _renderer is None:
        _renderer = MarkdownRenderer()
    return _renderer


@lru_cache(maxsize=100)
def render_markdown(content: str) -> str:
    """
    Cached markdown rendering for simple use cases.

    Args:
        content: Markdown string

    Returns:
        HTML string
    """
    renderer = get_markdown_renderer()
    return renderer.render_simple(content)


@lru_cache(maxsize=50)
def render_markdown_with_toc(content: str) -> tuple[str, str]:
    """
    Cached markdown rendering with table of contents.

    Args:
        content: Markdown string

    Returns:
        Tuple of (html_content, toc_html)
    """
    renderer = get_markdown_renderer()
    return renderer.render(content)
