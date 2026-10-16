"""
Activity Template Services — read surface for the 6 PS-owned template entities
================================================================================

Each template kind (Task/Goal/Habit/Event/Choice/Principle) gets a read-only
service that names its edge and its template label. Templates are PS-owned
curriculum content, authored only in the content vault (ADR-091 S8): an
``_tmpl.md`` file writes the node and a PathStep's ``{domain}_template_uids:``
frontmatter writes the ``HAS_*_TEMPLATE`` edge. The app authors none of it, so
a service holds no entity backend and no writer: only the attachment port and
``list_for_pathstep(ps_uid)``, the templates attached to a PathStep, read by the
teacher's templates panel.

The read binds the edge and the label, so it never returns a node of another
kind, whatever an edge points at.
"""

from __future__ import annotations

from typing import Any, ClassVar

from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName
from core.ports.template_protocols import TemplateAttachmentOperations
from core.utils.result_simplified import Result


class _BaseTemplateService:
    """The read surface shared by all 6 Activity Template services.

    Subclasses set ``_edge_name``, the ``HAS_*_TEMPLATE`` ``RelationshipName``
    the engagement service walks at spawn time, and ``_template_label``, the
    kind the edge's far end must carry. The enum typing makes both a
    compile-time-safe seam.
    """

    _edge_name: ClassVar[RelationshipName]
    _template_label: ClassVar[NeoLabel]

    def __init__(self, attachment: TemplateAttachmentOperations) -> None:
        self._attachment = attachment

    async def list_for_pathstep(self, ps_uid: str) -> Result[list[dict[str, Any]]]:
        """List the properties of this kind's templates attached to ``ps_uid``.

        Only a PathStep's edges to a template of this service's kind are read, so
        an edge to any other node is never returned. Returns raw property dicts
        (uid, title, status, ...) rather than domain models — the templates panel
        renders the dicts directly, so model rehydration would round-trip through
        the DTO for nothing.
        Backend: ``TemplateAttachmentBackend.list_for_pathstep``.
        """
        result = await self._attachment.list_for_pathstep(
            ps_uid, self._edge_name, self._template_label
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["props"] for record in result.value])


class TaskTemplateService(_BaseTemplateService):
    _edge_name: ClassVar[RelationshipName] = RelationshipName.HAS_TASK_TEMPLATE
    _template_label: ClassVar[NeoLabel] = NeoLabel.TASK_TEMPLATE


class GoalTemplateService(_BaseTemplateService):
    _edge_name: ClassVar[RelationshipName] = RelationshipName.HAS_GOAL_TEMPLATE
    _template_label: ClassVar[NeoLabel] = NeoLabel.GOAL_TEMPLATE


class HabitTemplateService(_BaseTemplateService):
    _edge_name: ClassVar[RelationshipName] = RelationshipName.HAS_HABIT_TEMPLATE
    _template_label: ClassVar[NeoLabel] = NeoLabel.HABIT_TEMPLATE


class EventTemplateService(_BaseTemplateService):
    _edge_name: ClassVar[RelationshipName] = RelationshipName.HAS_EVENT_TEMPLATE
    _template_label: ClassVar[NeoLabel] = NeoLabel.EVENT_TEMPLATE


class ChoiceTemplateService(_BaseTemplateService):
    _edge_name: ClassVar[RelationshipName] = RelationshipName.HAS_CHOICE_TEMPLATE
    _template_label: ClassVar[NeoLabel] = NeoLabel.CHOICE_TEMPLATE


class PrincipleTemplateService(_BaseTemplateService):
    _edge_name: ClassVar[RelationshipName] = RelationshipName.HAS_PRINCIPLE_TEMPLATE
    _template_label: ClassVar[NeoLabel] = NeoLabel.PRINCIPLE_TEMPLATE


__all__ = [
    "ChoiceTemplateService",
    "EventTemplateService",
    "GoalTemplateService",
    "HabitTemplateService",
    "PrincipleTemplateService",
    "TaskTemplateService",
]
