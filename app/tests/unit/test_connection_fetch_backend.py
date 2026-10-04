"""Unit tests for ConnectionFetchBackend — the Activity pages' link reader (ADR-044).

The reader reads, in one statement, every edge of the domain's page-view types in
both directions (the registry's ``page_heading`` definitions, ADR-090 §2), and places
each row under the view that reads it. These tests mock the QueryExecutor and assert
the statement's shape and parameters, the placement by edge type / direction /
far-end label, the one-listing-per-heading rule, and the page-resilient
empty-on-error safety-net. The real-graph half is
tests/integration/routes/test_activity_page_links.py.
"""

from unittest.mock import AsyncMock

import pytest

from adapters.persistence.neo4j.connection_fetch_backend import ConnectionFetchBackend
from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_registry import LABEL_CONFIGS
from core.utils.result_simplified import Errors, Result


def _backend_returning(records: object) -> tuple[ConnectionFetchBackend, AsyncMock]:
    executor = AsyncMock()
    executor.execute_query = AsyncMock(return_value=records)
    return ConnectionFetchBackend(executor), executor.execute_query


def _row(
    rel_type: str,
    *,
    outgoing: bool,
    far: str,
    uid: str,
    title: str = "",
    entity_uid: str = "goal_1",
) -> dict[str, object]:
    return {
        "entity_uid": entity_uid,
        "rel_type": rel_type,
        "outgoing": outgoing,
        "far_labels": ["Entity", far],
        "connected_uid": uid,
        "title": title or uid,
        "connected_type": far.lower(),
    }


class TestTheStatement:
    @pytest.mark.asyncio
    async def test_empty_uids_short_circuits_without_query(self):
        backend, execute_query = _backend_returning(Result.ok([]))
        assert await backend.fetch_entity_connections(NeoLabel.TASK, []) == {}
        execute_query.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_label_with_no_page_views_reads_nothing(self):
        backend, execute_query = _backend_returning(Result.ok([]))
        assert await backend.fetch_entity_connections(NeoLabel.KU, ["ku_1"]) == {}
        execute_query.assert_not_called()

    @pytest.mark.asyncio
    async def test_reads_every_page_view_type_in_both_directions_behind_the_wall(self):
        backend, execute_query = _backend_returning(Result.ok([]))
        await backend.fetch_entity_connections(NeoLabel.GOAL, ["goal_1"])

        assert execute_query.await_args is not None
        query, params = execute_query.await_args.args
        page_types = {view.relationship.value for view in LABEL_CONFIGS["Goal"].page_views()}
        pattern = query.split("OPTIONAL MATCH (n)-[r:", 1)[1].split("]-(other:Entity)", 1)[0]
        assert set(pattern.split("|")) == page_types
        assert ":Entity:Goal" in query
        assert params == {"uids": ["goal_1"], "publication_draft": "draft"}
        # The far end is the anchor owner's own, or published shared content.
        assert "AS anchor_owners" in query
        assert "any(o IN far_owners WHERE o IN anchor_owners)" in query

    @pytest.mark.asyncio
    async def test_empty_on_result_error(self):
        backend, _ = _backend_returning(Result.fail(Errors.database("connections", "boom")))
        assert await backend.fetch_entity_connections(NeoLabel.TASK, ["task_1"]) == {}

    @pytest.mark.asyncio
    async def test_empty_on_executor_exception_safety_net(self):
        executor = AsyncMock()
        executor.execute_query = AsyncMock(side_effect=RuntimeError("driver down"))
        backend = ConnectionFetchBackend(executor)
        # Page-resilient: a Neo4j failure must not propagate.
        assert await backend.fetch_entity_connections(NeoLabel.TASK, ["task_1"]) == {}


