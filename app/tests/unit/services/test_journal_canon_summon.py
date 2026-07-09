"""Tests for JournalService's canon summon dial (Stage 2 / Stage 3).

Covers the single dial branch point (`_maybe_summon_canon`) and that a summoned
stage passes the canon prompt block into the system prompt and appends the
"Drawing on" footer — only when passages were actually drawn.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.services.canon import CanonContext, CanonPassage
from core.services.journal.journal_service import JournalService
from core.utils.result_simplified import Errors, Result


def _canon_service(context_result):
    canon = MagicMock()
    canon.retrieve = AsyncMock(return_value=context_result)
    return canon


def _make_service(llm=None, canon=None):
    user_entry = MagicMock()
    # _build_context_summary awaits this; a bare MagicMock isn't awaitable.
    user_entry.get_vault_notes_for_context = AsyncMock(return_value=Result.ok([]))
    return JournalService(
        llm_caller=llm or MagicMock(),
        user_entry_service=user_entry,
        goals_service=None,
        tasks_service=None,
        habits_service=None,
        dsl_bridge=None,
        canon_retrieval_service=canon,
    )


def _populated_context() -> CanonContext:
    return CanonContext(
        passages=(
            CanonPassage(
                text="Linked knowledge endures.",
                book_title="Hyper Media Systems",
                resource_uid="resource_hms",
                similarity_score=0.9,
            ),
        )
    )


def _located_context() -> CanonContext:
    """A passage carrying its in-book location — for the discussion/sources path."""
    return CanonContext(
        passages=(
            CanonPassage(
                text="Hypermedia is a system of links.",
                book_title="Hypermedia Systems",
                resource_uid="resource_hms",
                similarity_score=0.9,
                heading="A Reintroduction",
                section_path="Hypermedia Concepts",
                sequence=7,
            ),
        )
    )


class TestMaybeSummonCanon:
    @pytest.mark.asyncio
    async def test_dial_off_returns_empty(self):
        service = _make_service(canon=_canon_service(Result.ok(_populated_context())))
        ctx = await service._maybe_summon_canon("entry", summon=False)
        assert ctx.has_passages is False

    @pytest.mark.asyncio
    async def test_no_canon_service_returns_empty(self):
        service = _make_service(canon=None)
        ctx = await service._maybe_summon_canon("entry", summon=True)
        assert ctx.has_passages is False

    @pytest.mark.asyncio
    async def test_retrieval_failure_returns_empty(self):
        service = _make_service(
            canon=_canon_service(Result.fail(Errors.unavailable("canon", "no embeddings")))
        )
        ctx = await service._maybe_summon_canon("entry", summon=True)
        assert ctx.has_passages is False

    @pytest.mark.asyncio
    async def test_success_returns_passages(self):
        service = _make_service(canon=_canon_service(Result.ok(_populated_context())))
        ctx = await service._maybe_summon_canon("entry", summon=True)
        assert ctx.has_passages is True
        assert ctx.books() == ["Hyper Media Systems"]


class TestStageCanonWiring:
    @pytest.mark.asyncio
    async def test_stage2_summon_infuses_prompt_and_appends_footer(self):
        llm = MagicMock()
        llm.is_model_supported = MagicMock(return_value=True)
        llm.generate = AsyncMock(return_value=Result.ok("The emerging theme is clarity."))
        service = _make_service(llm=llm, canon=_canon_service(Result.ok(_populated_context())))

        result = await service.run_stage2(
            raw_entry="hypermedia thoughts",
            scribe_output="scribe",
            review_notes="",
            user_uid="user_mike",
            summon_canon=True,
        )

        assert result.is_ok
        # Footer appended to the visible output.
        assert result.value.endswith("*Drawing on:* *Hyper Media Systems*")
        # Canon block threaded into the system prompt.
        system_prompt = llm.generate.await_args.kwargs["system_prompt"]
        assert "Wisdom to Draw On" in system_prompt
        assert "Linked knowledge endures." in system_prompt

    @pytest.mark.asyncio
    async def test_stage2_no_summon_no_footer(self):
        llm = MagicMock()
        llm.is_model_supported = MagicMock(return_value=True)
        llm.generate = AsyncMock(return_value=Result.ok("Plain response."))
        service = _make_service(llm=llm, canon=_canon_service(Result.ok(_populated_context())))

        result = await service.run_stage2(
            raw_entry="thoughts",
            scribe_output="scribe",
            review_notes="",
            user_uid="user_mike",
            summon_canon=False,
        )

        assert result.is_ok
        assert result.value == "Plain response."
        assert "Wisdom to Draw On" not in llm.generate.await_args.kwargs["system_prompt"]

    @pytest.mark.asyncio
    async def test_stage3_summon_appends_footer(self):
        llm = MagicMock()
        llm.is_model_supported = MagicMock(return_value=True)
        llm.generate = AsyncMock(return_value=Result.ok("Related connections here."))
        service = _make_service(llm=llm, canon=_canon_service(Result.ok(_populated_context())))

        result = await service.run_stage3(
            raw_entry="hypermedia thoughts",
            thought_partner_output="emerging",
            review_notes="",
            user_uid="user_mike",
            summon_canon=True,
        )

        assert result.is_ok
        assert result.value.endswith("*Drawing on:* *Hyper Media Systems*")

    @pytest.mark.asyncio
    async def test_run_compiled_threads_summon_to_both_stages(self):
        # The file path has no review gate, so run_compiled carries the dial.
        # Every stage output is footered → the compiled doc names the book, and
        # summoned Stage 2/3 prompts carry the canon block.
        llm = MagicMock()
        llm.is_model_supported = MagicMock(return_value=True)
        llm.generate = AsyncMock(return_value=Result.ok("Stage body."))
        service = _make_service(llm=llm, canon=_canon_service(Result.ok(_populated_context())))

        result = await service.run_compiled(
            raw_entry="hypermedia thoughts", user_uid="user_mike", summon_canon=True
        )

        assert result.is_ok
        assert "*Drawing on:* *Hyper Media Systems*" in result.value
        summoned_prompts = [
            call.kwargs["system_prompt"]
            for call in llm.generate.await_args_list
            if "Wisdom to Draw On" in call.kwargs["system_prompt"]
        ]
        # Stage 2 and Stage 3 both summoned (Stage 1 Scribe never does).
        assert len(summoned_prompts) == 2

    @pytest.mark.asyncio
    async def test_run_compiled_default_is_canon_free(self):
        llm = MagicMock()
        llm.is_model_supported = MagicMock(return_value=True)
        llm.generate = AsyncMock(return_value=Result.ok("Stage body."))
        service = _make_service(llm=llm, canon=_canon_service(Result.ok(_populated_context())))

        result = await service.run_compiled(raw_entry="thoughts", user_uid="user_mike")

        assert result.is_ok
        assert "Drawing on" not in result.value
        for call in llm.generate.await_args_list:
            assert "Wisdom to Draw On" not in call.kwargs["system_prompt"]

    @pytest.mark.asyncio
    async def test_no_passages_no_footer_even_when_summoned(self):
        llm = MagicMock()
        llm.is_model_supported = MagicMock(return_value=True)
        llm.generate = AsyncMock(return_value=Result.ok("Response body."))
        service = _make_service(llm=llm, canon=_canon_service(Result.ok(CanonContext.empty())))

        result = await service.run_stage2(
            raw_entry="nothing resonant",
            scribe_output="scribe",
            review_notes="",
            user_uid="user_mike",
            summon_canon=True,
        )

        assert result.is_ok
        assert result.value == "Response body."


class TestFollowUpCanonWiring:
    """The follow-up is the quote-on-demand surface (ADR-076)."""

    @pytest.mark.asyncio
    async def test_summon_injects_discussion_block_and_sources_footer(self):
        llm = MagicMock()
        llm.is_model_supported = MagicMock(return_value=True)
        llm.generate = AsyncMock(return_value=Result.ok("Yes, the book says so."))
        canon = _canon_service(Result.ok(_located_context()))
        service = _make_service(llm=llm, canon=canon)

        result = await service.run_follow_up(
            original_entry="my note",
            ai_response="prior response",
            user_reply="What does Hypermedia Systems say about links?",
            user_uid="user_mike",
            summon_canon=True,
        )

        assert result.is_ok
        # Discussion block (quote-permitting), NOT the silent-infusion block.
        system_prompt = llm.generate.await_args.kwargs["system_prompt"]
        assert "The Canon Shelf" in system_prompt
        assert "verbatim" in system_prompt
        assert "Wisdom to Draw On" not in system_prompt
        # Rich Sources footer with location + link appended to the reply.
        assert "**Sources**" in result.value
        assert "/library/resources/get?uid=resource_hms" in result.value

    @pytest.mark.asyncio
    async def test_retrieval_keys_on_the_user_question_not_the_entry(self):
        llm = MagicMock()
        llm.is_model_supported = MagicMock(return_value=True)
        llm.generate = AsyncMock(return_value=Result.ok("ok"))
        canon = _canon_service(Result.ok(_located_context()))
        service = _make_service(llm=llm, canon=canon)

        await service.run_follow_up(
            original_entry="THE ORIGINAL ENTRY",
            ai_response="prior",
            user_reply="THE QUESTION",
            user_uid="user_mike",
            summon_canon=True,
        )

        # Canon is retrieved for the user's question, not the raw entry.
        assert canon.retrieve.await_args.args[0] == "THE QUESTION"

    @pytest.mark.asyncio
    async def test_no_summon_is_canon_free(self):
        llm = MagicMock()
        llm.is_model_supported = MagicMock(return_value=True)
        llm.generate = AsyncMock(return_value=Result.ok("Plain reply."))
        service = _make_service(llm=llm, canon=_canon_service(Result.ok(_located_context())))

        result = await service.run_follow_up(
            original_entry="my note",
            ai_response="prior",
            user_reply="tell me more",
            user_uid="user_mike",
            summon_canon=False,
        )

        assert result.is_ok
        assert result.value == "Plain reply."
        assert "The Canon Shelf" not in llm.generate.await_args.kwargs["system_prompt"]
