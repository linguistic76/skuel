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

    @pytest.mark.asyncio
    async def test_resource_uids_scope_is_passed_to_retrieve(self):
        # C3 shelf checkboxes → retrieve(resource_uids=...); None = whole shelf.
        canon = _canon_service(Result.ok(_populated_context()))
        service = _make_service(canon=canon)
        await service._maybe_summon_canon("entry", summon=True, resource_uids=["res_a", "res_b"])
        assert canon.retrieve.await_args.kwargs["resource_uids"] == ["res_a", "res_b"]

    @pytest.mark.asyncio
    async def test_whole_shelf_when_no_scope(self):
        canon = _canon_service(Result.ok(_populated_context()))
        service = _make_service(canon=canon)
        await service._maybe_summon_canon("entry", summon=True)
        assert canon.retrieve.await_args.kwargs["resource_uids"] is None


class TestRunDiscussion:
    """The typed first message opens a user-led, quote-on-demand discussion."""

    @pytest.mark.asyncio
    async def test_user_message_is_the_raw_entry(self):
        # The user leads: the prompt is their words, not a wrapped template.
        llm = _stub_llm("Let's think about that.")
        service = _make_service(llm=llm, canon=_canon_service(Result.ok(CanonContext.empty())))

        await service.run_discussion("What's alive for me today?", "user_mike")

        assert llm.generate.await_args.kwargs["prompt"] == "What's alive for me today?"

    @pytest.mark.asyncio
    async def test_summon_injects_discussion_block_and_returns_sources(self):
        llm = _stub_llm("Hypermedia Systems puts it this way…")
        canon = _canon_service(Result.ok(_located_context()))
        service = _make_service(llm=llm, canon=canon)

        result = await service.run_discussion(
            "Tell me about hypermedia.", "user_mike", summon_canon=True
        )

        assert result.is_ok
        system_prompt = llm.generate.await_args.kwargs["system_prompt"]
        # Quote-permitting discussion block, not the silent-infusion block.
        assert "The Canon Shelf" in system_prompt
        assert "verbatim" in system_prompt
        assert "Wisdom to Draw On" not in system_prompt
        # Companion, no forced headings.
        assert "# What is Emerging" not in system_prompt
        turn = result.value
        assert turn.text == "Hypermedia Systems puts it this way…"
        assert len(turn.sources) == 1
        assert turn.sources[0].resource_uid == "resource_hms"

    @pytest.mark.asyncio
    async def test_book_scope_is_passed_through(self):
        llm = _stub_llm("ok")
        canon = _canon_service(Result.ok(_located_context()))
        service = _make_service(llm=llm, canon=canon)

        await service.run_discussion(
            "ground me", "user_mike", summon_canon=True, canon_book_uids=["res_a"]
        )

        assert canon.retrieve.await_args.kwargs["resource_uids"] == ["res_a"]

    @pytest.mark.asyncio
    async def test_no_summon_is_canon_free(self):
        llm = _stub_llm("Plain companion reply.")
        service = _make_service(llm=llm, canon=_canon_service(Result.ok(_located_context())))

        result = await service.run_discussion("just thinking out loud", "user_mike")

        assert result.is_ok
        assert result.value.text == "Plain companion reply."
        assert result.value.sources == ()
        assert "The Canon Shelf" not in llm.generate.await_args.kwargs["system_prompt"]


