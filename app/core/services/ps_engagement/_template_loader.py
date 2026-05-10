"""_TemplateLoader — load every template attached to a PathStep.

Walks the 6 ``HAS_*_TEMPLATE`` edges in one Cypher pass per domain and hydrates
the results into the typed ``TemplateBundle`` consumed by the validator and
spawn orchestrator.

This is the single read path for "what templates does this PS own?" — the
validator and orchestrator share one bundle per call so we don't double-query.
"""

from __future__ import annotations

from typing import Any

from core.models.relationship_names import RelationshipName
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

from ._validator import TemplateBundle

logger = get_logger(__name__)


class _TemplateLoader:
    """Reads PS-attached template nodes via the 6 template backends."""

    def __init__(
        self,
        executor: Any,
        task_template_backend: Any,
        goal_template_backend: Any,
        habit_template_backend: Any,
        event_template_backend: Any,
        choice_template_backend: Any,
        principle_template_backend: Any,
    ) -> None:
        self._executor = executor
        self._tasks = task_template_backend
        self._goals = goal_template_backend
        self._habits = habit_template_backend
        self._events = event_template_backend
        self._choices = choice_template_backend
        self._principles = principle_template_backend

    async def load(self, ps_uid: str) -> Result[TemplateBundle]:
        """Fetch all templates for one PS. Empty bundle if PS has none."""
        from core.models.templates.choice_template import ChoiceTemplate
        from core.models.templates.event_template import EventTemplate
        from core.models.templates.goal_template import GoalTemplate
        from core.models.templates.habit_template import HabitTemplate
        from core.models.templates.principle_template import PrincipleTemplate
        from core.models.templates.task_template import TaskTemplate

        rel_to_backend_and_class: list[tuple[RelationshipName, Any, type]] = [
            (RelationshipName.HAS_TASK_TEMPLATE, self._tasks, TaskTemplate),
            (RelationshipName.HAS_GOAL_TEMPLATE, self._goals, GoalTemplate),
            (RelationshipName.HAS_HABIT_TEMPLATE, self._habits, HabitTemplate),
            (RelationshipName.HAS_EVENT_TEMPLATE, self._events, EventTemplate),
            (RelationshipName.HAS_CHOICE_TEMPLATE, self._choices, ChoiceTemplate),
            (RelationshipName.HAS_PRINCIPLE_TEMPLATE, self._principles, PrincipleTemplate),
        ]

        results: dict[type, list[Any]] = {}
        for rel, backend, cls in rel_to_backend_and_class:
            uids_res = await self._fetch_template_uids(ps_uid, rel)
            if uids_res.is_error:
                return Result.fail(uids_res)

            instances: list[Any] = []
            for uid in uids_res.value:
                inst_res = await backend.get_by_uid(uid)
                if inst_res.is_error:
                    return Result.fail(inst_res)
                if inst_res.value is None:
                    return Result.fail(
                        Errors.database(
                            operation="load_template",
                            message=(
                                f"Template UID {uid} attached to PS {ps_uid} via "
                                f"{rel.value} but the node could not be loaded — "
                                f"possible orphan edge."
                            ),
                        )
                    )
                instances.append(inst_res.value)
            results[cls] = instances

        return Result.ok(
            TemplateBundle(
                ps_uid=ps_uid,
                tasks=tuple(results[TaskTemplate]),
                goals=tuple(results[GoalTemplate]),
                habits=tuple(results[HabitTemplate]),
                events=tuple(results[EventTemplate]),
                choices=tuple(results[ChoiceTemplate]),
                principles=tuple(results[PrincipleTemplate]),
            )
        )

    async def _fetch_template_uids(self, ps_uid: str, rel: RelationshipName) -> Result[list[str]]:
        # rel.value is from a closed enum, not user input — safe to interpolate.
        query = f"""
        MATCH (ps {{uid: $ps_uid}})-[:{rel.value}]->(t)
        RETURN t.uid AS uid
        ORDER BY t.uid
        """
        result = await self._executor.execute(
            query=query,
            params={"ps_uid": ps_uid},
            operation=f"fetch_{rel.value.lower()}_uids",
        )
        if result.is_error:
            return Result.fail(result)
        records: list[dict[str, Any]] = result.value
        return Result.ok([r["uid"] for r in records])
