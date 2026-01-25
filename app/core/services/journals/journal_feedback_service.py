"""
Journal Feedback Service
=========================

Generates transparent AI feedback for journal entries using Journal Projects.

Following SKUEL principles:
- Transparent: User sees exact prompt sent to LLM
- User-controlled: User provides instructions, selects model
- Simple: Instructions + content → LLM → feedback
- No black boxes: Everything is visible and editable

This service:
1. Takes a journal entry + project
2. Builds prompt from project instructions + entry content
3. Sends to LLM (user's choice of model)
4. Returns feedback
"""

from core.models.journal import JournalProjectPure, JournalPure
from core.services.ai_service import AnthropicService, OpenAIService
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


class JournalFeedbackService:
    """
    Generates AI feedback for journal entries using project instructions.

    Supports both OpenAI and Anthropic models.
    User selects which model to use via JournalProject.model field.


    Source Tag: "journal_feedback_service_explicit"
    - Format: "journal_feedback_service_explicit" for user-created relationships
    - Format: "journal_feedback_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from journal_feedback metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (Phase 5 eliminated those)
    - Returns Result[T] for error handling
    - Logs operations with structured logging

    """

    def __init__(
        self,
        openai_service: OpenAIService | None = None,
        anthropic_service: AnthropicService | None = None,
    ) -> None:
        """
        Initialize with AI services.

        Args:
            openai_service: OpenAI service (optional),
            anthropic_service: Anthropic service (optional)

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

        logger.info(f"JournalFeedbackService initialized with: {', '.join(available)}")

    async def generate_feedback(
        self,
        entry: JournalPure,
        project: JournalProjectPure,
        temperature: float = 0.7,
        max_tokens: int = 4000,
    ) -> Result[str]:
        """
        Generate AI feedback for a journal entry using project instructions.

        This is the core transparency: user's instructions + entry → LLM → feedback.

        Args:
            entry: Journal entry to analyze,
            project: Project with instructions and model selection,
            temperature: Sampling temperature (0-1, default 0.7),
            max_tokens: Maximum tokens to generate (default 4000)

        Returns:
            Result[str] containing the generated feedback
        """
        try:
            # Validate project
            if not project.is_valid():
                return Result.fail(
                    Errors.validation("Invalid project: missing required fields", field="project")
                )

            # Build prompt using project's transparent method
            prompt = project.get_feedback_prompt(entry.content)

            self.logger.info(
                f"Generating feedback for entry {entry.uid} using project {project.uid}"
            )
            self.logger.debug(f"Model: {project.model}, Prompt length: {len(prompt)} chars")

            # Route to appropriate AI service based on model
            if project.model.startswith("gpt"):
                # OpenAI model
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
                    model=project.model,
                )

            elif project.model.startswith("claude"):
                # Anthropic model
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
                    model=project.model,
                )

            else:
                return Result.fail(
                    Errors.validation(
                        f"Unknown model: {project.model}. Must start with 'gpt' or 'claude'",
                        field="model",
                    )
                )

            if result.is_error:
                self.logger.error(f"AI service error: {result.error}")
                return result

            feedback = result.value

            self.logger.info(f"✅ Feedback generated: {len(feedback)} chars")
            return Result.ok(feedback)

        except Exception as e:
            self.logger.error(f"Error generating feedback: {e}")
            return Result.fail(
                Errors.system(f"Feedback generation failed: {e!s}", operation="generate_feedback")
            )

    def get_supported_models(self) -> dict[str, list[str]]:
        """
        Get list of supported models by provider.

        Returns:
            Dict mapping provider to list of model names
        """
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
        """
        Check if a model is supported by available services.

        Args:
            model: Model name to check

        Returns:
            True if supported, False otherwise
        """
        if model.startswith("gpt") and self.openai:
            return True
        return bool(model.startswith("claude") and self.anthropic)