class TestListCanonShelf:
    @pytest.mark.asyncio
    async def test_no_canon_service_returns_empty_list(self):
        service = _make_service(canon=None)
        result = await service.list_canon_shelf()
        assert result.is_ok
        assert result.value == []

    @pytest.mark.asyncio
    async def test_delegates_to_canon_list_shelf(self):
        from core.ports.query_types import ShelvedBook

        canon = MagicMock()
        books = [ShelvedBook(resource_uid="res_a", title="Book A")]
        canon.list_shelf = AsyncMock(return_value=Result.ok(books))
        service = _make_service(canon=canon)

        result = await service.list_canon_shelf()

        assert result.is_ok
        assert result.value == books
        canon.list_shelf.assert_awaited_once()


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
        # Structured sources returned for clickable rendering (not markdown in text).
        turn = result.value
        assert turn.text == "Yes, the book says so."
        assert len(turn.sources) == 1
        assert turn.sources[0].resource_uid == "resource_hms"
        assert turn.sources[0].locators == ("Hypermedia Concepts > A Reintroduction",)

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
        assert result.value.text == "Plain reply."
        assert result.value.sources == ()
        assert "The Canon Shelf" not in llm.generate.await_args.kwargs["system_prompt"]


# ---------------------------------------------------------------------------
# Vault dial (canon P3) — mirrors the canon matrix on the second corpus
# ---------------------------------------------------------------------------


def _vault_context() -> CanonContext:
    from core.services.canon import SourceKind

    return CanonContext(
        passages=(
            CanonPassage(
                text="I already wrote about this tension.",
                book_title="My Stoicism Notes",
                resource_uid="ue_note_1",
                similarity_score=0.85,
                source_kind=SourceKind.VAULT,
                vault_path="knowledge/stoicism.md",
            ),
        ),
        source_kind=SourceKind.VAULT,
    )


def _dual_service(canon_result=None, vault_result=None, llm=None):
    """Service whose canon mock answers both retrieve and retrieve_vault."""
    canon = MagicMock()
    canon.retrieve = AsyncMock(
        return_value=canon_result if canon_result is not None else Result.ok(CanonContext.empty())
    )
    canon.retrieve_vault = AsyncMock(
        return_value=vault_result if vault_result is not None else Result.ok(CanonContext.empty())
    )
    service = _make_service(llm=llm, canon=canon)
    return service, canon


def _stub_llm(reply: str = "Response body."):
    llm = MagicMock()
    llm.is_model_supported = MagicMock(return_value=True)
    llm.generate = AsyncMock(return_value=Result.ok(reply))
    return llm


class TestMaybeSummonVault:
    @pytest.mark.asyncio
    async def test_dial_off_returns_empty_and_never_retrieves(self):
        service, canon = _dual_service(vault_result=Result.ok(_vault_context()))
        ctx = await service._maybe_summon_vault("entry", "user_mike", summon=False)
        assert ctx.has_passages is False
        canon.retrieve_vault.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_canon_service_returns_empty(self):
        service = _make_service(canon=None)
        ctx = await service._maybe_summon_vault("entry", "user_mike", summon=True)
        assert ctx.has_passages is False

    @pytest.mark.asyncio
    async def test_retrieval_failure_returns_empty(self):
        service, _ = _dual_service(
            vault_result=Result.fail(Errors.unavailable("vault", "no embeddings"))
        )
        ctx = await service._maybe_summon_vault("entry", "user_mike", summon=True)
        assert ctx.has_passages is False

    @pytest.mark.asyncio
    async def test_success_returns_passages(self):
        service, _ = _dual_service(vault_result=Result.ok(_vault_context()))
        ctx = await service._maybe_summon_vault("entry", "user_mike", summon=True)
        assert ctx.has_passages is True
        assert ctx.books() == ["My Stoicism Notes"]

    @pytest.mark.asyncio
    async def test_retrieves_for_exactly_the_acting_user(self):
        # The service seam is the cross-user boundary: retrieval must be called
        # with the acting user_uid and nothing else.
        service, canon = _dual_service(vault_result=Result.ok(_vault_context()))
        await service._maybe_summon_vault("entry", "user_mike", summon=True)
        canon.retrieve_vault.assert_awaited_once_with("entry", "user_mike")


