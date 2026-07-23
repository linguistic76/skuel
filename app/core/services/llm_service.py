"""
LLM Service for Natural Language Generation
============================================

Provides LLM integration for Askesis and other services: prompt building,
RAG context formatting, and the Askesis system prompts. The actual provider
call is delegated to an injected ``UnifiedLLMCaller`` (W1 / ADR-044) — the
multi-provider caller that routes by model prefix (gpt* → OpenAI, claude* →
Anthropic), so Askesis reaches whichever provider the requested model names.
The vendor SDKs live in ``adapters/external/llm/``. When no caller is wired
(MOCK/LOCAL provider, or tests), ``generate`` returns canned mock responses.
"""

__version__ = "1.0"


import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from core.ports.base_protocols import EnumLike
from core.ports.llm_protocols import ChatMessage
from core.services.llm_caller import LLMCallerProtocol

logger = logging.getLogger(__name__)


class LLMProvider(StrEnum):
    """Supported LLM providers"""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    LOCAL = "local"
    MOCK = "mock"

    @classmethod
    def from_model(cls, model: str) -> "LLMProvider":
        """Infer the provider that serves ``model`` from its name prefix.

        Mirrors ``UnifiedLLMCaller``'s prefix routing (claude* → Anthropic,
        otherwise OpenAI) so a per-call model override labels the response with
        the provider it actually routed to — not the service's configured
        default. Unrecognized names fall back to OpenAI; the caller rejects them
        before any provider is reached, so the label only rides an error path.
        """
        if model.startswith("claude"):
            return cls.ANTHROPIC
        return cls.OPENAI


@dataclass
class LLMConfig:
    """Configuration for LLM service.

    The provider/model select behaviour at the composition root (which adapter
    to inject) and label the LLMResponse. The API key is no longer held here —
    it is read at the root and passed to the chat adapter (W1).
    """

    provider: LLMProvider = LLMProvider.MOCK
    model_name: str = "gpt-4o-mini"
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
    """

    def __init__(
        self, config: LLMConfig | None = None, caller: LLMCallerProtocol | None = None
    ) -> None:
        """
        Initialize LLM service with configuration and an optional multi-provider caller.

        Args:
            config: LLM configuration. ``model_name`` is the default model,
                overridable per call — its prefix selects the provider.
            caller: The multi-provider ``UnifiedLLMCaller`` that routes by model
                prefix (gpt* → OpenAI, claude* → Anthropic). Required for real
                providers (OPENAI/ANTHROPIC). When ``None`` with a MOCK/LOCAL
                provider, ``generate`` returns canned mock responses with no
                external calls.

        Raises:
            ValueError: If a real provider (OPENAI/ANTHROPIC) is configured
                without a ``caller`` — fail-fast so a miswired service surfaces
                at bootstrap instead of silently returning mock text.
        """
        self.config = config or LLMConfig()
        if caller is None and self.config.provider in (
            LLMProvider.OPENAI,
            LLMProvider.ANTHROPIC,
        ):
            raise ValueError(
                f"LLMService configured for provider '{self.config.provider}' requires a "
                "caller (the composition root wires chat_clients.caller). Use LLMProvider.MOCK "
                "or LLMProvider.LOCAL for mock responses without a caller."
            )
        self.caller = caller

    async def generate(  # skuel-lint: disable=SKUEL005 -- always answers: port errors fold into a degraded LLMResponse, never a propagated failure
        self,
        prompt: str,
        context: str | None = None,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        conversation_history: list[dict[str, str]] | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        """
        Generate text using the LLM.

        Args:
            prompt: The user prompt,
            context: Additional context,
            system_prompt: System instructions,
            temperature: Sampling temperature,
            max_tokens: Maximum tokens to generate,
            conversation_history: Prior turns for multi-turn RAG,
            model: Per-call model override (its prefix selects the provider);
                defaults to ``config.model_name``.

        Returns:
            LLM response
        """
        # Use provided values or defaults from config
        system_prompt = system_prompt or self.config.system_prompt
        temperature = temperature or self.config.temperature
        max_tokens = max_tokens or self.config.max_tokens
        model = model or self.config.model_name

        # Combine context with prompt if provided
        full_prompt = prompt
        if context:
            full_prompt = f"Context: {context}\n\nQuery: {prompt}"

        # No caller ⇒ MOCK/LOCAL provider (the constructor enforces that real
        # providers are wired with a caller) → canned mock response, no external call.
        if self.caller is None:
            return self._generate_mock(full_prompt, system_prompt)

        # Build the conversation (system prompt is passed separately so each
        # adapter places it where its SDK expects).
        messages: list[ChatMessage] = [
            {"role": m["role"], "content": m["content"]} for m in (conversation_history or [])
        ]
        messages.append({"role": "user", "content": full_prompt})

        # The caller routes by model prefix (gpt* → OpenAI, claude* → Anthropic).
        result = await self.caller.complete(
            messages,
            system_prompt=system_prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        # Label the response with the provider the model actually routes to
        # (a per-call override may cross providers), not the configured default.
        if result.is_error:
            return LLMResponse(
                content="",
                provider=LLMProvider.from_model(model),
                model=model,
                error=str(result.expect_error()),
            )

        completion = result.value
        return LLMResponse(
            content=completion.text,
            provider=LLMProvider.from_model(completion.model or model),
            model=completion.model or model,
            usage=completion.usage,
        )

    def _generate_mock(self, prompt: str, _system_prompt: str | None) -> LLMResponse:
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

    async def generate_context_aware_answer(  # skuel-lint: disable=SKUEL005 -- always answers: errors fold into degraded response text (RAG surface)
        self,
        query: str,
        user_context: str,
        additional_context: dict | None = None,
        intent: Any | None = None,
        conversation_history: list[dict[str, str]] | None = None,
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
            conversation_history=conversation_history,
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

            # Special formatting for relevant_chunks — inline the passage text
            # (with context_window for grounding) and attribute to the parent
            # PathStep so the LLM can cite the source.
            if key == "relevant_chunks" and isinstance(value, list):
                context_lines.append("Relevant Passages:")
                for hit in value:
                    if not isinstance(hit, dict):
                        continue
                    title = hit.get("parent_title", "Unknown")
                    parent_uid = hit.get("parent_uid", "")
                    chunk_type = hit.get("chunk_type", "")
                    similarity = hit.get("similarity", 0.0)
                    passage = (hit.get("context_window") or hit.get("text") or "").strip()
                    header = f"  From '{title}' ({parent_uid}) — {chunk_type}, similarity {similarity:.2f}:"
                    context_lines.append(header)
                    for line in passage.splitlines() or [""]:
                        context_lines.append(f"    {line}")
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