class TestPlacement:
    @pytest.mark.asyncio
    async def test_each_row_is_placed_under_the_view_that_reads_it(self):
        backend, _ = _backend_returning(
            Result.ok(
                [
                    _row("SUPPORTS_GOAL", outgoing=False, far="Habit", uid="habit_1"),
                    _row("FULFILLS_GOAL", outgoing=False, far="Task", uid="task_1"),
                    # OPTIONAL MATCH miss → rel_type None → skipped.
                    {"entity_uid": "goal_2", "rel_type": None},
                ]
            )
        )
        result = await backend.fetch_entity_connections(NeoLabel.GOAL, ["goal_1", "goal_2"])

        assert {(row["heading"], row["connected_uid"]) for row in result["goal_1"]} == {
            ("Habits that support this goal", "habit_1"),
            ("Tasks that contribute to this goal", "task_1"),
        }
        assert "goal_2" not in result

    @pytest.mark.asyncio
    async def test_an_edge_in_the_direction_no_view_reads_is_left_out(self):
        # The goal reads SUPPORTS_GOAL incoming only; an outgoing one has no view.
        backend, _ = _backend_returning(
            Result.ok([_row("SUPPORTS_GOAL", outgoing=True, far="Habit", uid="habit_1")])
        )
        assert await backend.fetch_entity_connections(NeoLabel.GOAL, ["goal_1"]) == {}

    @pytest.mark.asyncio
    async def test_a_far_end_the_view_does_not_name_is_left_out(self):
        # The habit's REINFORCES_HABIT views name Task and Event; a Goal is neither.
        backend, _ = _backend_returning(
            Result.ok(
                [
                    _row(
                        "REINFORCES_HABIT",
                        outgoing=False,
                        far="Event",
                        uid="event_1",
                        entity_uid="habit_1",
                    ),
                    _row(
                        "REINFORCES_HABIT",
                        outgoing=False,
                        far="Goal",
                        uid="goal_1",
                        entity_uid="habit_1",
                    ),
                ]
            )
        )
        result = await backend.fetch_entity_connections(NeoLabel.HABIT, ["habit_1"])

        assert [(row["heading"], row["connected_uid"]) for row in result["habit_1"]] == [
            ("Events where this habit is practiced", "event_1")
        ]

    @pytest.mark.asyncio
    async def test_one_link_under_two_names_is_listed_once(self):
        # GUIDED_BY_PRINCIPLE out and GUIDES_GOAL in share the goal's heading.
        backend, _ = _backend_returning(
            Result.ok(
                [
                    _row("GUIDED_BY_PRINCIPLE", outgoing=True, far="Principle", uid="principle_1"),
                    _row("GUIDES_GOAL", outgoing=False, far="Principle", uid="principle_1"),
                ]
            )
        )
        result = await backend.fetch_entity_connections(NeoLabel.GOAL, ["goal_1"])

        assert [(row["heading"], row["connected_uid"]) for row in result["goal_1"]] == [
            ("Principles that support this goal", "principle_1")
        ]

    @pytest.mark.asyncio
    async def test_rows_follow_the_page_views_order_then_title(self):
        views = LABEL_CONFIGS["Goal"].page_views()
        first, last = views[0], views[-1]
        assert first.page_heading != last.page_heading
        records = [
            _row(
                last.relationship.value,
                outgoing=last.direction == "outgoing",
                far=last.target_label if last.target_label != "Entity" else "Ku",
                uid="b",
            ),
            _row(
                first.relationship.value,
                outgoing=first.direction == "outgoing",
                far=first.target_label if first.target_label != "Entity" else "Ku",
                uid="z",
                title="Zed",
            ),
            _row(
                first.relationship.value,
                outgoing=first.direction == "outgoing",
                far=first.target_label if first.target_label != "Entity" else "Ku",
                uid="a",
                title="Alpha",
            ),
        ]
        backend, _ = _backend_returning(Result.ok(records))
        result = await backend.fetch_entity_connections(NeoLabel.GOAL, ["goal_1"])

        assert [row["connected_uid"] for row in result["goal_1"]] == ["a", "z", "b"]


class TestFetchSourcePathstep:
    @pytest.mark.asyncio
    async def test_returns_uid_and_title_on_hit(self):
        backend, _ = _backend_returning(Result.ok([{"uid": "ps:demo:step-1", "title": "Intro"}]))
        assert await backend.fetch_source_pathstep("ps:demo:step-1", "user_owner") == {
            "uid": "ps:demo:step-1",
            "title": "Intro",
        }

    @pytest.mark.asyncio
    async def test_asks_for_a_published_step_or_one_the_owner_engaged(self):
        backend, execute_query = _backend_returning(Result.ok([]))
        await backend.fetch_source_pathstep("ps:demo:step-1", "user_owner")

        query, params = execute_query.call_args.args
        assert params == {
            "uid": "ps:demo:step-1",
            "owner_uid": "user_owner",
            "publication_draft": "draft",
        }
        assert "publication_state" in query
        assert "ENGAGED_WITH" in query

    @pytest.mark.asyncio
    async def test_none_for_empty_uid_without_querying(self):
        backend, execute_query = _backend_returning(Result.ok([]))
        assert await backend.fetch_source_pathstep("", "user_owner") is None
        execute_query.assert_not_called()

    @pytest.mark.asyncio
    async def test_none_when_pathstep_missing(self):
        backend, _ = _backend_returning(Result.ok([]))
        assert await backend.fetch_source_pathstep("ps:gone", "user_owner") is None

    @pytest.mark.asyncio
    async def test_none_on_query_error(self):
        backend, _ = _backend_returning(Result.fail(Errors.database("lookup", "boom")))
        assert await backend.fetch_source_pathstep("ps:demo:step-1", "user_owner") is None

    @pytest.mark.asyncio
    async def test_none_on_executor_exception_safety_net(self):
        executor = AsyncMock()
        executor.execute_query = AsyncMock(side_effect=RuntimeError("driver down"))
        backend = ConnectionFetchBackend(executor)
        assert await backend.fetch_source_pathstep("ps:demo:step-1", "user_owner") is None

    @pytest.mark.asyncio
    async def test_falls_back_to_uid_when_title_null(self):
        backend, _ = _backend_returning(Result.ok([{"uid": "ps:demo:step-1", "title": None}]))
        assert await backend.fetch_source_pathstep("ps:demo:step-1", "user_owner") == {
            "uid": "ps:demo:step-1",
            "title": "ps:demo:step-1",
        }
