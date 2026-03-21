"""
Instruction Resolver
=====================

Unified instruction resolution for LLM processing.

Priority: custom_instructions > exercise > enrichment_mode > default (activity_tracking)

Maps enrichment modes to prompt registry templates. Returns OutputInstruction
with a prompt template containing {content} placeholder — the generator
substitutes actual content at call time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.ports.output_generator_protocols import OutputInstruction
from core.prompts import PROMPT_REGISTRY
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.exercises.exercise import Exercise

logger = get_logger("skuel.services.output.instruction_resolver")

# Enrichment mode → prompt template ID mapping
_MODE_TEMPLATE_MAP: dict[str, str] = {
    "activity_tracking": "journal_activity",
    "idea_articulation": "journal_articulation",
    "critical_thinking": "journal_exploration",
}

DEFAULT_ENRICHMENT_MODE = "activity_tracking"


class InstructionResolver:
    """
    Resolves processing instructions into a unified OutputInstruction.

    Priority:
        1. custom_instructions — user-provided text, used directly as prompt
        2. exercise — Exercise.instructions field with model/temp from Exercise
        3. enrichment_mode — maps to prompt registry template
        4. default — activity_tracking template
    """

    def resolve(
        self,
        enrichment_mode: str | None = None,
        custom_instructions: str | None = None,
        exercise: Exercise | None = None,
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_tokens: int = 4000,
    ) -> Result[OutputInstruction]:
        """
        Resolve processing instructions into an OutputInstruction.

        The returned prompt_text contains a {content} placeholder that the
        generator substitutes with actual content at call time.

        Args:
            enrichment_mode: Processing strategy name (maps to prompt template)
            custom_instructions: User-provided instruction text (highest priority)
            exercise: Exercise with instructions and model selection
            model: Default LLM model
            temperature: Default sampling temperature
            max_tokens: Default max tokens

        Returns:
            Result[OutputInstruction] with resolved prompt template
        """
        # Priority 1: custom instructions
        if custom_instructions:
            return Result.ok(
                OutputInstruction(
                    prompt_text=f"{custom_instructions}\n\n## Content to Process\n\n{{content}}",
                    source="custom",
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            )

        # Priority 2: exercise instructions
        if exercise:
            if not exercise.is_valid():
                return Result.fail(
                    Errors.validation("Invalid exercise: missing required fields", field="exercise")
                )
            # Exercise provides its own prompt via get_feedback_prompt()
            # Use {content} as placeholder — caller substitutes real content
            return Result.ok(
                OutputInstruction(
                    prompt_text="{content}",  # Sentinel — caller uses exercise.get_feedback_prompt()
                    source="exercise",
                    model=getattr(exercise, "model", model) or model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            )

        # Priority 3/4: enrichment mode or default
        mode = enrichment_mode or DEFAULT_ENRICHMENT_MODE
        template_id = _MODE_TEMPLATE_MAP.get(mode)

        if not template_id:
            logger.warning(f"Unknown enrichment mode '{mode}', falling back to activity_tracking")
            template_id = _MODE_TEMPLATE_MAP[DEFAULT_ENRICHMENT_MODE]

        # Render template with {content} placeholder
        # PROMPT_REGISTRY.render() replaces kwargs — we pass content="{content}"
        # so the returned string has literal {content} for later substitution
        prompt_text = PROMPT_REGISTRY.render(template_id, content="{content}")

        return Result.ok(
            OutputInstruction(
                prompt_text=prompt_text,
                source="template",
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        )


__all__ = ["InstructionResolver"]
