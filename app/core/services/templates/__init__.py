"""
Activity Template Services — CRUD facades for the 6 PS-owned template entities
================================================================================

Phase 5 of the PathStep + Activity Templates build (see plan at
``/home/mike/.claude/plans/skip-when-do-idempotent-shell.md``).

Each template kind (Task/Goal/Habit/Event/Choice/Principle) gets a thin
:class:`BaseService` subclass over its UniversalNeo4jBackend so that the route
layer can wire CRUD via :class:`CRUDRouteFactory`. Templates are PS-owned
curriculum content (no per-user state) — the services use ``ContentScope.SHARED``
at the route layer with TEACHER role gating.

Each service also exposes 3 PS-attachment helpers used by the per-template
route file's api_factory:

    attach_to_pathstep(ps_uid, template_uid)    → MERGE the HAS_*_TEMPLATE edge
    detach_from_pathstep(ps_uid, template_uid)  → DELETE the edge
    list_for_pathstep(ps_uid)                   → templates attached to a PS

These methods delegate to the shared executor used by ``PsEngagementService``
so the engagement service and the route layer see the same edges.

See:
    project_pathstep_activity_bridge.md (memory) — bridge contract overview
    project_pathstep_lifecycle_contract.md (memory) — lifecycle invariants
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from core.models.protocols import DomainModelProtocol
from core.models.templates.choice_template import ChoiceTemplate
from core.models.templates.choice_template_dto import ChoiceTemplateDTO
from core.models.templates.event_template import EventTemplate
from core.models.templates.event_template_dto import EventTemplateDTO
from core.models.templates.goal_template import GoalTemplate
from core.models.templates.goal_template_dto import GoalTemplateDTO
from core.models.templates.habit_template import HabitTemplate
from core.models.templates.habit_template_dto import HabitTemplateDTO
from core.models.templates.principle_template import PrincipleTemplate
from core.models.templates.principle_template_dto import PrincipleTemplateDTO
from core.models.templates.task_template import TaskTemplate
from core.models.templates.task_template_dto import TaskTemplateDTO
from core.ports import BackendOperations
from core.services.base_service import BaseService
from core.services.domain_config import DomainConfig
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor

logger = get_logger(__name__)


class _BaseTemplateService[T: DomainModelProtocol](BaseService[BackendOperations[T], T]):
    """Common CRUD + PS-attachment surface for all 6 Activity Template services.

    Subclasses set ``_config``, ``_edge_name``, and ``_service_name``. The edge
    name is the ``HAS_*_TEMPLATE`` relationship the engagement service walks at
    spawn time — keep these aligned with ``RelationshipName`` enum values.
    """

    _edge_name: ClassVar[str] = ""

    def __init__(
        self,
        backend: BackendOperations[T],
        executor: Neo4jQueryExecutor,
    ) -> None:
        super().__init__(backend, self._service_name or self.__class__.__name__)
        self.backend = backend
        self._executor = executor
        self.logger = logger  # type: ignore[assignment]  # structlog BoundLogger

    async def attach_to_pathstep(self, ps_uid: str, template_uid: str) -> Result[bool]:
        """MERGE the HAS_*_TEMPLATE edge between ``ps_uid`` and ``template_uid``.

        Idempotent: re-attaching is a no-op. Both nodes must already exist;
        otherwise the MATCH fails and a NotFound is returned.
        """
        if not self._edge_name:
            return Result.fail(
                Errors.system(
                    message=(
                        f"{self.__class__.__name__} did not set _edge_name — "
                        "PS attachment cannot be performed."
                    ),
                    operation="attach_to_pathstep",
                )
            )
        query = (
            "MATCH (ps {uid: $ps_uid}), (t {uid: $template_uid}) "
            f"MERGE (ps)-[:{self._edge_name}]->(t) "
            "RETURN ps.uid AS ps_uid, t.uid AS t_uid"
        )
        result: Result[list[dict[str, Any]]] = await self._executor.execute_write(
            query=query,
            params={"ps_uid": ps_uid, "template_uid": template_uid},
            operation="attach_template_to_pathstep",
        )
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.fail(
                Errors.not_found(
                    "PathStep or Template",
                    f"ps={ps_uid} template={template_uid}",
                )
            )
        return Result.ok(True)

    async def detach_from_pathstep(self, ps_uid: str, template_uid: str) -> Result[bool]:
        """DELETE the HAS_*_TEMPLATE edge.

        Idempotent: detaching an already-detached pair returns ``Result.ok(False)``.
        """
        if not self._edge_name:
            return Result.fail(
                Errors.system(
                    message=(
                        f"{self.__class__.__name__} did not set _edge_name — "
                        "PS detachment cannot be performed."
                    ),
                    operation="detach_from_pathstep",
                )
            )
        query = (
            "MATCH (ps {uid: $ps_uid})-[r:"
            f"{self._edge_name}"
            "]->(t {uid: $template_uid}) "
            "DELETE r RETURN count(r) AS removed"
        )
        result: Result[list[dict[str, Any]]] = await self._executor.execute_write(
            query=query,
            params={"ps_uid": ps_uid, "template_uid": template_uid},
            operation="detach_template_from_pathstep",
        )
        if result.is_error:
            return Result.fail(result)
        removed = bool(result.value and result.value[0].get("removed", 0))
        return Result.ok(removed)

    async def list_for_pathstep(self, ps_uid: str) -> Result[list[dict[str, Any]]]:
        """List template properties attached to ``ps_uid`` via this edge type.

        Returns raw property dicts (uid, title, status, ...) rather than
        domain models — the route layer JSON-serializes the dicts directly,
        and adding model rehydration here would just round-trip through DTO
        for no gain in the API surface.
        """
        if not self._edge_name:
            return Result.fail(
                Errors.system(
                    message=(
                        f"{self.__class__.__name__} did not set _edge_name — "
                        "list_for_pathstep cannot be performed."
                    ),
                    operation="list_for_pathstep",
                )
            )
        query = (
            "MATCH (ps {uid: $ps_uid})-[:"
            f"{self._edge_name}"
            "]->(t) "
            "RETURN properties(t) AS props "
            "ORDER BY t.created_at"
        )
        result: Result[list[dict[str, Any]]] = await self._executor.execute(
            query=query,
            params={"ps_uid": ps_uid},
            operation="list_templates_for_pathstep",
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["props"] for record in result.value])


class TaskTemplateService(_BaseTemplateService[TaskTemplate]):
    _service_name: ClassVar[str | None] = "task_templates"
    _edge_name: ClassVar[str] = "HAS_TASK_TEMPLATE"
    _config = DomainConfig(
        dto_class=TaskTemplateDTO,
        model_class=TaskTemplate,
        entity_label="Entity",
        search_fields=("title", "description"),
        search_order_by="created_at",
        user_ownership_relationship=None,
    )


class GoalTemplateService(_BaseTemplateService[GoalTemplate]):
    _service_name: ClassVar[str | None] = "goal_templates"
    _edge_name: ClassVar[str] = "HAS_GOAL_TEMPLATE"
    _config = DomainConfig(
        dto_class=GoalTemplateDTO,
        model_class=GoalTemplate,
        entity_label="Entity",
        search_fields=("title", "description", "vision_statement"),
        search_order_by="created_at",
        user_ownership_relationship=None,
    )


class HabitTemplateService(_BaseTemplateService[HabitTemplate]):
    _service_name: ClassVar[str | None] = "habit_templates"
    _edge_name: ClassVar[str] = "HAS_HABIT_TEMPLATE"
    _config = DomainConfig(
        dto_class=HabitTemplateDTO,
        model_class=HabitTemplate,
        entity_label="Entity",
        search_fields=("title", "description", "cue", "routine"),
        search_order_by="created_at",
        user_ownership_relationship=None,
    )


class EventTemplateService(_BaseTemplateService[EventTemplate]):
    _service_name: ClassVar[str | None] = "event_templates"
    _edge_name: ClassVar[str] = "HAS_EVENT_TEMPLATE"
    _config = DomainConfig(
        dto_class=EventTemplateDTO,
        model_class=EventTemplate,
        entity_label="Entity",
        search_fields=("title", "description", "event_type", "location"),
        search_order_by="created_at",
        user_ownership_relationship=None,
    )


class ChoiceTemplateService(_BaseTemplateService[ChoiceTemplate]):
    _service_name: ClassVar[str | None] = "choice_templates"
    _edge_name: ClassVar[str] = "HAS_CHOICE_TEMPLATE"
    _config = DomainConfig(
        dto_class=ChoiceTemplateDTO,
        model_class=ChoiceTemplate,
        entity_label="Entity",
        search_fields=("title", "description", "decision_rationale"),
        search_order_by="created_at",
        user_ownership_relationship=None,
    )


class PrincipleTemplateService(_BaseTemplateService[PrincipleTemplate]):
    _service_name: ClassVar[str | None] = "principle_templates"
    _edge_name: ClassVar[str] = "HAS_PRINCIPLE_TEMPLATE"
    _config = DomainConfig(
        dto_class=PrincipleTemplateDTO,
        model_class=PrincipleTemplate,
        entity_label="Entity",
        search_fields=("title", "description", "statement"),
        search_order_by="created_at",
        user_ownership_relationship=None,
    )


__all__ = [
    "ChoiceTemplateService",
    "EventTemplateService",
    "GoalTemplateService",
    "HabitTemplateService",
    "PrincipleTemplateService",
    "TaskTemplateService",
]
