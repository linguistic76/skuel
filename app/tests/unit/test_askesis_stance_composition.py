"""Tests for the askesis_stance composition on BOTH answer branches (ADR-082 D1/D3).

The authored stance fragment heads the guided system prompt (stance +
pedagogy leaf + canon block) AND the facet/context-aware system prompt built
by ``LLMService._build_context_aware_system_prompt`` — parity is the point:
without it the nous-facet path stays the least-instructed path. The expected
stance text comes from the same PROMPT_REGISTRY the production code renders,
so the assertions hold whether the committed floor or a founder-local
override serves.
"""

from unittest.mock import AsyncMock, MagicMock

from core.models.enums import GuidanceMode
from core.prompts import PROMPT_REGISTRY
from core.services.askesis.response_generator import ResponseGenerator
from core.services.canon import CanonContext, CanonPassage
from core.services.llm_service import LLMProvider, LLMResponse, LLMService
from core.services.user.unified_user_context import UserContext


def _stance() -> str:
    return PROMPT_REGISTRY.render("askesis_stance")


def _user_context() -> UserContext:
    # A real skeleton context — its ADR-082 grounding projection renders ""
    # so stance composition is observed without a learner block in between.
    return UserContext(user_uid="user_test")


def _guidance(mode: GuidanceMode = GuidanceMode.SOCRATIC) -> MagicMock:
    guidance = MagicMock()
    guidance.mode = mode
    return guidance


def _canon_context() -> CanonContext:
    return CanonContext(
        passages=(
            CanonPassage(
                text="Hypermedia is a media type with hypermedia controls.",
                book_title="Hypermedia Systems",
                resource_uid="resource.hypermedia-systems",
                similarity_score=0.91,
                heading="A Brief History of Hypermedia",
                section_path="Hypermedia Concepts > Hypermedia: A Reintroduction",
                sequence=7,
            ),
        )
    )


# ============================================================================
# Guided branch — build_guided_system_prompt
# ============================================================================


class TestGuidedBranch:
    def _generator(self) -> ResponseGenerator:
        generator = ResponseGenerator()
        generator._build_socratic_prompt = MagicMock(  # type: ignore[method-assign]
            return_value="PEDAGOGY LEAF"
        )
        return generator

    def test_stance_heads_the_guided_prompt(self) -> None:
        prompt = self._generator().build_guided_system_prompt(
            _guidance(), MagicMock(), _user_context()
        )

        assert prompt.startswith(_stance())
        assert prompt.endswith("PEDAGOGY LEAF")

    def test_composition_order_stance_leaf_canon(self) -> None:
        """ADR-082 D1: stance + pedagogy leaf + canon block, in that order."""
        prompt = self._generator().build_guided_system_prompt(
            _guidance(), MagicMock(), _user_context(), canon_context=_canon_context()
        )

        assert (
            prompt.index(_stance())
            < prompt.index("PEDAGOGY LEAF")
            < prompt.index("## Readings for This Step")
        )

    def test_every_guidance_mode_gets_the_stance(self) -> None:
        for mode in GuidanceMode:
            generator = ResponseGenerator()
            builder = MagicMock(return_value="LEAF")
            generator._build_direct_prompt = builder  # type: ignore[method-assign]
            generator._build_socratic_prompt = builder  # type: ignore[method-assign]
            generator._build_exploratory_prompt = builder  # type: ignore[method-assign]
            generator._build_encouraging_prompt = builder  # type: ignore[method-assign]

            prompt = generator.build_guided_system_prompt(
                _guidance(mode), MagicMock(), _user_context()
            )

            assert prompt.startswith(_stance()), mode


# ============================================================================
# Facet / context-aware branch — LLMService system prompt
# ============================================================================


class TestFacetBranch:
    def test_stance_heads_the_context_aware_prompt(self) -> None:
        service = LLMService()

        prompt = service._build_context_aware_system_prompt("USER CTX", None, None)

        assert prompt.startswith(_stance())
        assert "=== USER'S CURRENT STATE ===" in prompt
        assert "USER CTX" in prompt
        assert prompt.index(_stance()) < prompt.index("USER CTX")

    async def test_generate_context_aware_answer_sends_stance_as_system_prompt(self) -> None:
        """The public entry both facet call sites use carries the stance."""
        service = LLMService()
        service.generate = AsyncMock(  # type: ignore[method-assign]
            return_value=LLMResponse(content="ok", provider=LLMProvider.MOCK, model="mock-model")
        )

        await service.generate_context_aware_answer(query="What is hypermedia?", user_context="CTX")

        system_prompt = service.generate.call_args.kwargs["system_prompt"]
        assert system_prompt.startswith(_stance())
