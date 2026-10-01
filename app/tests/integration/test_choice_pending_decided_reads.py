"""
The Choices backend counts and lists pending and decided as the model defines them.

``Choice.is_pending`` / ``Choice.is_decided`` are the one definition; their Cypher
spelling (``query/cypher/choice_fragments.py``) is composed by the Choices backend's
count and list reads and by the user context's ``pending_choice_uids``. Every legal
Choice status is seeded with and without a ``decided_at``, the models are read back,
and each composing read must select exactly the rows the model's predicate selects.
"""

from __future__ import annotations

from datetime import datetime

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.backends.activity_backends import ChoicesBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from adapters.persistence.neo4j.user_context_queries import UserContextQueryExecutor
from core.models.choice.choice import Choice
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.type_hints import UserUID
from core.models.user.user import User
from core.services.user.user_context_builder import UserContextBuilder

_OWNER = "user_choice_vocabulary"
_STRANGER = "user_choice_vocabulary_stranger"
_DECIDED_AT = datetime(2026, 9, 1, 12, 0)
_DEADLINE = datetime(2026, 9, 20, 9, 0)
_BY = "2026-12-31"


@pytest_asyncio.fixture
async def choices(neo4j_driver, clean_neo4j) -> ChoicesBackend:
    """One choice per (status, decided or not) for the owner, plus a stranger's open one."""
    async with neo4j_driver.session() as session:
        await session.run("UNWIND $uids AS uid MERGE (:User {uid: uid})", uids=[_OWNER, _STRANGER])
    backend = ChoicesBackend(neo4j_driver, NeoLabel.CHOICE, Choice, base_label=NeoLabel.ENTITY)
    seeds = [
        Choice(
            uid=f"choice_{status.value}_{'decided' if decided_at else 'open'}",
            title="which way",
            user_uid=_OWNER,
            status=status,
            decided_at=decided_at,
            decision_deadline=_DEADLINE,
        )
        for status in EntityType.CHOICE.valid_statuses()
        for decided_at in (None, _DECIDED_AT)
    ]
    seeds.append(
        Choice(
            uid="choice_strangers_open",
            title="not yours",
            user_uid=_STRANGER,
            status=EntityStatus.ACTIVE,
            decision_deadline=_DEADLINE,
        )
    )
    for seed in seeds:
        created = await backend.create(seed)
        assert created.is_ok, created.expect_error()
    return backend


async def _models(backend: ChoicesBackend) -> list[Choice]:
    found = await backend.find_by(user_uid=_OWNER)
    assert found.is_ok, found.expect_error()
    assert len(found.value) == 2 * len(EntityType.CHOICE.valid_statuses())
    return list(found.value)


@pytest.mark.asyncio
async def test_the_seed_holds_every_answer(choices: ChoicesBackend) -> None:
    """The comparison below is only worth something if both predicates split the rows."""
    models = await _models(choices)

    pending = {c.uid for c in models if c.is_pending()}
    decided = {c.uid for c in models if c.is_decided()}
    assert pending == {"choice_draft_open", "choice_active_open"}
    assert "choice_active_decided" in decided and "choice_completed_open" in decided
    assert "choice_archived_open" not in pending | decided


@pytest.mark.asyncio
async def test_stats_count_what_the_model_counts(choices: ChoicesBackend) -> None:
    models = await _models(choices)

    stats = await choices.get_stats_for_user(_OWNER)

    assert stats.is_ok, stats.expect_error()
    assert stats.value == {
        "total": len(models),
        "pending": sum(1 for c in models if c.is_pending()),
        "decided": sum(1 for c in models if c.is_decided()),
    }
    assert stats.value["pending"] == 2


@pytest.mark.asyncio
async def test_the_pending_list_is_the_models_pending_set(choices: ChoicesBackend) -> None:
    models = await _models(choices)

    listed = await choices.get_pending_choices(_OWNER)

    assert listed.is_ok, listed.expect_error()
    assert {row["uid"] for row in listed.value} == {c.uid for c in models if c.is_pending()}


@pytest.mark.asyncio
async def test_only_a_pending_choice_needs_a_decision(choices: ChoicesBackend) -> None:
    models = await _models(choices)

    due = await choices.get_choices_needing_decision(_OWNER, _BY)

    assert due.is_ok, due.expect_error()
    assert {row["uid"] for row in due.value} == {c.uid for c in models if c.is_pending()}


@pytest.mark.asyncio
async def test_a_choice_stored_without_a_status_reads_as_pending_on_both_sides(
    choices: ChoicesBackend, neo4j_driver
) -> None:
    async with neo4j_driver.session() as session:
        await session.run("MATCH (c:Entity {uid: 'choice_active_open'}) REMOVE c.status")
    models = await _models(choices)
    unstatused = next(c for c in models if c.uid == "choice_active_open")
    assert unstatused.is_pending()

    listed = await choices.get_pending_choices(_OWNER)
    stats = await choices.get_stats_for_user(_OWNER)

    assert listed.is_ok and stats.is_ok
    assert "choice_active_open" in {row["uid"] for row in listed.value}
    assert stats.value["pending"] == sum(1 for c in models if c.is_pending()) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("depth", ["standard", "rich"])
async def test_the_user_context_lists_the_models_pending_set(
    choices: ChoicesBackend, neo4j_driver, depth: str
) -> None:
    """Both context depths read ``pending_choice_uids`` through their own statement."""
    models = await _models(choices)
    builder = UserContextBuilder(UserContextQueryExecutor(Neo4jQueryExecutor(neo4j_driver)))
    owner = UserUID(_OWNER)
    user = User(uid=_OWNER, title="vocabulary", email="vocabulary@test.com")

    built = await (
        builder.build_rich_user_context(owner, user)
        if depth == "rich"
        else builder.build_user_context(owner, user)
    )

    assert built.is_ok, built.error
    assert set(built.value.pending_choice_uids) == {c.uid for c in models if c.is_pending()}
    assert "choice_active_decided" not in built.value.pending_choice_uids