class TestStageVaultWiring:
    @pytest.mark.asyncio
    async def test_stage2_vault_summon_infuses_prompt_and_appends_footer(self):
        llm = _stub_llm("The emerging theme is clarity.")
        service, canon = _dual_service(vault_result=Result.ok(_vault_context()), llm=llm)

        result = await service.run_stage2(
            raw_entry="stoic thoughts",
            scribe_output="scribe",
            review_notes="",
            user_uid="user_mike",
            summon_vault=True,
        )

        assert result.is_ok
        assert result.value.endswith("*Drawing on:* *My Stoicism Notes*")
        system_prompt = llm.generate.await_args.kwargs["system_prompt"]
        assert "The User's Own Notes to Draw On" in system_prompt
        assert "I already wrote about this tension." in system_prompt
        # The vault dial retrieves on the raw entry, scoped to the acting user.
        canon.retrieve_vault.assert_awaited_once_with("stoic thoughts", "user_mike")
        # Canon dial off → the shelf is never touched.
        canon.retrieve.assert_not_called()

    @pytest.mark.asyncio
    async def test_stage3_vault_summon_appends_footer(self):
        llm = _stub_llm("Related connections here.")
        service, _ = _dual_service(vault_result=Result.ok(_vault_context()), llm=llm)

        result = await service.run_stage3(
            raw_entry="stoic thoughts",
            thought_partner_output="emerging",
            review_notes="",
            user_uid="user_mike",
            summon_vault=True,
        )

        assert result.is_ok
        assert result.value.endswith("*Drawing on:* *My Stoicism Notes*")

    @pytest.mark.asyncio
    async def test_both_dials_merge_into_one_footer(self):
        llm = _stub_llm()
        service, _ = _dual_service(
            canon_result=Result.ok(_populated_context()),
            vault_result=Result.ok(_vault_context()),
            llm=llm,
        )

        result = await service.run_stage2(
            raw_entry="thoughts",
            scribe_output="scribe",
            review_notes="",
            user_uid="user_mike",
            summon_canon=True,
            summon_vault=True,
        )

        assert result.is_ok
        # ONE merged footer line, never two rules.
        assert result.value.count("---") == 1
        assert result.value.count("Drawing on") == 1
        assert "*Hyper Media Systems*" in result.value
        assert "*My Stoicism Notes*" in result.value
        # Both blocks in the prompt, canon first.
        system_prompt = llm.generate.await_args.kwargs["system_prompt"]
        assert "Wisdom to Draw On" in system_prompt
        assert "The User's Own Notes to Draw On" in system_prompt
        assert system_prompt.index("Wisdom to Draw On") < system_prompt.index(
            "The User's Own Notes to Draw On"
        )

    @pytest.mark.asyncio
    async def test_vault_dial_suppresses_shallow_note_digest(self):
        # De-dup: the grounded block replaces the shallow recency snippets.
        llm = _stub_llm()
        service, _ = _dual_service(vault_result=Result.ok(_vault_context()), llm=llm)

        await service.run_stage2(
            raw_entry="thoughts",
            scribe_output="scribe",
            review_notes="",
            user_uid="user_mike",
            summon_vault=True,
        )
        service._user_entry.get_vault_notes_for_context.assert_not_called()

    @pytest.mark.asyncio
    async def test_dial_off_keeps_shallow_note_digest(self):
        llm = _stub_llm()
        service, _ = _dual_service(llm=llm)

        await service.run_stage2(
            raw_entry="thoughts",
            scribe_output="scribe",
            review_notes="",
            user_uid="user_mike",
        )
        service._user_entry.get_vault_notes_for_context.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_vault_retrieval_failure_keeps_shallow_note_digest(self):
        # Fail-soft floor: a dial-on retrieval FAILURE must not ground the
        # stage below its dial-off state — the shallow digest stays.
        llm = _stub_llm()
        service, _ = _dual_service(
            vault_result=Result.fail(Errors.unavailable("vault", "no embeddings")), llm=llm
        )

        await service.run_stage2(
            raw_entry="thoughts",
            scribe_output="scribe",
            review_notes="",
            user_uid="user_mike",
            summon_vault=True,
        )
        service._user_entry.get_vault_notes_for_context.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_vault_retrieval_empty_hit_keeps_shallow_note_digest(self):
        # Same floor for a clean search with nothing above min_score.
        llm = _stub_llm()
        service, _ = _dual_service(vault_result=Result.ok(CanonContext.empty()), llm=llm)

        await service.run_follow_up(
            original_entry="entry",
            ai_response="response",
            user_reply="what did I write about stoicism?",
            user_uid="user_mike",
            summon_vault=True,
        )
        service._user_entry.get_vault_notes_for_context.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_compiled_threads_vault_dial_to_both_stages(self):
        llm = _stub_llm("Stage body.")
        service, _ = _dual_service(vault_result=Result.ok(_vault_context()), llm=llm)

        result = await service.run_compiled(
            raw_entry="stoic thoughts", user_uid="user_mike", summon_vault=True
        )

        assert result.is_ok
        assert "*Drawing on:* *My Stoicism Notes*" in result.value
        summoned_prompts = [
            call.kwargs["system_prompt"]
            for call in llm.generate.await_args_list
            if "The User's Own Notes to Draw On" in call.kwargs["system_prompt"]
        ]
        assert len(summoned_prompts) == 2  # Stage 2 and Stage 3, never Stage 1

    @pytest.mark.asyncio
    async def test_no_passages_no_footer_even_when_summoned(self):
        llm = _stub_llm("Response body.")
        service, _ = _dual_service(vault_result=Result.ok(CanonContext.empty()), llm=llm)

        result = await service.run_stage2(
            raw_entry="nothing resonant",
            scribe_output="scribe",
            review_notes="",
            user_uid="user_mike",
            summon_vault=True,
        )

        assert result.is_ok
        assert result.value == "Response body."


