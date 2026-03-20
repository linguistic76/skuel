"""
Output Generator Protocols
============================

Standardizes how content is sent through LLM processing.

OutputInstruction: resolved instruction for LLM processing (immutable).
OutputGeneratorOperations: protocol for LLM-only content generation (no persistence).

See: core/services/output/instruction_resolver.py for instruction resolution logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

from core.utils.result_simplified import Result


@dataclass(frozen=True)
class OutputInstruction:
    """Resolved instruction for LLM processing."""

    prompt_text: str
    source: Literal["template", "custom", "exercise"] = "template"
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 4000


class OutputGeneratorOperations(Protocol):
    """Protocol for LLM-based content generation. No persistence — pure transform."""

    async def generate_output(
        self,
        content: str,
        instruction: OutputInstruction,
    ) -> Result[str]:
        """Generate formatted text from content + instruction."""
        ...


__all__ = ["OutputGeneratorOperations", "OutputInstruction"]
