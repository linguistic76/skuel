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

from typing import Any, ClassVar

from core.models.protocols import DomainModelProtocol
from core.models.relationship_names import RelationshipName
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
from core.ports.template_protocols import TemplateAttachmentOperations
from core.services.base_service import BaseService
from core.services.domain_config import DomainConfig
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


class _BaseTemplateService[T: DomainModelProtocol](BaseService[BackendOperations[T], T]):
    """Common CRUD + PS-attachment surface for all 6 Activity Template services.

    Subclasses set ``_config``, ``_edge_name``, and ``_service_name``. The edge
    name is the ``HAS_*_TEMPLATE`` ``RelationshipName`` the engagement service
    walks at spawn time; the enum typing makes it a compile-time-safe seam.
    """

    _edge_name: ClassVar[RelationshipName | None] = None

    def __init__(
        self,
        backend: BackendOperations[T],
        attachment: TemplateAttachmentOperations,
    ) -> None:
        super().__init__(backend, self._service_name or self.__class__.__name__)
        self.backend = backend
        self._attachment = attachment
        self.logger = logger  # type: ignore[assignment]  # structlog BoundLogger

    async def attach_to_pathstep(self, ps_uid: str, template_uid: str) -> Result[bool]:
        """Attach this template to the PathStep ``ps_uid``.

        Idempotent: re-attaching is a no-op. Both nodes must already exist;
        otherwise a NotFound is returned.
        """
        if self._edge_name is None:
            return Result.fail(
                Errors.system(
                    message=(
                        f"{self.__class__.__name__} did not set _edge_name — "
                        "PS attachment cannot be performed."
                    ),
                    operation="attach_to_pathstep",
                )
            )
        result = await self._attachment.attach(ps_uid, template_uid, self._edge_name)
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
        """Detach this template from the PathStep ``ps_uid``.

        Idempotent: detaching an already-detached pair returns ``Result.ok(False)``.
        """
        if self._edge_name is None:
            return Result.fail(
                Errors.system(
                    message=(
                        f"{self.__class__.__name__} did not set _edge_name — "
                        "PS detachment cannot be performed."
                    ),
                    operation="detach_from_pathstep",
                )
            )
        result = await self._attachment.detach(ps_uid, template_uid, self._edge_name)
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
        if self._edge_name is None:
            return Result.fail(
                Errors.system(
                    message=(
                        f"{self.__class__.__name__} did not set _edge_name — "
                        "list_for_pathstep cannot be performed."
                    ),
                    operation="list_for_pathstep",
                )
            )
        result = await self._attachment.list_for_pathstep(ps_uid, self._edge_name)
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["props"] for record in result.value])


class TaskTemplateService(_BaseTemplateService[TaskTemplate]):
    _service_name: ClassVar[str | None] = "task_templates"
    _edge_name: ClassVar[RelationshipName] = RelationshipName.HAS_TASK_TEMPLATE
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
    _edge_name: ClassVar[RelationshipName] = RelationshipName.HAS_GOAL_TEMPLATE
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
    _edge_name: ClassVar[RelationshipName] = RelationshipName.HAS_HABIT_TEMPLATE
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
    _edge_name: ClassVar[RelationshipName] = RelationshipName.HAS_EVENT_TEMPLATE
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
    _edge_name: ClassVar[RelationshipName] = RelationshipName.HAS_CHOICE_TEMPLATE
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
    _edge_name: ClassVar[RelationshipName] = RelationshipName.HAS_PRINCIPLE_TEMPLATE
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