class TestFollowUpVaultWiring:
    @pytest.mark.asyncio
    async def test_vault_summon_injects_discussion_block_and_sources(self):
        llm = _stub_llm("You wrote exactly that.")
        service, canon = _dual_service(vault_result=Result.ok(_vault_context()), llm=llm)

        result = await service.run_follow_up(
            original_entry="my note",
            ai_response="prior response",
            user_reply="What did I write about stoicism?",
            user_uid="user_mike",
            summon_vault=True,
        )

        assert result.is_ok
        system_prompt = llm.generate.await_args.kwargs["system_prompt"]
        assert "The User's Vault Notes" in system_prompt
        assert "verbatim" in system_prompt
        # Keyed on the user's question, scoped to the acting user.
        canon.retrieve_vault.assert_awaited_once_with(
            "What did I write about stoicism?", "user_mike"
        )
        turn = result.value
        assert len(turn.sources) == 1
        assert turn.sources[0].resource_uid == "ue_note_1"
        assert turn.sources[0].locators == ("knowledge/stoicism.md",)

    @pytest.mark.asyncio
    async def test_both_dials_concatenate_sources_canon_first(self):
        llm = _stub_llm()
        service, _ = _dual_service(
            canon_result=Result.ok(_located_context()),
            vault_result=Result.ok(_vault_context()),
            llm=llm,
        )

        result = await service.run_follow_up(
            original_entry="my note",
            ai_response="prior",
            user_reply="q",
            user_uid="user_mike",
            summon_canon=True,
            summon_vault=True,
        )

        assert result.is_ok
        sources = result.value.sources
        assert [s.resource_uid for s in sources] == ["resource_hms", "ue_note_1"]

    @pytest.mark.asyncio
    async def test_no_summon_is_vault_free(self):
        llm = _stub_llm("Plain reply.")
        service, canon = _dual_service(vault_result=Result.ok(_vault_context()), llm=llm)

        result = await service.run_follow_up(
            original_entry="my note",
            ai_response="prior",
            user_reply="tell me more",
            user_uid="user_mike",
        )

        assert result.is_ok
        assert result.value.sources == ()
        canon.retrieve_vault.assert_not_called()
        assert "The User's Vault Notes" not in llm.generate.await_args.kwargs["system_prompt"]
