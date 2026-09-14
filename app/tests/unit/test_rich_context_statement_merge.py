"""
``execute_mega_query`` merges the registry's partials and refuses a half-answer.

Every ``RICH_CONTEXT_STATEMENTS`` entry returns one row for a user that exists
and none for one that does not; the executor merges the one-row partials into
the ``mega_data`` map. The verdicts on the row counts are the point of this
module: no row anywhere is the unknown-user sentinel, and a row from some
statements but not others is a statement whose aggregation collapsed to zero
rows — the shape that once emptied a whole rich context silently (a learner
whose every insight was dismissed) — so it fails loudly rather than merging
what arrived.
"""

from __future__ import annotations

from typing import Any

import pytest

from adapters.persistence.neo4j.user_context_queries import (
    RICH_CONTEXT_STATEMENTS,
    UserContextQueryExecutor,
    merge_partial_context,
)
from core.models.type_hints import UserUID
from core.utils.result_simplified import Errors, Result

_USER_UID = UserUID("user_test")


class _FakeExecutor:
    """Answers each registered statement with the rows scripted for it."""

    def __init__(self, rows_by_statement: dict[str, list[dict[str, Any]] | Exception]) -> None:
        self._rows = rows_by_statement
        self.params_seen: list[dict[str, Any]] = []

    async def execute_query(
        self, query: str, params: dict[str, Any] | None = None
    ) -> Result[list[dict[str, Any]]]:
        self.params_seen.append(params or {})
        name = next(name for name, text in RICH_CONTEXT_STATEMENTS if text == query)
        scripted = self._rows[name]
        if isinstance(scripted, Exception):
            return Result.fail(Errors.database(operation="execute_query", message=str(scripted)))
        return Result.ok(scripted)


def _one_row(partial: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"result": partial}]


_PARTIALS: dict[str, dict[str, Any]] = {
    "tasks_and_goals": {
        "uids": {"active_task_uids": ["t1"], "active_goal_uids": ["g1"]},
        "entities": {"tasks": [{"entity": {"uid": "t1"}}], "goals": []},
        "progress_counts": {"tasks_completed": 0, "tasks_total": 1},
    },
    "habits_and_events": {
        "uids": {"active_habit_uids": ["h1"], "upcoming_event_uids": []},
        "entities": {"habits": [{"entity": {"uid": "h1"}}], "events": []},
    },
    "principles_and_choices": {
        "uids": {"core_principle_uids": [], "pending_choice_uids": []},
        "entities": {"principles": [], "choices": []},
    },
    "knowledge": {
        "uids": {"knowledge_mastery": [{"uid": "ku1", "score": 0.9}], "ku_view_data": []},
        "rich": {"knowledge": [{"uid": "ku1"}]},
    },
    "curriculum": {
        "uids": {"enrolled_path_uids": ["lp1"], "active_moc_uids": []},
        "entities": {"learning_paths": [], "path_steps": []},
        "rich": {"learning_paths": [], "path_steps": []},
    },
    "learner_state": {
        "life_path": {"uid": "lp.life", "alignment_score": 0.5},
        "activity_report": None,
        "active_insights_raw": [],
    },
}


def test_merge_folds_shared_sections_and_takes_owned_ones_whole() -> None:
    merged: dict[str, Any] = {}
    for partial in _PARTIALS.values():
        merge_partial_context(merged, partial)

    assert sorted(merged) == [
        "active_insights_raw",
        "activity_report",
        "entities",
        "life_path",
        "progress_counts",
        "rich",
        "uids",
    ]
    # a section five statements contribute to holds every key, from every one of them
    assert sorted(merged["uids"]) == [
        "active_goal_uids",
        "active_habit_uids",
        "active_moc_uids",
        "active_task_uids",
        "core_principle_uids",
        "enrolled_path_uids",
        "knowledge_mastery",
        "ku_view_data",
        "pending_choice_uids",
        "upcoming_event_uids",
    ]
    assert sorted(merged["entities"]) == [
        "choices",
        "events",
        "goals",
        "habits",
        "learning_paths",
        "path_steps",
        "principles",
        "tasks",
    ]
    assert sorted(merged["rich"]) == ["knowledge", "learning_paths", "path_steps"]
    # a section one statement owns arrives as is — including a null
    assert merged["life_path"] == {"uid": "lp.life", "alignment_score": 0.5}
    assert merged["activity_report"] is None
    assert merged["active_insights_raw"] == []


@pytest.mark.asyncio
async def test_every_statement_runs_with_the_one_parameter_map() -> None:
    fake = _FakeExecutor({name: _one_row(partial) for name, partial in _PARTIALS.items()})

    result = await UserContextQueryExecutor(fake).execute_mega_query(_USER_UID, min_confidence=0.5)

    assert result.is_ok, result.error
    assert len(fake.params_seen) == len(RICH_CONTEXT_STATEMENTS)
    assert all(params == fake.params_seen[0] for params in fake.params_seen)
    assert fake.params_seen[0]["user_uid"] == _USER_UID
    assert fake.params_seen[0]["min_confidence"] == 0.5
    assert result.value["uids"]["active_task_uids"] == ["t1"]
    assert result.value["uids"]["enrolled_path_uids"] == ["lp1"]
    assert result.value["life_path"]["uid"] == "lp.life"


@pytest.mark.asyncio
async def test_no_row_from_any_statement_is_the_unknown_user_sentinel() -> None:
    fake = _FakeExecutor({name: [] for name in _PARTIALS})

    result = await UserContextQueryExecutor(fake).execute_mega_query(_USER_UID)

    assert result.is_ok
    assert result.value == {"uids": {}, "entities": {}, "rich": {}}


@pytest.mark.asyncio
async def test_a_row_from_some_statements_but_not_others_fails_loudly() -> None:
    """A collapsed aggregation must not merge as 'this learner has none of that'."""
    rows: dict[str, list[dict[str, Any]] | Exception] = {
        name: _one_row(partial) for name, partial in _PARTIALS.items()
    }
    rows["learner_state"] = []
    fake = _FakeExecutor(rows)

    result = await UserContextQueryExecutor(fake).execute_mega_query(_USER_UID)

    assert result.is_error
    message = result.expect_error().message
    assert "['learner_state']" in message
    assert "returned no row" in message


@pytest.mark.asyncio
async def test_a_failed_statement_fails_the_read() -> None:
    rows: dict[str, list[dict[str, Any]] | Exception] = {
        name: _one_row(partial) for name, partial in _PARTIALS.items()
    }
    rows["knowledge"] = RuntimeError("connection reset")
    fake = _FakeExecutor(rows)

    result = await UserContextQueryExecutor(fake).execute_mega_query(_USER_UID)

    assert result.is_error
    assert "connection reset" in result.expect_error().message
