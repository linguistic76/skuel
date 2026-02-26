"""
LLM Service for Natural Language Generation
============================================

Provides LLM integration for Askesis and other services.
Supports multiple LLM providers (OpenAI, Anthropic, local models).
"""

__version__ = "1.0"


import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any

from core.config import get_openai_key
from core.errors import ConfigurationError
from core.ports.base_protocols import EnumLike

logger = logging.getLogger(__name__)


class LLMProvider(str, Enum):
    """Supported LLM providers"""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    LOCAL = "local"
    MOCK = "mock"


@dataclass
class LLMConfig:
    """Configuration for LLM service"""

    provider: LLMProvider = LLMProvider.MOCK
    api_key: str | None = None
    model_name: str = "gpt-3.5-turbo"
    temperature: float = 0.7
    max_tokens: int = 500
    system_prompt: str | None = None


@dataclass
class LLMResponse:
    """Response from LLM"""

    content: str
    provider: LLMProvider
    model: str
    usage: dict[str, int] | None = None
    error: str | None = None


class LLMService:
    """
    Service for interacting with Large Language Models.


    Source Tag: "llm_service_explicit"
    - Format: "llm_service_explicit" for user-created relationships
    - Format: "llm_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from llm metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (uses pure Cypher)
    - Returns Result[T] for error handling
    - Logs operations with structured logging

    """

    def __init__(self, config: LLMConfig | None = None) -> None:
        """
        Initialize LLM service with configuration.

        Args:
            config: LLM configuration
        """
        self.config = config or LLMConfig()
        self._initialize_provider()

    def _initialize_provider(self) -> None:
        """Initialize the LLM provider based on config."""
        if self.config.provider == LLMProvider.OPENAI:
            self._init_openai()
        elif self.config.provider == LLMProvider.ANTHROPIC:
            self._init_anthropic()
        elif self.config.provider == LLMProvider.LOCAL:
            self._init_local()
        else:
            # Mock provider for testing
            logger.info("Using mock LLM provider")

    def _init_openai(self) -> None:
        """Initialize OpenAI client."""
        try:
            from openai import AsyncOpenAI

            # Use provided key or get from centralized config
            api_key = self.config.api_key
            if not api_key:
                try:
                    api_key = get_openai_key()
                except ConfigurationError:
                    # For LLM service, we'll raise since OpenAI is required when selected
                    raise

            # Create modern OpenAI client (v1.x+)
            self.client = AsyncOpenAI(api_key=api_key)
            logger.info("OpenAI LLM provider initialized (modern API v1.x+)")
        except ImportError:
            logger.warning("OpenAI library not installed, falling back to mock")
            self.config.provider = LLMProvider.MOCK

    def _init_anthropic(self) -> None:
        """Initialize Anthropic client."""
        try:
            import anthropic

            self.client = anthropic.Anthropic(
                api_key=self.config.api_key or os.getenv("ANTHROPIC_API_KEY")
            )
            logger.info("Anthropic LLM provider initialized")
        except ImportError:
            logger.warning("Anthropic library not installed, falling back to mock")
            self.config.provider = LLMProvider.MOCK

    def _init_local(self) -> None:
        """Initialize local model (e.g., Ollama)."""
        logger.info("Local LLM provider initialized")
        # Would connect to local model server

    async def generate(
        self,
        prompt: str,
        context: str | None = None,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """
        Generate text using the LLM.

        Args:
            prompt: The user prompt,
            context: Additional context,
            system_prompt: System instructions,
            temperature: Sampling temperature,
            max_tokens: Maximum tokens to generate

        Returns:
            LLM response
        """
        # Use provided values or defaults from config
        system_prompt = system_prompt or self.config.system_prompt
        temperature = temperature or self.config.temperature
        max_tokens = max_tokens or self.config.max_tokens

        # Combine context with prompt if provided
        full_prompt = prompt
        if context:
            full_prompt = f"Context: {context}\n\nQuery: {prompt}"

        # Generate based on provider
        if self.config.provider == LLMProvider.OPENAI:
            return await self._generate_openai(full_prompt, system_prompt, temperature, max_tokens)
        elif self.config.provider == LLMProvider.ANTHROPIC:
            return await self._generate_anthropic(
                full_prompt, system_prompt, temperature, max_tokens
            )
        elif self.config.provider == LLMProvider.LOCAL:
            return await self._generate_local(full_prompt, system_prompt, temperature, max_tokens)
        else:
            return await self._generate_mock(full_prompt, system_prompt)

    async def _generate_openai(
        self, prompt: str, system_prompt: str | None, temperature: float, max_tokens: int
    ) -> LLMResponse:
        """Generate using OpenAI API (modern v1.x+ syntax)."""
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            # Modern OpenAI API (v1.x+)
            response = await self.client.chat.completions.create(
                model=self.config.model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            return LLMResponse(
                content=response.choices[0].message.content,
                provider=LLMProvider.OPENAI,
                model=self.config.model_name,
                usage=response.usage.model_dump() if response.usage else None,
            )
        except Exception as e:
            logger.error(f"OpenAI generation failed: {e}")
            return LLMResponse(
                content="", provider=LLMProvider.OPENAI, model=self.config.model_name, error=str(e)
            )

    async def _generate_anthropic(
        self, prompt: str, system_prompt: str | None, temperature: float, max_tokens: int
    ) -> LLMResponse:
        """Generate using Anthropic API."""
        try:
            message = self.client.messages.create(
                model=self.config.model_name,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt or "",
                messages=[{"role": "user", "content": prompt}],
            )

            return LLMResponse(
                content=message.content[0].text,
                provider=LLMProvider.ANTHROPIC,
                model=self.config.model_name,
            )
        except Exception as e:
            logger.error(f"Anthropic generation failed: {e}")
            return LLMResponse(
                content="",
                provider=LLMProvider.ANTHROPIC,
                model=self.config.model_name,
                error=str(e),
            )

    async def _generate_local(
        self, prompt: str, system_prompt: str | None, _temperature: float, _max_tokens: int
    ) -> LLMResponse:
        """Generate using local model."""
        # Would call local model API
        return await self._generate_mock(prompt, system_prompt)

    async def _generate_mock(self, prompt: str, _system_prompt: str | None) -> LLMResponse:
        """Generate mock response for testing."""
        # Create a reasonable mock response based on the prompt
        prompt_lower = prompt.lower()

        if "what" in prompt_lower or "explain" in prompt_lower:
            content = f"Based on your question about '{prompt[:50]}...', here's what I found:\n\n"
            content += "This is a comprehensive topic that involves several key concepts. "
            content += "The main aspects include understanding the fundamentals, "
            content += (
                "practicing the implementation, and applying the knowledge in real scenarios.\n\n"
            )
            content += "Would you like me to elaborate on any specific aspect?"

        elif "how" in prompt_lower:
            content = f"To accomplish '{prompt[:50]}...', follow these steps:\n\n"
            content += "1. Start by understanding the basic concepts\n"
            content += "2. Practice with simple examples\n"
            content += "3. Gradually increase complexity\n"
            content += "4. Apply the knowledge to real problems\n\n"
            content += "Each step builds upon the previous one for effective learning."

        elif "search" in prompt_lower or "find" in prompt_lower:
            content = "I found several relevant items for your search:\n\n"
            content += "• First result: A comprehensive guide on the topic\n"
            content += "• Second result: Practical examples and exercises\n"
            content += "• Third result: Advanced techniques and best practices\n\n"
            content += "These resources should help you explore the topic thoroughly."

        else:
            content = f"Regarding '{prompt[:50]}...', "
            content += "this is an interesting topic to explore. "
            content += "The key is to approach it systematically, starting with the fundamentals "
            content += "and progressively building your understanding. "
            content += "Practice and application are essential for mastery."

        return LLMResponse(content=content, provider=LLMProvider.MOCK, model="mock-model")

    async def generate_for_askesis(
        self,
        query: str,
        search_results: list[dict] | None = None,
        conversation_history: list[dict] | None = None,
        intent: str | None = None,
    ) -> str:
        """
        Generate a response specifically for Askesis chat.

        Args:
            query: User's query,
            search_results: Search results to incorporate,
            conversation_history: Previous messages,
            intent: Detected user intent

        Returns:
            Generated response text
        """
        # Build context from search results
        context = ""
        if search_results:
            context = "Search Results:\n"
            for i, result in enumerate(search_results[:3], 1):
                if isinstance(result, dict):
                    title = result.get("title", "Untitled")
                    summary = result.get("summary", result.get("description", ""))
                    context += f"{i}. {title}: {summary}\n"

        # Build conversation context
        if conversation_history:
            context += "\n\nConversation History:\n"
            for msg in conversation_history[-3:]:  # Last 3 messages
                role = msg.get("role", "unknown")
                content = msg.get("content", "")[:100]
                context += f"{role}: {content}...\n"

        # Create system prompt based on intent
        system_prompt = self._get_askesis_system_prompt(intent)

        # Generate response
        response = await self.generate(
            prompt=query, context=context, system_prompt=system_prompt, temperature=0.7
        )

        if response.error:
            return f"I understand you're asking about '{query}'. Let me help you explore this topic based on the available information."

        return response.content

    async def generate_context_aware_answer(
        self,
        query: str,
        user_context: str,
        additional_context: dict | None = None,
        intent: Any | None = None,
    ) -> str:
        """
        Generate context-aware answer using full user state.

        This is the RAG generation method that combines rich user context
        from UserContext with LLM generation.

        Args:
            query: User's question,
            user_context: Rich natural language context from _build_llm_context_from_user_context(),
            additional_context: Optional additional entities/metadata,
            intent: Query intent (from QueryIntent enum)

        Returns:
            Natural language answer leveraging user's actual data
        """
        # Build comprehensive system prompt
        system_prompt = self._build_context_aware_system_prompt(
            user_context, additional_context, intent
        )

        # Generate response using full context
        response = await self.generate(
            prompt=query,
            system_prompt=system_prompt,
            temperature=0.7,
            max_tokens=500,
        )

        if response.error:
            # Fallback to structured response if LLM fails
            return (
                f"Based on your question about '{query}', here's what I can tell you:\n\n"
                f"{user_context}\n\n"
                f"Please let me know if you'd like more specific information."
            )

        return response.content

    def _build_context_aware_system_prompt(
        self, user_context: str, additional_context: dict | None, intent: Any | None
    ) -> str:
        """Build rich system prompt that includes user context."""
        # Base prompt
        prompt_parts = [
            "You are Askesis, an intelligent learning assistant with complete awareness",
            "of the user's current state. Use this context to provide personalized,",
            "specific answers that reference their actual data.",
            "",
            "=== USER'S CURRENT STATE ===",
            user_context,
            "",
        ]

        # Add additional context if provided
        if additional_context:
            prompt_parts.append("=== ADDITIONAL CONTEXT ===")
            prompt_parts.append(self._format_additional_context(additional_context))
            prompt_parts.append("")

        # Add intent-specific guidance
        if intent:
            intent_str = str(intent.value) if isinstance(intent, EnumLike) else str(intent)
            prompt_parts.append("=== QUERY TYPE ===")
            prompt_parts.append(f"The user is asking a {intent_str} question.")
            prompt_parts.append("")

        # Add response guidelines
        prompt_parts.extend(
            [
                "=== RESPONSE GUIDELINES ===",
                "1. Reference SPECIFIC data from the user's context (numbers, UIDs, etc.)",
                "2. Be conversational and natural - avoid robotic responses",
                "3. Provide actionable insights when appropriate",
                "4. Keep answers concise (2-4 paragraphs)",
                "5. If the user has critical issues (overdue tasks, at-risk habits), mention them",
                "",
                "Now answer the user's question using their actual data:",
            ]
        )

        return "\n".join(prompt_parts)

    def _format_additional_context(self, additional_context: dict) -> str:
        """
        Format additional context dict into readable text for LLM.

        Args:
            additional_context: Dict of context metadata

        Returns:
            Formatted context string
        """
        if not additional_context:
            return ""

        context_lines = []

        for key, value in additional_context.items():
            # Special formatting for mentioned_entities
            if key == "mentioned_entities" and isinstance(value, dict):
                context_lines.append("Entities User Asked About:")
                for entity_type, entities in value.items():
                    if entities:  # Only show non-empty entity lists
                        entity_type_title = entity_type.replace("_", " ").title()
                        context_lines.append(f"  {entity_type_title}:")
                        for entity in entities:
                            uid = entity.get("uid", "unknown")
                            title = entity.get("title", "Unknown")
                            context_lines.append(f"    - {title} ({uid})")
                continue

            # Format key for readability (snake_case → Title Case)
            formatted_key = key.replace("_", " ").title()

            # Format value based on type
            if isinstance(value, dict):
                # Nested dict - format as indented list
                context_lines.append(f"{formatted_key}:")
                for sub_key, sub_value in value.items():
                    formatted_sub_key = sub_key.replace("_", " ").title()
                    context_lines.append(f"  - {formatted_sub_key}: {sub_value}")
            elif isinstance(value, list):
                # List - format as comma-separated or indented based on complexity
                if value and isinstance(value[0], dict):
                    # List of dicts - format as indented items
                    context_lines.append(f"{formatted_key}:")
                    for item in value:
                        if "title" in item and "uid" in item:
                            context_lines.append(f"  - {item['title']} ({item['uid']})")
                        elif "title" in item and "similarity" in item:
                            context_lines.append(
                                f"  - {item['title']} (similarity: {item['similarity']:.2f})"
                            )
                        else:
                            context_lines.append(f"  - {item}")
                else:
                    # Simple list - comma-separated
                    context_lines.append(f"{formatted_key}: {', '.join(str(v) for v in value)}")
            else:
                # Scalar - simple key: value
                context_lines.append(f"{formatted_key}: {value}")

        return "\n".join(context_lines)

    def _get_askesis_system_prompt(self, intent: str | None) -> str:
        """Get appropriate system prompt for Askesis based on intent."""
        base_prompt = "You are Askesis, a helpful learning assistant. "

        if intent == "learn":
            return (
                base_prompt
                + "Explain concepts clearly and provide educational value. Be thorough but accessible."
            )
        elif intent == "practice":
            return (
                base_prompt
                + "Provide practical exercises and hands-on guidance. Be encouraging and supportive."
            )
        elif intent == "explore":
            return (
                base_prompt
                + "Help the user discover connections and explore topics broadly. Be curious and insightful."
            )
        elif intent == "clarify":
            return (
                base_prompt
                + "Clarify confusion and provide clear explanations. Be patient and thorough."
            )
        else:
            return (
                base_prompt
                + "Provide helpful, accurate, and relevant information. Be professional and clear."
            )


# Factory function
def create_llm_service(
    provider: str | None = None, api_key: str | None = None, model: str | None = None
) -> LLMService:
    """
    Create an LLM service with the specified configuration.

    Args:
        provider: LLM provider name,
        api_key: API key for the provider,
        model: Model name to use

    Returns:
        Configured LLM service
    """
    config = LLMConfig()

    if provider:
        config.provider = LLMProvider(provider.lower())
    if api_key:
        config.api_key = api_key
    if model:
        config.model_name = model

    # Set default system prompt for Askesis
    config.system_prompt = (
        "You are Askesis, an intelligent learning assistant. "
        "You help users learn, practice, and explore knowledge. "
        "Be helpful, educational, and encouraging."
    )

    return LLMService(config)
