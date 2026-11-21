"""The Askesis bundle reads its PathStep and cited Resources from the shape the graph stores.

The step arrives as the MEGA-QUERY's ``properties(ps)``, each Resource as
``get_cited_resources``' ``r {.*}``: enum fields hold their stored values, ``created_at`` an
ISO string, ``updated_at`` (and a step's ``last_applied_date``) the driver's ``DateTime``,
beside keys no field holds (the embedding, stray frontmatter). The bundle holds enum members
and ``datetime``s, refuses a stored value its field cannot read, and says why at ERROR.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from neo4j.time import DateTime as DriverDateTime
from structlog.testing import capture_logs
from structlog.typing import EventDict

from core.models.enums import Domain, GuidanceMode, KuComplexity, LearningLevel, SELCategory
from core.models.enums.curriculum_enums import PublicationState
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.pathways.path_step import PathStep
from core.models.query_types import QueryIntent
from core.services.askesis.context_retriever import ContextRetriever
from core.services.askesis.query_processor import QueryProcessor
from core.services.user.unified_user_context import UserContext
from core.utils.result_simplified import ErrorCategory, Result

_USER = "user_0123456789abcdef"
_STEP_UID = "ps.test.stored-shape"
_CREATED = "2026-11-21T03:04:54.336Z"
_CREATED_AT = datetime(2026, 11, 21, 3, 4, 54, 336000, tzinfo=UTC)
_UPDATED_AT = datetime(2026, 11, 20, 9, 30, tzinfo=UTC)
_APPLIED_AT = datetime(2026, 11, 19, 18, 0, tzinfo=UTC)

type _Stored = dict[str, Any]  # boundary: raw node properties, driver temporals included


def _stored_step(**overrides: object) -> _Stored:
    """A PathStep's properties as the MEGA-QUERY hands them over (measured on the live graph)."""
    step: _Stored = {
        "uid": _STEP_UID,
        "title": "Stored Shape",
        "entity_type": "path_step",
        "status": "active",
        "learning_level": "beginner",
        "complexity": "advanced",
        "sel_category": "self_awareness",
        "publication_state": "published",
        "intent": "Read the stored shape",
        "nous": ["self-awareness"],
        "learning_objectives": ["Name the shape"],
        "tags": ["shape"],
        "quality_score": 0.88,
        "estimated_time_minutes": 12,
        "word_count": 5,
        "created_at": _CREATED,
        "updated_at": DriverDateTime.from_native(_UPDATED_AT),
        "last_applied_date": DriverDateTime.from_native(_APPLIED_AT),
        "embedding": [0.1] * 8,
        "embedding_model": "text-embedding-3-small",
        "embedding_text_hash": "0f3a",
        "difficulty": "easy",
        "notes": "frontmatter no field holds",
        "connections.requires": ["ps.test.other"],
    }
    step.update(overrides)
    return step


def _stored_resource(uid: str, **overrides: object) -> _Stored:
    """A cited Resource's row as ``get_cited_resources`` returns it."""
    resource: _Stored = {
        "uid": uid,
        "title": f"Book {uid}",
        "entity_type": "resource",
        "author": "Some Author",
        "description": "A book.",
        "content": "Body of the resource.\n",
        "media_type": "book",
        "publication_year": 1999,
        "tags": ["shape"],
        "created_at": "2026-11-21T03:04:53.688Z",
        "updated_at": DriverDateTime.from_native(_UPDATED_AT),
        "embedding": [0.1] * 8,
        "embedding_version": "v3",
    }
    resource.update(overrides)
    return {"resource": resource, "locator": None}


def _context(*steps: _Stored) -> UserContext:
    context = UserContext(user_uid=_USER)
    context.active_path_steps_rich = [{"step": step, "graph_context": {}} for step in steps]
    return context


def _retriever(cited: list[_Stored] | None = None) -> ContextRetriever:
    ps_backend = MagicMock()
    ps_backend.get_cited_resources = AsyncMock(return_value=Result.ok(cited or []))
    return ContextRetriever(ps_backend=ps_backend)


def _errors(logs: list[EventDict]) -> list[EventDict]:
    return [entry for entry in logs if entry["log_level"] == "error"]


@pytest.mark.anyio
async def test_the_bundle_step_holds_enum_members_and_datetimes() -> None:
    result = await _retriever().load_ps_bundle(_USER, _context(_stored_step()))

    assert result.is_ok, result
    step = result.value.path_step
    assert step.entity_type is EntityType.PATH_STEP
    assert step.status is EntityStatus.ACTIVE
    assert step.learning_level is LearningLevel.BEGINNER
    assert step.complexity is KuComplexity.ADVANCED
    assert step.sel_category is SELCategory.SELF_AWARENESS
    assert step.publication_state is PublicationState.PUBLISHED
    assert step.created_at == _CREATED_AT
    assert type(step.updated_at) is datetime
    assert step.updated_at == _UPDATED_AT
    assert type(step.last_applied_date) is datetime
    assert step.last_applied_date == _APPLIED_AT
    assert (step.title, step.intent) == ("Stored Shape", "Read the stored shape")


