"""
PathStep Organization Service — ORGANIZES Relationship Management
==================================================================

Manages hierarchical organization of PathSteps via ORGANIZES relationships.

Any PathStep can organize other PathSteps — this is emergent identity,
not a type discriminator. A PathStep "is an organizer" when it has outgoing
ORGANIZES relationships.

**Two Paths to Knowledge (Montessori-Inspired):**
- LP Path: Structured, linear, teacher-directed curriculum
- ORGANIZES Path: Unstructured, graph, learner-directed exploration

Same PathStep, two access paths — progress is tracked on the PathStep itself.

See: /docs/architecture/CURRICULUM_GROUPING_PATTERNS.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from core.models.pathways.path_step import PathStep
    from core.ports.curriculum_protocols import PsOrganizesBackendOperations
    from core.services.ps.ps_core_service import PsCoreService

from core.models.enums.entity_enums import ContentOrigin, EntityType
from core.ports.query_types import OrganizerResult, RootOrganizerResult
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.services.ps.organization")

# The entity types this service's reads may return. The PathStep API answers
# unauthenticated callers (curriculum is shared content), and the ORGANIZES edge
# joins any two entities — a personal-vault ``moc: true`` UserEntry organizes
# PathSteps too. Every read here is therefore scoped to shared curriculum by
# ``entity_type``, so a user-owned organizer, child or root never leaves the
# graph through this door. Derived from the enum, never hand-listed.
SHARED_CURRICULUM_TYPES: Final[tuple[str, ...]] = tuple(
    t.value for t in EntityType if t.content_origin() is ContentOrigin.CURRICULUM
)


@dataclass
class OrganizedStep:
    """A PathStep with its position in an organization hierarchy."""

    uid: str
    title: str
    order: int
    children: list[OrganizedStep] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "uid": self.uid,
            "title": self.title,
            "order": self.order,
            "children": [c.to_dict() for c in self.children],
            "is_leaf": len(self.children) == 0,
        }


@dataclass
class StepOrganizationView:
    """A PathStep viewed as an organizer — with its organized children hierarchy."""

    root_uid: str
    root_title: str
    children: list[OrganizedStep] = field(default_factory=list)
    total_steps: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "root_uid": self.root_uid,
            "root_title": self.root_title,
            "children": [c.to_dict() for c in self.children],
            "total_steps": self.total_steps,
            "is_organizer": len(self.children) > 0,
        }


@dataclass(frozen=True)
class StepNavigation:
    """Previous/next sibling in MOC ORGANIZES order."""

    prev_uid: str | None = None
    prev_title: str | None = None
    next_uid: str | None = None
    next_title: str | None = None


class PsOrganizationService:
    """
    Organization service for ORGANIZES relationships on PathSteps.

    Any PathStep can organize other PathSteps — not limited to a specific EntityType.
    This service provides convenient access patterns for hierarchical navigation.

    Two guards make it safe behind the unauthenticated PathStep API:

    - **The subject is a PathStep.** Every read and the create resolve their uid
      through ``ps_core`` (a ``:PathStep`` match) and answer not-found for any
      other entity, so a user-owned entity is never the subject of a read here.
    - **The other end is shared curriculum.** Organizers, children and roots are
      scoped to ``SHARED_CURRICULUM_TYPES`` on the backend query, so a personal
      map that organizes a PathStep is not returned as its organizer and never
      appears as a root.

    ``unorganize`` and ``reorder`` act on an existing edge by its two uids and
    carry no guard — they are admin-only at the route.
    """

    def __init__(
        self,
        ps_core: PsCoreService,
        backend: PsOrganizesBackendOperations,
    ) -> None:
        self.ps_core = ps_core
        self.backend = backend
        self.logger = logger

    # =========================================================================
    # IDENTITY OPERATIONS
    # =========================================================================

    async def _require_path_step(self, ps_uid: str) -> Result[PathStep]:
        """The subject of a read or a create, or not-found when it is not a PathStep."""
        ps_result = await self.ps_core.get(ps_uid)
        if ps_result.is_error:
            return Result.fail(ps_result)
        if not ps_result.value:
            return Result.fail(Errors.not_found(resource="PathStep", identifier=ps_uid))
        return Result.ok(ps_result.value)

    async def is_organizer(self, ps_uid: str) -> Result[bool]:
        """Check if a PathStep has organized children (outgoing ORGANIZES relationships)."""
        subject = await self._require_path_step(ps_uid)
        if subject.is_error:
            return Result.fail(subject)
        return await self.backend.is_organizer(ps_uid)

    async def get_organization_view(
        self, ps_uid: str, max_depth: int = 3
    ) -> Result[StepOrganizationView]:
        """Get a PathStep with its organized children hierarchy."""
        subject = await self._require_path_step(ps_uid)
        if subject.is_error:
            return Result.fail(subject)
        ps = subject.value

        children, total = await self._get_organized_children(ps_uid, max_depth)

        view = StepOrganizationView(
            root_uid=ps_uid,
            root_title=ps.title,
            children=children,
            total_steps=total,
        )

        return Result.ok(view)

    async def _get_organized_children(
        self, parent_uid: str, max_depth: int, current_depth: int = 0
    ) -> tuple[list[OrganizedStep], int]:
        """Recursively get organized children of a PathStep."""
        if current_depth >= max_depth:
            return [], 0

        result = await self.backend.get_organized_children(
            parent_uid, child_types=SHARED_CURRICULUM_TYPES
        )
        if result.is_error:
            self.logger.error(
                "Error getting organized children - returning empty",
                extra={
                    "parent_uid": parent_uid,
                    "current_depth": current_depth,
                    "max_depth": max_depth,
                    "error_message": str(result.error),
                },
            )
            return [], 0

        children = []
        total = 0

        for record in result.value:
            child_uid = record["uid"]
            child_title = record["title"]
            order = record["order"] or 0

            grandchildren, grandchild_count = await self._get_organized_children(
                child_uid, max_depth, current_depth + 1
            )

            children.append(
                OrganizedStep(
                    uid=child_uid,
                    title=child_title,
                    order=order,
                    children=grandchildren,
                )
            )
            total += 1 + grandchild_count

        return children, total

    # =========================================================================
    # ORGANIZATION OPERATIONS
    # =========================================================================

    async def organize(
        self,
        parent_uid: str,
        child_uid: str,
        order: int = 0,
    ) -> Result[bool]:
        """Organize a PathStep under another PathStep (create ORGANIZES relationship)."""
        parent = await self._require_path_step(parent_uid)
        if parent.is_error:
            return Result.fail(parent)
        child = await self._require_path_step(child_uid)
        if child.is_error:
            return Result.fail(child)

        return await self.backend.organize(parent_uid, child_uid, order)

    async def unorganize(self, parent_uid: str, child_uid: str) -> Result[bool]:
        """Remove organization relationship between PathSteps."""
        return await self.backend.unorganize(parent_uid, child_uid)

    async def reorder(self, parent_uid: str, child_uid: str, new_order: int) -> Result[bool]:
        """Change the order of a child PathStep within its parent."""
        return await self.backend.reorder(parent_uid, child_uid, new_order)

    # =========================================================================
    # DISCOVERY OPERATIONS
    # =========================================================================

    async def get_navigation(self, ps_uid: str) -> Result[StepNavigation]:
        """Get prev/next sibling in MOC ORGANIZES order.

        Database errors are propagated (not hidden). Legitimate empty states
        (no organizers, not found in children) return empty StepNavigation.
        """
        subject = await self._require_path_step(ps_uid)
        if subject.is_error:
            return Result.fail(subject)

        organizers_result = await self.backend.find_organizers(
            ps_uid, organizer_types=SHARED_CURRICULUM_TYPES
        )
        if organizers_result.is_error:
            return Result.fail(organizers_result)

        if not organizers_result.value:
            return Result.ok(StepNavigation())

        moc_uid = organizers_result.value[0].get("uid")
        moc_view_result = await self.get_organization_view(moc_uid, max_depth=1)
        if moc_view_result.is_error:
            return Result.fail(moc_view_result)

        children = moc_view_result.value.children

        current_idx = None
        for idx, child in enumerate(children):
            if child.uid == ps_uid:
                current_idx = idx
                break

        if current_idx is None:
            return Result.ok(StepNavigation())

        prev_step = children[current_idx - 1] if current_idx > 0 else None
        next_step = children[current_idx + 1] if current_idx < len(children) - 1 else None

        return Result.ok(
            StepNavigation(
                prev_uid=prev_step.uid if prev_step else None,
                prev_title=prev_step.title if prev_step else None,
                next_uid=next_step.uid if next_step else None,
                next_title=next_step.title if next_step else None,
            )
        )

    async def find_organizers(self, ps_uid: str) -> Result[list[OrganizerResult]]:
        """The shared-curriculum organizers of a PathStep; not-found for any other subject."""
        subject = await self._require_path_step(ps_uid)
        if subject.is_error:
            return Result.fail(subject)
        return await self.backend.find_organizers(ps_uid, organizer_types=SHARED_CURRICULUM_TYPES)

    async def list_root_organizers(self, limit: int = 50) -> Result[list[RootOrganizerResult]]:
        """Shared-curriculum entities that organize others and are organized by nothing."""
        return await self.backend.list_root_organizers(limit, root_types=SHARED_CURRICULUM_TYPES)

    async def get_organized_children(self, ps_uid: str) -> Result[list[OrganizerResult]]:
        """The shared-curriculum children a PathStep organizes; not-found for any other subject."""
        subject = await self._require_path_step(ps_uid)
        if subject.is_error:
            return Result.fail(subject)
        return await self.backend.get_organized_children(
            ps_uid, child_types=SHARED_CURRICULUM_TYPES
        )
