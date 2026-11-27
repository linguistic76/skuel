"""``get_task_urgency`` orders tasks by priority, then by due date.

HIGH first, then MEDIUM, then LOW, then a task that states no priority; within one
priority the earlier due date first and a task with no due date last. The key serves
both a ``Task`` and a ``TaskDTO`` (its one caller sorts DTOs), and a task read from a
stored node through either door holds its priority as the ``Priority`` member, so the
order of tasks read from the graph is decided by their priority too.
"""

from __future__ import annotations

from datetime import date

from adapters.persistence.neo4j.neo4j_mapper import from_neo4j_node
from core.models.enums import Priority
from core.models.task.task import Task, get_task_urgency
from core.models.task.task_dto import TaskDTO

EARLY = date(2026, 12, 1)
LATE = date(2026, 12, 20)


def _task(uid: str, priority: Priority | None, due_date: date | None = None) -> Task:
    return Task(uid=uid, title=uid, user_uid="user_test", priority=priority, due_date=due_date)


def _dto(uid: str, priority: Priority | None, due_date: date | None = None) -> TaskDTO:
    return TaskDTO(uid=uid, title=uid, user_uid="user_test", priority=priority, due_date=due_date)


def _order(tasks: list[Task] | list[TaskDTO]) -> list[str]:
    return [task.uid for task in sorted(tasks, key=get_task_urgency)]


class TestPriorityDecidesTheOrder:
    def test_high_medium_low_by_rank_not_by_word(self) -> None:
        tasks = [
            _task("task_low", Priority.LOW, EARLY),
            _task("task_medium", Priority.MEDIUM, EARLY),
            _task("task_high", Priority.HIGH, EARLY),
        ]

        assert _order(tasks) == ["task_high", "task_medium", "task_low"]

    def test_a_task_with_no_priority_sorts_after_low(self) -> None:
        tasks = [
            _task("task_none", None, EARLY),
            _task("task_low", Priority.LOW, LATE),
            _task("task_high", Priority.HIGH, LATE),
            _task("task_medium", Priority.MEDIUM, LATE),
        ]

        assert _order(tasks) == ["task_high", "task_medium", "task_low", "task_none"]

    def test_priority_outranks_an_earlier_due_date(self) -> None:
        tasks = [
            _task("task_low_soon", Priority.LOW, EARLY),
            _task("task_high_later", Priority.HIGH, LATE),
        ]

        assert _order(tasks) == ["task_high_later", "task_low_soon"]


class TestDueDateBreaksATie:
    def test_earlier_due_date_first_and_no_due_date_last(self) -> None:
        tasks = [
            _task("task_undated", Priority.HIGH),
            _task("task_late", Priority.HIGH, LATE),
            _task("task_early", Priority.HIGH, EARLY),
        ]

        assert _order(tasks) == ["task_early", "task_late", "task_undated"]

    def test_tasks_with_no_priority_order_by_due_date(self) -> None:
        tasks = [
            _task("task_undated", None),
            _task("task_late", None, LATE),
            _task("task_early", None, EARLY),
        ]

        assert _order(tasks) == ["task_early", "task_late", "task_undated"]


class TestTheKeyServesTheCallersShape:
    def test_dtos_sort_the_same_way(self) -> None:
        dtos = [
            _dto("task_none", None, EARLY),
            _dto("task_low", Priority.LOW, EARLY),
            _dto("task_high_late", Priority.HIGH, LATE),
            _dto("task_high_early", Priority.HIGH, EARLY),
            _dto("task_medium", Priority.MEDIUM, EARLY),
        ]

        assert _order(dtos) == [
            "task_high_early",
            "task_high_late",
            "task_medium",
            "task_low",
            "task_none",
        ]


def _stored(uid: str, priority: str, due_date: str) -> dict[str, object]:
    return {
        "uid": uid,
        "title": uid,
        "user_uid": "user_test",
        "entity_type": "task",
        "priority": priority,
        "due_date": due_date,
    }


class TestATaskReadFromTheGraphHoldsTheMember:
    def test_the_mapper_reads_the_stored_value_as_the_member(self) -> None:
        task = from_neo4j_node(_stored("task_high", "high", "2026-12-01"), Task)

        assert task.priority is Priority.HIGH

    def test_the_dto_reads_the_stored_value_as_the_member(self) -> None:
        dto = TaskDTO.from_dict(_stored("task_high", "high", "2026-12-01"))

        assert dto.priority is Priority.HIGH

    def test_tasks_read_through_the_mapper_sort_by_their_priority(self) -> None:
        tasks = [
            from_neo4j_node(_stored("task_low", "low", "2026-12-01"), Task),
            from_neo4j_node(_stored("task_high", "high", "2026-12-20"), Task),
            from_neo4j_node(_stored("task_medium", "medium", "2026-12-10"), Task),
        ]

        assert _order(tasks) == ["task_high", "task_medium", "task_low"]

    def test_tasks_read_through_the_dto_sort_by_their_priority(self) -> None:
        dtos = [
            TaskDTO.from_dict(_stored("task_low", "low", "2026-12-01")),
            TaskDTO.from_dict(_stored("task_high", "high", "2026-12-20")),
            TaskDTO.from_dict(_stored("task_medium", "medium", "2026-12-10")),
        ]

        assert _order(dtos) == ["task_high", "task_medium", "task_low"]
