"""
Activity Template Services — read surface for the 6 PS-owned template entities
================================================================================

Each template kind (Task/Goal/Habit/Event/Choice/Principle) gets a thin
:class:`BaseService` subclass over its UniversalNeo4jBackend. Templates are
PS-owned curriculum content, authored only in the content vault (ADR-091 S8): an
``_tmpl.md`` file writes the node and a PathStep's ``{domain}_template_uids:``
frontmatter writes the ``HAS_*_TEMPLATE`` edge. The app authors none of it.

The one member a caller uses is ``list_for_pathstep(ps_uid)`` — the templates
attached to a PathStep, read by the teacher's templates panel. ``BaseService``
still carries generic writers, so every consumer holds the read-only
:class:`~core.ports.template_protocols.ActivityTemplateOperations` instead of the
concrete class.

Each service declares its edge and its template label; the read binds both, so it
never returns a node of another kind, whatever an edge points at.
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
from core.ports import BackendOperations
from core.ports.template_protocols import TemplateAttachmentOperations
from core.services.base_service import BaseService
from core.services.domain_config import DomainConfig
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


class _BaseTemplateService[T: DomainModelProtocol](BaseService[BackendOperations[T], T]):
    """The read surface shared by all 6 Activity Template services.

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
        """The edge and far-end label this service reads by, or a system error."""
        if self._edge_name is None or self._template_label is None:
            return Result.fail(
                Errors.system(
                    message=(
                        f"{self.__class__.__name__} did not set _edge_name and "
                        "_template_label — its PathStep templates cannot be read."
                    ),
                    operation=operation,
                )
            )
        return Result.ok((self._edge_name, self._template_label))

    async def list_for_pathstep(self, ps_uid: str) -> Result[list[dict[str, Any]]]:
        """List the properties of this kind's templates attached to ``ps_uid``.

        Only a PathStep's edges to a template of this service's kind are read, so
        an edge to any other node is never returned. Returns raw property dicts
        (uid, title, status, ...) rather than domain models — the templates panel
        renders the dicts directly, so model rehydration would round-trip through
        the DTO for nothing.
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
