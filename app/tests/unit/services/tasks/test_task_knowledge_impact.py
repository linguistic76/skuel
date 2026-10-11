"""A task's knowledge impact names the knowledge the task links in the graph.

``analyze_task_knowledge_impact`` scores the task from its own fields and reads the
knowledge it applies, requires or was inferred to touch from its edges.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from core.models.enums import EntityStatus
from core.models.task.task import Task
from core.services.tasks._orchestration_mixin import _OrchestrationMixin
from core.services.tasks.task_relationships import TaskRelationships
from core.utils.result_simplified import Result

NOW = datetime(2026, 1, 5, tzinfo=UTC)


class _Tasks(_OrchestrationMixin):
    def __init__(self, task: Task) -> None:
        self.get_task = AsyncMock(return_value=Result.ok(task))
        self.relationships = Mock()


async def test_the_combined_knowledge_is_the_tasks_graph_links(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fetch(task_uid: str, _service: object) -> TaskRelationships:
        assert task_uid == "task_impact"
        return TaskRelationships(
            applies_knowledge_uids=["ku.impact.applied"],
            prerequisite_knowledge_uids=["ku.impact.required"],
            inferred_knowledge_uids=["ku.impact.applied"],
        )

    monkeypatch.setattr(TaskRelationships, "fetch", fetch)
    task = Task(
        uid="task_impact",
        title="Impact",
        user_uid="user_impact",
        status=EntityStatus.ACTIVE,
        created_at=NOW,
        updated_at=NOW,
    )

    result = await _Tasks(task).analyze_task_knowledge_impact("task_impact")

    assert result.is_ok, result
    assert result.value["combined_knowledge_uids"] == {"ku.impact.applied", "ku.impact.required"}
    assert result.value["task_uid"] == "task_impact"
