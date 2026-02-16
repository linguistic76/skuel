"""
Journals Service Package
=========================

Journal output generation with three formatting strategies:
- Activity: Structured with DSL tags preserved
- Articulation: Verbatim with formatting improvements
- Exploration: Question-organized

Enrichment mode is explicitly defined in Assignment processing instructions,
not inferred by LLM classification.
"""

from core.services.journals.journal_output_generator import JournalOutputGenerator

__all__ = [
    "JournalOutputGenerator",
]
