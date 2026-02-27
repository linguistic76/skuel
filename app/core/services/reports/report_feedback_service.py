"""
Report Feedback Service
========================

Generates transparent AI feedback for report entries using Exercises.

Following SKUEL principles:
- Transparent: User sees exact prompt sent to LLM
- User-controlled: User provides instructions, selects model
- Simple: Instructions + content -> LLM -> feedback
"""

from core.models.curriculum.exercise import Exercise
from core.models.reports.submission import Submission
from core.services.ai_service import AnthropicService, OpenAIService
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


class ReportsFeedbackService:
    """
    Generates AI feedback for report entries using exercise instructions.

    Supports both OpenAI and Anthropic models.
    User selects which model to use via Exercise.model field.
    """

    def __init__(
        self,
        openai_service: OpenAIService | None = None,
        anthropic_service: AnthropicService | None = None,
    ) -> None:
        """
        Initialize with AI services.

        At least one service must be provided.
        """
        if not openai_service and not anthropic_service:
            raise ValueError("At least one AI service (OpenAI or Anthropic) must be provided")

        self.openai = openai_service
        self.anthropic = anthropic_service
        self.logger = logger

        available = []
        if self.openai:
            available.append("OpenAI")
        if self.anthropic:
            available.append("Anthropic")

        logger.info(f"ReportsFeedbackService initialized with: {', '.join(available)}")

    async def generate_feedback(
        self,
        entry: Submission,
        exercise: Exercise,
        temperature: float = 0.7,
        max_tokens: int = 4000,
    ) -> Result[str]:
        """
        Generate AI feedback for a report entry using exercise instructions.

        Args:
            entry: Submission to analyze (uses content or processed_content)
            exercise: Exercise with instructions and model selection
            temperature: Sampling temperature (0-1, default 0.7)
            max_tokens: Maximum tokens to generate (default 4000)

        Returns:
            Result[str] containing the generated feedback
        """
        try:
            if not exercise.is_valid():
                return Result.fail(
                    Errors.validation("Invalid exercise: missing required fields", field="exercise")
                )

            entry_content = entry.content or entry.processed_content or ""
            if not entry_content:
                return Result.fail(
                    Errors.validation("Submission has no content for feedback", field="content")
                )

            prompt = exercise.get_feedback_prompt(entry_content)

            self.logger.info(
                f"Generating feedback for entry {entry.uid} using exercise {exercise.uid}"
            )
            self.logger.debug(f"Model: {exercise.model}, Prompt length: {len(prompt)} chars")

            if exercise.model.startswith("gpt"):
                if not self.openai:
                    return Result.fail(
                        Errors.integration(
                            service="OpenAI",
                            operation="generate_feedback",
                            message="OpenAI service not configured, but GPT model requested",
                        )
                    )
                result = await self.openai.generate_completion(
                    prompt=prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    model=exercise.model,
                )

            elif exercise.model.startswith("claude"):
                if not self.anthropic:
                    return Result.fail(
                        Errors.integration(
                            service="Anthropic",
                            operation="generate_feedback",
                            message="Anthropic service not configured, but Claude model requested",
                        )
                    )
                result = await self.anthropic.generate_completion(
                    prompt=prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    model=exercise.model,
                )

            else:
                return Result.fail(
                    Errors.validation(
                        f"Unknown model: {exercise.model}. Must start with 'gpt' or 'claude'",
                        field="model",
                    )
                )

            if result.is_error:
                self.logger.error(f"AI service error: {result.error}")
                return result

            feedback = result.value
            self.logger.info(f"Feedback generated: {len(feedback)} chars")
            return Result.ok(feedback)

        except Exception as e:
            self.logger.error(f"Error generating feedback: {e}")
            return Result.fail(
                Errors.system(f"Feedback generation failed: {e!s}", operation="generate_feedback")
            )

    def get_supported_models(self) -> dict[str, list[str]]:
        """Get list of supported models by provider."""
        models = {}
        if self.openai:
            models["openai"] = ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"]
        if self.anthropic:
            models["anthropic"] = [
                "claude-3-5-sonnet-20241022",
                "claude-3-5-haiku-20241022",
                "claude-3-opus-20240229",
                "claude-3-sonnet-20240229",
                "claude-3-haiku-20240307",
            ]
        return models

    def is_model_supported(self, model: str) -> bool:
        """Check if a model is supported by available services."""
        if model.startswith("gpt") and self.openai:
            return True
        return bool(model.startswith("claude") and self.anthropic)
