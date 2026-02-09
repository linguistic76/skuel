"""
Journal Mode Classifier
=======================

LLM-based classification of journal entries into processing modes.

Infers weight distribution (activity, articulation, exploration) to determine
appropriate formatting and extraction strategies.
"""

import json
from pathlib import Path

from core.services.ai_service import OpenAIService
from core.services.journals.journal_types import JournalWeights
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.services.journals.classifier")


class JournalModeClassifier:
    """
    Classifies journal entries using LLM to infer mode weights.

    Uses OpenAI to analyze content and return weight distribution across:
    - Activity tracking (actionable items, DSL tags)
    - Idea articulation (conceptual exploration)
    - Critical thinking (questions, brainstorming)
    """

    def __init__(self, openai_service: OpenAIService) -> None:
        """
        Initialize classifier with OpenAI service.

        Args:
            openai_service: OpenAI service for LLM calls
        """
        self.openai_service = openai_service
        self.logger = logger

        # Load classification prompt
        prompt_path = Path(__file__).parent / "prompts" / "mode_classification.md"
        self.classification_prompt = prompt_path.read_text()

    async def infer_weights(
        self, content: str, user_declared_mode: str | None = None
    ) -> Result[JournalWeights]:
        """
        Infer mode weights from journal content using LLM.

        If user declared mode upfront, use that as primary (0.8 weight).
        Otherwise, infer from content analysis.

        Args:
            content: Journal entry text to classify
            user_declared_mode: Optional user-declared primary mode

        Returns:
            Result containing JournalWeights with inferred distribution
        """
        # If user declared mode, use 80/10/10 distribution
        if user_declared_mode:
            return self._apply_declared_mode(user_declared_mode)

        # Otherwise, use LLM inference
        return await self._infer_from_content(content)

    def _apply_declared_mode(self, declared_mode: str) -> Result[JournalWeights]:
        """Apply user-declared mode as primary (80% weight)."""
        mode_map = {
            "activity": JournalWeights.activity_dominant(),
            "articulation": JournalWeights.articulation_dominant(),
            "exploration": JournalWeights.exploration_dominant(),
        }

        weights = mode_map.get(declared_mode.lower())
        if not weights:
            return Result.fail(
                Errors.validation(
                    message=f"Invalid declared mode: {declared_mode}",
                    field="user_declared_mode",
                    value=declared_mode,
                )
            )

        self.logger.info(f"Using declared mode '{declared_mode}': {weights.to_dict()}")
        return Result.ok(weights)

    async def _infer_from_content(self, content: str) -> Result[JournalWeights]:
        """Infer weights from content using LLM analysis."""
        self.logger.info(f"Inferring mode weights from content ({len(content)} chars)")

        # Build prompt with content
        prompt = self.classification_prompt.format(content=content)

        # Call OpenAI for classification
        try:
            response = await self.openai_service.generate_completion(
                prompt=prompt,
                temperature=0.3,  # Lower temperature for consistent classification
                max_tokens=150,  # Small response (just JSON)
            )

            if response.is_error:
                return Result.fail(response.expect_error())

            # Parse JSON response
            response_text = response.value.strip()

            # Handle markdown code blocks if present
            if response_text.startswith("```json"):
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif response_text.startswith("```"):
                response_text = response_text.split("```")[1].split("```")[0].strip()

            classification = json.loads(response_text)

            # Extract weights
            activity = float(classification.get("activity", 0.33))
            articulation = float(classification.get("articulation", 0.33))
            exploration = float(classification.get("exploration", 0.34))
            reasoning = classification.get("reasoning", "No reasoning provided")

            # Normalize to ensure sum = 1.0
            total = activity + articulation + exploration
            if total > 0:
                activity = activity / total
                articulation = articulation / total
                exploration = exploration / total

            weights = JournalWeights(
                activity=activity,
                articulation=articulation,
                exploration=exploration,
            )

            self.logger.info(f"Inferred weights: {weights.to_dict()} - {reasoning}")
            return Result.ok(weights)

        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse LLM response as JSON: {e}")
            # Fallback to balanced weights
            return Result.ok(JournalWeights.balanced())

        except ValueError as e:
            self.logger.error(f"Invalid weight values from LLM: {e}")
            # Fallback to balanced weights
            return Result.ok(JournalWeights.balanced())

        except Exception as e:
            return Result.fail(
                Errors.system(
                    message=f"Classification failed: {e}",
                    operation="infer_weights",
                    exception=e,
                )
            )

    def get_threshold_from_instructions(self, instructions: dict[str, any] | None) -> float:
        """
        Extract processing threshold from ReportProject instructions.

        Default threshold: 0.2 (20%)
        Configurable via instructions: {"mode_threshold": 0.3}

        Args:
            instructions: Optional ReportProject instructions dict

        Returns:
            Threshold value (0.0-1.0)
        """
        if not instructions:
            return 0.2

        threshold = instructions.get("mode_threshold", 0.2)

        # Validate threshold is reasonable
        if not isinstance(threshold, int | float):
            self.logger.warning(f"Invalid threshold type: {type(threshold)}, using 0.2")
            return 0.2

        if not (0.0 <= threshold <= 1.0):
            self.logger.warning(f"Invalid threshold value: {threshold}, using 0.2")
            return 0.2

        return float(threshold)
