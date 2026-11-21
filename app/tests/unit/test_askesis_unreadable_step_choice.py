"""A step in progress that does not read is no candidate: Askesis guides on the next one, and says so.

The ADR-059 rule ranks the learner's steps in progress (engaged first, then not engaged)
and guides on the first that reads as a PathStep. A step whose stored properties hold a
value its field cannot read, or no uid, is passed over; each one ranked ahead of the
guided step is named in a closing sentence of the answer. The steps arrive as the
MEGA-QUERY's ``properties(ps)``: enum values, ``created_at`` an ISO string, ``updated_at``
the driver's ``DateTime``.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from neo4j.time import DateTime as DriverDateTime

from core.models.askesis.ps_bundle import PsBundle
from core.models.enums import GuidanceMode
from core.models.query_types import QueryIntent
from core.services.askesis.context_retriever import ContextRetriever
from core.services.askesis.query_processor import QueryProcessor
from core.services.ps_engagement.engagement import Engagement
from core.services.user.unified_user_context import UserContext
from core.utils.result_simplified import Result

_USER = "user_0123456789abcdef"
_BAD = "ps.choice.does-not-read"
_GOOD = "ps.choice.reads"
_OTHER = "ps.choice.reads-too"

type _Stored = dict[str, Any]  # boundary: raw node properties, driver temporals included
type _Response = dict[str, Any]  # boundary: the answer's JSON-shaped response dict


def _stored(uid: str, title: str, **overrides: object) -> _Stored:
    step: _Stored = {
        "uid": uid,
        "title": title,
        "entity_type": "path_step",
        "status": "active",
        "learning_level": "beginner",
        "publication_state": "published",
        "intent": f"Practise {title.lower()}",
        "created_at": "2026-11-21T03:04:54.336Z",
        "updated_at": DriverDateTime.from_native(datetime(2026, 11, 20, 9, 30, tzinfo=UTC)),
    }
    step.update(overrides)
    return step


def _unreadable(uid: str, title: str) -> _Stored:
    return _stored(uid, title, learning_level="expertish")


def _context(*steps: _Stored) -> UserContext:
    context = UserContext(user_uid=_USER)
    context.current_ps_uids = {str(step.get("uid")) for step in steps}
    context.active_path_steps_rich = [{"step": step, "graph_context": {}} for step in steps]
    return context


def _engagements(*engaged_uids: str) -> MagicMock:
    """find_active answers an engaged edge for ``engaged_uids``, none for any other step."""

    async def _find_active(_user_uid: str, ps_uid: str) -> Result[Engagement | None]:
        if ps_uid not in engaged_uids:
            return Result.ok(None)
        return Result.ok(
            Engagement(
                uid=f"eng_{ps_uid}",
                student_uid=_USER,
                ps_uid=ps_uid,
                state="engaged",
                since=datetime(2026, 11, 1, 10, 0, tzinfo=UTC),
            )
        )

    service = MagicMock()
    service.find_active = AsyncMock(side_effect=_find_active)
    return service


def _processor(context: UserContext, engagements: MagicMock) -> tuple[QueryProcessor, MagicMock]:
    """The real retriever chooses and builds; every other collaborator answers enough
    for both the guided and the context-aware branch to reach an answer."""
    ps_backend = MagicMock()
    ps_backend.get_cited_resources = AsyncMock(return_value=Result.ok([]))
    retriever = ContextRetriever(ps_backend=ps_backend, ps_engagement_service=engagements)
    retriever.retrieve_relevant_context = AsyncMock(return_value={})  # type: ignore[method-assign]

    intent_classifier = MagicMock()
    intent_classifier.classify_intent = AsyncMock(return_value=Result.ok(QueryIntent.EXPLORATORY))
    intent_classifier.determine_guidance_mode = MagicMock(
        return_value=MagicMock(mode=GuidanceMode.SOCRATIC)
    )
    response_generator = MagicMock()
    response_generator.build_guided_system_prompt = MagicMock(return_value="guided prompt")
    response_generator.build_llm_context = MagicMock(return_value="llm context")
    response_generator.generate_actions = MagicMock(return_value=[])
    entity_extractor = MagicMock()
    entity_extractor.extract_entities_from_query = MagicMock(return_value={})
    entity_extractor.extract_from_bundle = MagicMock(return_value=[])
    user_service = MagicMock()
    user_service.get_rich_unified_context = AsyncMock(return_value=Result.ok(context))
    user_service.add_conversation_message = AsyncMock(return_value=Result.ok(True))
    llm_service = MagicMock()
    llm_service.resolve_model = MagicMock(return_value=None)
    llm_service.generate = AsyncMock(return_value=MagicMock(content="Guided answer."))
    llm_service.generate_context_aware_answer = AsyncMock(return_value="Context answer.")

    processor = QueryProcessor(
        intent_classifier=intent_classifier,
        response_generator=response_generator,
        entity_extractor=entity_extractor,
        context_retriever=retriever,
        user_service=user_service,
        llm_service=llm_service,
        zpd_service=MagicMock(),
    )
    return processor, response_generator


def _guided_on(response_generator: MagicMock) -> str:
    """The uid of the step the guided prompt was built around."""
    (_guidance, bundle, _context), _kwargs = response_generator.build_guided_system_prompt.call_args
    assert isinstance(bundle, PsBundle)
    return bundle.path_step.uid


async def _ask(context: UserContext, engagements: MagicMock) -> tuple[_Response, MagicMock]:
    processor, response_generator = _processor(context, engagements)
    result = await processor.answer_user_question(_USER, "What is this step about?")
    assert result.is_ok, result
    return result.value, response_generator


# ---------------------------------------------------------------------------
# Which step Askesis guides on
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_an_engaged_step_that_does_not_read_gives_way_to_a_readable_step_in_progress() -> (
    None
):
    response, response_generator = await _ask(
        _context(_unreadable(_BAD, "Noticing"), _stored(_GOOD, "Naming")), _engagements(_BAD)
    )

    assert response["mode"] == "guided"
    assert response["guidance_mode"] == GuidanceMode.SOCRATIC.value
    assert _guided_on(response_generator) == _GOOD


@pytest.mark.anyio
async def test_the_next_engaged_step_comes_before_a_step_not_engaged() -> None:
    response, response_generator = await _ask(
        _context(
            _unreadable(_BAD, "Noticing"), _stored(_OTHER, "Pausing"), _stored(_GOOD, "Naming")
        ),
        _engagements(_BAD, _GOOD),
    )

    assert response["mode"] == "guided"
    assert _guided_on(response_generator) == _GOOD


@pytest.mark.anyio
async def test_a_step_with_no_uid_stored_is_no_candidate_and_is_never_looked_up() -> None:
    engagements = _engagements()
    no_uid = _stored(_BAD, "Noticing")
    del no_uid["uid"]

    response, response_generator = await _ask(
        _context(no_uid, _stored(_GOOD, "Naming")), engagements
    )

    assert response["mode"] == "guided"
    assert _guided_on(response_generator) == _GOOD
    assert [call.args[1] for call in engagements.find_active.await_args_list] == [_GOOD]


# ---------------------------------------------------------------------------
# What the learner is told
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_the_learner_is_told_which_step_could_not_be_opened_and_which_guides() -> None:
    response, _ = await _ask(
        _context(_unreadable(_BAD, "Noticing"), _stored(_GOOD, "Naming")), _engagements(_BAD)
    )

    assert response["answer"] == (
        "Guided answer.\n\n"
        'I couldn\'t open your step "Noticing" just now, so I\'m working from "Naming".'
    )


@pytest.mark.anyio
async def test_a_learner_whose_one_step_does_not_read_is_told_the_answer_is_not_drawn_from_it() -> (
    None
):
    response, response_generator = await _ask(
        _context(_unreadable(_BAD, "Noticing")), _engagements(_BAD)
    )

    assert response["mode"] == "llm_generated"
    assert "guidance_mode" not in response
    response_generator.build_guided_system_prompt.assert_not_called()
    assert response["answer"] == (
        "Context answer.\n\n"
        "I couldn't open your step \"Noticing\" just now, so this answer isn't drawn from "
        "its material."
    )


@pytest.mark.anyio
async def test_a_step_that_does_not_read_ranked_behind_the_choice_is_not_mentioned() -> None:
    response, response_generator = await _ask(
        _context(_stored(_GOOD, "Naming"), _unreadable(_BAD, "Noticing")), _engagements(_GOOD)
    )

    assert _guided_on(response_generator) == _GOOD
    assert response["answer"] == "Guided answer."


@pytest.mark.anyio
async def test_the_conversation_remembers_the_notice_the_learner_read() -> None:
    """The session window and the stored turn hold the answer as the learner saw it, so a
    follow-up about the step that could not be opened reaches the model with the sentence."""
    processor, _ = _processor(
        _context(_unreadable(_BAD, "Noticing"), _stored(_GOOD, "Naming")), _engagements(_BAD)
    )

    result = await processor.answer_user_question(
        _USER, "What is this step about?", session_id="session-unopened"
    )
    await asyncio.gather(*processor._background_tasks)

    assert result.is_ok, result
    answered = result.value["answer"]
    assert answered.endswith('so I\'m working from "Naming".')
    session = processor.conversation_context.get_or_create_session("session-unopened", _USER)
    assert session.to_llm_messages(max_tokens=2000)[-1] == {
        "role": "assistant",
        "content": answered,
    }
    stored = cast("AsyncMock", processor.user_service.add_conversation_message).await_args_list
    assert [call.args[1:] for call in stored] == [
        ("user", "What is this step about?"),
        ("assistant", answered),
    ]
