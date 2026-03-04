"""
core.prompts — Centralized Prompt Template Registry
=====================================================

Single source of truth for all LLM prompt templates used across SKUEL services.

Templates are stored as Markdown files in core/prompts/templates/ and loaded
lazily on first access. The PROMPT_REGISTRY singleton is the one-and-only
import consumers need.

Usage:
    from core.prompts import PROMPT_REGISTRY

    prompt = PROMPT_REGISTRY.render("activity_feedback", time_period="7d", ...)
    template = PROMPT_REGISTRY.get("journal_activity")
"""

from core.prompts.prompt_template import PromptTemplate
from core.prompts.registry import PROMPT_REGISTRY

__all__ = ["PromptTemplate", "PROMPT_REGISTRY"]