@pytest.mark.anyio
async def test_each_cited_resource_holds_enum_members_and_datetimes() -> None:
    retriever = _retriever([_stored_resource("resource.shape-book")])

    result = await retriever.load_ps_bundle(_USER, _context(_stored_step()))

    assert result.is_ok, result
    (resource,) = result.value.resources
    assert resource.entity_type is EntityType.RESOURCE
    assert resource.domain is Domain.KNOWLEDGE
    assert resource.created_at == datetime(2026, 11, 21, 3, 4, 53, 688000, tzinfo=UTC)
    assert type(resource.updated_at) is datetime
    assert resource.updated_at == _UPDATED_AT
    assert resource.explain_existence() == "Book resource.shape-book — by Some Author (1999)"


@pytest.mark.anyio
async def test_a_step_holding_a_value_its_field_cannot_read_is_refused_and_says_why() -> None:
    with capture_logs() as logs:
        result = await _retriever().load_ps_bundle(
            _USER, _context(_stored_step(learning_level="wizard"))
        )

    assert result.is_error
    assert result.expect_error().category is ErrorCategory.SYSTEM
    (logged,) = _errors(logs)
    assert _STEP_UID in logged["event"]
    assert "'wizard' is not a LearningLevel value" in logged["event"]


@pytest.mark.anyio
async def test_a_refused_step_leaves_the_answer_unguided() -> None:
    canon_service = MagicMock()
    canon_service.retrieve = AsyncMock()
    intent_classifier = MagicMock()
    intent_classifier.classify_intent = AsyncMock(return_value=Result.ok(QueryIntent.EXPLORATORY))
    intent_classifier.determine_guidance_mode = MagicMock(
        return_value=MagicMock(mode=GuidanceMode.SOCRATIC)
    )
    # Complete enough that a bundle which did build would reach a guided prompt.
    response_generator = MagicMock()
    response_generator.build_guided_system_prompt = MagicMock(return_value="guided prompt")
    entity_extractor = MagicMock()
    entity_extractor.extract_from_bundle = MagicMock(return_value=[])
    processor = QueryProcessor(
        intent_classifier=intent_classifier,
        response_generator=response_generator,
        entity_extractor=entity_extractor,
        context_retriever=_retriever([_stored_resource("resource.shape-book")]),
        user_service=MagicMock(),
        llm_service=MagicMock(),
        zpd_service=MagicMock(),
        canon_service=canon_service,
    )

    prompt, mode, ps_bundle, canon_context = await processor._run_guided_pipeline(
        _USER, "What is this step about?", _context(_stored_step(learning_level="wizard"))
    )

    assert (prompt, mode, ps_bundle) == (None, None, None)
    assert not canon_context.has_passages
    canon_service.retrieve.assert_not_awaited()


@pytest.mark.anyio
async def test_a_resource_holding_a_value_its_field_cannot_read_is_left_out_alone() -> None:
    retriever = _retriever(
        [
            _stored_resource("resource.bad-domain", domain="bogus"),
            _stored_resource("resource.good-book"),
        ]
    )

    with capture_logs() as logs:
        result = await retriever.load_ps_bundle(_USER, _context(_stored_step()))

    assert result.is_ok, result
    assert [resource.uid for resource in result.value.resources] == ["resource.good-book"]
    (logged,) = _errors(logs)
    assert "resource.bad-domain" in logged["event"]
    assert "'bogus' is not a Domain value" in logged["event"]


@pytest.mark.anyio
async def test_an_unexpected_failure_building_the_step_is_logged_with_its_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _broken(cls: type[PathStep], dto: object) -> PathStep:
        raise RuntimeError("a defect in the build")

    monkeypatch.setattr(PathStep, "from_dto", classmethod(_broken))

    with capture_logs() as logs:
        result = await _retriever().load_ps_bundle(_USER, _context(_stored_step()))

    assert result.is_error
    assert result.expect_error().category is ErrorCategory.SYSTEM
    (logged,) = _errors(logs)
    assert _STEP_UID in logged["event"]
    assert logged.get("exc_info") is True


@pytest.mark.anyio
async def test_a_step_with_no_uid_is_refused_and_says_why() -> None:
    with capture_logs() as logs:
        result = await _retriever().load_ps_bundle(_USER, _context(_stored_step(uid="")))

    assert result.is_error
    assert result.expect_error().category is ErrorCategory.SYSTEM
    (logged,) = _errors(logs)
    assert "no uid" in logged["event"]


@pytest.mark.anyio
async def test_no_step_in_progress_is_not_found_and_names_why() -> None:
    result = await _retriever().load_ps_bundle(_USER, _context())

    assert result.is_error
    error = result.expect_error()
    assert error.category is ErrorCategory.NOT_FOUND
    assert error.details["identifier"] == _USER
    assert error.details["reason"] == "no step in progress the learner has not mastered"
