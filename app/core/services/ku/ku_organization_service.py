"""
KU Organization Service — ORGANIZES Relationship Management
============================================================

Manages hierarchical organization of Knowledge Units via ORGANIZES relationships.

Any Ku can organize other Kus — this is emergent identity, not a type discriminator.
A Ku "is an organizer" when it has outgoing ORGANIZES relationships.

**Two Paths to Knowledge (Montessori-Inspired):**
- LS Path: Structured, linear, teacher-directed curriculum
- ORGANIZES Path: Unstructured, graph, learner-directed exploration

Same Ku, two access paths — progress is tracked on the Ku itself.

See: /docs/architecture/CURRICULUM_GROUPING_PATTERNS.md
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from adapters.persistence.neo4j.domain_backends import KuBackend
    from core.services.ku_service import KuService

logger = get_logger(__name__)


@dataclass
class OrganizedKu:
    """A Ku with its position in an organization hierarchy."""

    uid: str
    title: str
    order: int
    children: list["OrganizedKu"] = field(default_factory=list)

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
class OrganizationView:
    """A Ku viewed as an organizer — with its organized children hierarchy."""

    root_uid: str
    root_title: str
    children: list[OrganizedKu] = field(default_factory=list)
    total_kus: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "root_uid": self.root_uid,
            "root_title": self.root_title,
            "children": [c.to_dict() for c in self.children],
            "total_kus": self.total_kus,
            "is_organizer": len(self.children) > 0,
        }


class KuOrganizationService:
    """
    Organization service for ORGANIZES relationships on Kus.

    Any Ku can organize other Kus — not limited to a specific EntityType.
    This service provides convenient access patterns for hierarchical navigation.
    """

    def __init__(
        self,
        ku_service: "KuService",
        backend: "KuBackend",
    ) -> None:
        self.ku_service = ku_service
        self.backend = backend
        self.logger = logger

    # =========================================================================
    # IDENTITY OPERATIONS
    # =========================================================================

    async def is_organizer(self, ku_uid: str) -> Result[bool]:
        """Check if a Ku has organized children (outgoing ORGANIZES relationships)."""
        return await self.backend.is_organizer(ku_uid)

    async def get_organization_view(
        self, ku_uid: str, max_depth: int = 3
    ) -> Result[OrganizationView]:
        """Get a Ku with its organized children hierarchy."""
        ku_result = await self.ku_service.get(ku_uid)
        if ku_result.is_error:
            return Result.fail(ku_result.expect_error())

        ku = ku_result.value
        if not ku:
            return Result.fail(Errors.not_found(resource="Ku", identifier=ku_uid))

        children, total = await self._get_organized_children(ku_uid, max_depth)

        view = OrganizationView(
            root_uid=ku_uid,
            root_title=ku.title,
            children=children,
            total_kus=total,
        )

        return Result.ok(view)

    async def _get_organized_children(
        self, parent_uid: str, max_depth: int, current_depth: int = 0
    ) -> tuple[list[OrganizedKu], int]:
        """Recursively get organized children of a Ku."""
        if current_depth >= max_depth:
            return [], 0

        result = await self.backend.get_organized_children(parent_uid)
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
                OrganizedKu(
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
        """Organize a Ku under another Ku (create ORGANIZES relationship)."""
        parent_result = await self.ku_service.get(parent_uid)
        if parent_result.is_error:
            return Result.fail(parent_result.expect_error())
        if not parent_result.value:
            return Result.fail(Errors.not_found(resource="Ku (parent)", identifier=parent_uid))

        child_result = await self.ku_service.get(child_uid)
        if child_result.is_error:
            return Result.fail(child_result.expect_error())
        if not child_result.value:
            return Result.fail(Errors.not_found(resource="Ku (child)", identifier=child_uid))

        return await self.backend.organize(parent_uid, child_uid, order)

    async def unorganize(self, parent_uid: str, child_uid: str) -> Result[bool]:
        """Remove organization relationship between Kus."""
        return await self.backend.unorganize(parent_uid, child_uid)

    async def reorder(self, parent_uid: str, child_uid: str, new_order: int) -> Result[bool]:
        """Change the order of a child Ku within its parent."""
        return await self.backend.reorder(parent_uid, child_uid, new_order)

    # =========================================================================
    # DISCOVERY OPERATIONS
    # =========================================================================

    async def find_organizers(self, ku_uid: str) -> Result[list[dict[str, Any]]]:
        """Find all parent Kus that organize the given Ku."""
        return await self.backend.find_organizers(ku_uid)

    async def list_root_organizers(self, limit: int = 50) -> Result[list[dict[str, Any]]]:
        """List Kus that organize others but are not themselves organized (root organizers)."""
        return await self.backend.list_root_organizers(limit)

    async def get_organized_children(self, ku_uid: str) -> Result[list[dict[str, Any]]]:
        """Get direct children of a Ku organized by ORGANIZES relationship."""
        return await self.backend.get_organized_children(ku_uid)
