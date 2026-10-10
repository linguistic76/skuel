"""
Activity Template Services — CRUD facades for the 6 PS-owned template entities
================================================================================

Phase 5 of the PathStep + Activity Templates build.

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

The service admits both ends by kind: ``ps_uid`` must name a PathStep and
``template_uid`` a template of this service's own kind. Each service declares its
edge and its template label; the attachment statements bind both, so an attach or
detach naming anything else matches nothing and answers not-found — whatever the
uid is, another user's Goal included — and the list never reads a node of another
kind.
"""

from __future__ import annotations

from typing import Any, ClassVar

from core.models.enums.neo_labels import NeoLabel
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
from core.models.update_contracts import RawChanges
from core.models.validation_rules import ONLINE_URL_REQUIRED, patch_leaves_online_without_url
from core.ports import BackendOperations
from core.ports.template_protocols import TemplateAttachmentOperations
from core.services.base_service import BaseService
from core.services.domain_config import DomainConfig
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


class _BaseTemplateService[T: DomainModelProtocol](BaseService[BackendOperations[T], T]):
    """Common CRUD + PS-attachment surface for all 6 Activity Template services.

    Subclasses set ``_config``, ``_edge_name``, ``_template_label`` and
    ``_service_name``. The edge name is the ``HAS_*_TEMPLATE`` ``RelationshipName``
    the engagement service walks at spawn time; the template label is the kind the
    edge's far end must carry. The enum typing makes both a compile-time-safe seam.
    """

    _edge_name: ClassVar[RelationshipName | None] = None
    _template_label: ClassVar[NeoLabel | None] = None

    def __init__(
        self,
        backend: BackendOperations[T],
        attachment: TemplateAttachmentOperations,
    ) -> None:
        super().__init__(backend, self._service_name or self.__class__.__name__)
        self.backend = backend
        self._attachment = attachment
        self.logger = logger  # type: ignore[assignment]  # structlog BoundLogger

    def _attachment_kind(self, operation: str) -> Result[tuple[RelationshipName, NeoLabel]]:
        """The edge and far-end label this service attaches by, or a system error."""
        if self._edge_name is None or self._template_label is None:
            return Result.fail(
                Errors.system(
                    message=(
                        f"{self.__class__.__name__} did not set _edge_name and "
                        "_template_label — PS attachment cannot be performed."
                    ),
                    operation=operation,
                )
            )
        return Result.ok((self._edge_name, self._template_label))

    @staticmethod
    def _not_found(ps_uid: str, template_uid: str) -> Result[bool]:
        # One answer for a missing uid and a node of the wrong kind, at either end.
        return Result.fail(
            Errors.not_found("PathStep or Template", f"ps={ps_uid} template={template_uid}")
        )

    async def attach_to_pathstep(self, ps_uid: str, template_uid: str) -> Result[bool]:
        """Attach this template to the PathStep ``ps_uid``.

        Idempotent: re-attaching is a no-op. ``ps_uid`` must name a PathStep and
        ``template_uid`` a template of this service's kind; otherwise nothing is
        written and a NotFound is returned, alike for a missing uid and the wrong
        kind. Backend: ``TemplateAttachmentBackend.attach``.
        """
        kind = self._attachment_kind("attach_to_pathstep")
        if kind.is_error:
            return Result.fail(kind)
        edge_name, template_label = kind.value
        result = await self._attachment.attach(ps_uid, template_uid, edge_name, template_label)
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return self._not_found(ps_uid, template_uid)
        return Result.ok(True)

    async def detach_from_pathstep(self, ps_uid: str, template_uid: str) -> Result[bool]:
        """Detach this template from the PathStep ``ps_uid``.

        Admits both ends as ``attach_to_pathstep`` does — a pair that is not a
        PathStep and a template of this kind is a NotFound. Idempotent: detaching
        an already-detached right-kind pair returns ``Result.ok(False)``.
        Backend: ``TemplateAttachmentBackend.detach``.
        """
        kind = self._attachment_kind("detach_from_pathstep")
        if kind.is_error:
            return Result.fail(kind)
        edge_name, template_label = kind.value
        result = await self._attachment.detach(ps_uid, template_uid, edge_name, template_label)
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return self._not_found(ps_uid, template_uid)
        return Result.ok(bool(result.value[0].get("removed", 0)))

    async def list_for_pathstep(self, ps_uid: str) -> Result[list[dict[str, Any]]]:
        """List the properties of this kind's templates attached to ``ps_uid``.

        Only a PathStep's edges to a template of this service's kind are read, so
        an edge to any other node is never returned. Returns raw property dicts
        (uid, title, status, ...) rather than domain models — the route layer
        JSON-serializes the dicts directly, and adding model rehydration here
        would just round-trip through DTO for no gain in the API surface.
        Backend: ``TemplateAttachmentBackend.list_for_pathstep``.
        """
        kind = self._attachment_kind("list_for_pathstep")
        if kind.is_error:
            return Result.fail(kind)
        edge_name, template_label = kind.value
        result = await self._attachment.list_for_pathstep(ps_uid, edge_name, template_label)
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["props"] for record in result.value])


class TaskTemplateService(_BaseTemplateService[TaskTemplate]):
    _service_name: ClassVar[str | None] = "task_templates"
    _edge_name: ClassVar[RelationshipName] = RelationshipName.HAS_TASK_TEMPLATE
    _template_label: ClassVar[NeoLabel] = NeoLabel.TASK_TEMPLATE
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
    _template_label: ClassVar[NeoLabel] = NeoLabel.GOAL_TEMPLATE
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
    _template_label: ClassVar[NeoLabel] = NeoLabel.HABIT_TEMPLATE
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
    _template_label: ClassVar[NeoLabel] = NeoLabel.EVENT_TEMPLATE
    _config = DomainConfig(
        dto_class=EventTemplateDTO,
        model_class=EventTemplate,
        entity_label="Entity",
        search_fields=("title", "description", "event_type", "location"),
        search_order_by="created_at",
        user_ownership_relationship=None,
    )

    def _validate_update(self, current: EventTemplate, updates: RawChanges) -> Result[None]:
        """An online template needs a meeting URL, judged on the merged state.

        Spawning copies ``is_online`` and ``meeting_url`` onto every engaging learner's
        Event, so the rule ``EventTemplateCreateRequest`` holds at creation holds here
        too. A patch naming neither field passes (see ``patch_leaves_online_without_url``).
        """
        if patch_leaves_online_without_url(
            updates.to_changes(), is_online=current.is_online, meeting_url=current.meeting_url
        ):
            return Result.fail(Errors.validation(message=ONLINE_URL_REQUIRED, field="meeting_url"))
        return Result.ok(None)


class ChoiceTemplateService(_BaseTemplateService[ChoiceTemplate]):
    _service_name: ClassVar[str | None] = "choice_templates"
    _edge_name: ClassVar[RelationshipName] = RelationshipName.HAS_CHOICE_TEMPLATE
    _template_label: ClassVar[NeoLabel] = NeoLabel.CHOICE_TEMPLATE
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
    _template_label: ClassVar[NeoLabel] = NeoLabel.PRINCIPLE_TEMPLATE
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
