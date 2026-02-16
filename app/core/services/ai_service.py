"""
AI Service - Wrapper for OpenAI/Anthropic API calls
====================================================

Simple wrapper for AI completions used by:
- ContentEnrichmentService for intelligent editing
- JournalProjects for transparent feedback generation

Supports both OpenAI and Anthropic models.
"""

from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.services.ai")


class OpenAIService:
    """
    Simple OpenAI API wrapper for text generation.


    Source Tag: "ai_service_explicit"
    - Format: "ai_service_explicit" for user-created relationships
    - Format: "ai_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from ai metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (Phase 5 eliminated those)
    - Returns Result[T] for error handling
    - Logs operations with structured logging

    """

    def __init__(self, api_key: str) -> None:
        """
        Initialize OpenAI service.

        Args:
            api_key: OpenAI API key
        """
        self.api_key = api_key
        self.logger = logger

        try:
            import openai

            self.openai = openai
            self.client = openai.OpenAI(api_key=api_key)
            self.logger.info("OpenAI client initialized")
        except ImportError as e:
            self.logger.error("openai package not installed")
            raise ValueError("openai package required for AI service") from e

    async def generate_completion(
        self,
        prompt: str,
        max_tokens: int = 4000,
        temperature: float = 0.7,
        model: str = "gpt-4o-mini",
    ) -> Result[str]:
        """
        Generate completion from prompt.

        Args:
            prompt: Input prompt,
            max_tokens: Maximum tokens to generate,
            temperature: Sampling temperature (0-1),
            model: Model to use

        Returns:
            Result containing generated text
        """
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that formats journal transcripts.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )

            completion = response.choices[0].message.content

            # Defensive check: OpenAI might return None
            if completion is None:
                self.logger.error("OpenAI returned None as completion content")
                return Result.fail(
                    Errors.integration(
                        service="OpenAI",
                        operation="generate_completion",
                        message="API returned None as content",
                    )
                )

            self.logger.info(f"Generated completion: {len(completion)} chars")

            return Result.ok(completion)

        except Exception as e:
            self.logger.error(f"OpenAI API error: {e}")
            return Result.fail(
                Errors.integration(
                    service="OpenAI", operation="generate_completion", message=str(e)
                )
            )


class AnthropicService:
    """Simple Anthropic API wrapper for text generation."""

    def __init__(self, api_key: str) -> None:
        """
        Initialize Anthropic service.

        Args:
            api_key: Anthropic API key
        """
        self.api_key = api_key
        self.logger = logger

        try:
            import anthropic

            self.anthropic = anthropic
            self.client = anthropic.Anthropic(api_key=api_key)
            self.logger.info("Anthropic client initialized")
        except ImportError as e:
            self.logger.error("anthropic package not installed")
            raise ValueError("anthropic package required for Anthropic service") from e

    async def generate_completion(
        self,
        prompt: str,
        max_tokens: int = 4000,
        temperature: float = 0.7,
        model: str = "claude-3-5-sonnet-20241022",
    ) -> Result[str]:
        """
        Generate completion from prompt.

        Args:
            prompt: Input prompt,
            max_tokens: Maximum tokens to generate,
            temperature: Sampling temperature (0-1),
            model: Model to use (e.g., "claude-3-5-sonnet-20241022")

        Returns:
            Result containing generated text
        """
        try:
            response = self.client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            )

            completion = response.content[0].text

            self.logger.info(f"Generated completion: {len(completion)} chars")

            return Result.ok(completion)

        except Exception as e:
            self.logger.error(f"Anthropic API error: {e}")
            return Result.fail(
                Errors.integration(
                    service="Anthropic", operation="generate_completion", message=str(e)
                )
            )
