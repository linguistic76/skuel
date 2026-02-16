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
    from neo4j import AsyncDriver

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

    Any Ku can organize other Kus — not limited to a specific KuType.
    This service provides convenient access patterns for hierarchical navigation.
    """

    def __init__(
        self,
        ku_service: "KuService",
        driver: "AsyncDriver",
    ) -> None:
        self.ku_service = ku_service
        self.driver = driver
        self.logger = logger

    # =========================================================================
    # IDENTITY OPERATIONS
    # =========================================================================

    async def is_organizer(self, ku_uid: str) -> Result[bool]:
        """Check if a Ku has organized children (outgoing ORGANIZES relationships)."""
        query = """
        MATCH (ku:Ku {uid: $ku_uid})
        OPTIONAL MATCH (ku)-[:ORGANIZES]->(child:Ku)
        RETURN ku IS NOT NULL AS ku_exists, count(child) > 0 AS is_organizer
        """

        try:
            records, _, _ = await self.driver.execute_query(
                query,
                {"ku_uid": ku_uid},
            )

            if not records:
                return Result.fail(Errors.not_found(resource="Ku", identifier=ku_uid))

            record = records[0]
            if not record["ku_exists"]:
                return Result.fail(Errors.not_found(resource="Ku", identifier=ku_uid))

            return Result.ok(record["is_organizer"])

        except Exception as e:
            self.logger.error(f"Error checking organizer status for {ku_uid}: {e}")
            return Result.fail(Errors.database(message=str(e), operation="is_organizer"))

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

        query = """
        MATCH (parent:Ku {uid: $parent_uid})-[r:ORGANIZES]->(child:Ku)
        RETURN child.uid AS uid, child.title AS title, r.order AS order
        ORDER BY r.order ASC
        """

        try:
            records, _, _ = await self.driver.execute_query(
                query,
                {"parent_uid": parent_uid},
            )

            children = []
            total = 0

            for record in records:
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

        except Exception as e:
            self.logger.error(
                "Error getting organized children - returning empty",
                extra={
                    "parent_uid": parent_uid,
                    "current_depth": current_depth,
                    "max_depth": max_depth,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            return [], 0

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

        query = """
        MATCH (parent:Ku {uid: $parent_uid})
        MATCH (child:Ku {uid: $child_uid})
        MERGE (parent)-[r:ORGANIZES]->(child)
        SET r.order = $order
        RETURN true AS success
        """

        try:
            records, _, _ = await self.driver.execute_query(
                query,
                {"parent_uid": parent_uid, "child_uid": child_uid, "order": order},
            )

            if records and records[0]["success"]:
                self.logger.info(f"Organized Ku {child_uid} under {parent_uid} at position {order}")
                return Result.ok(True)

            return Result.ok(False)

        except Exception as e:
            self.logger.error(f"Error organizing {child_uid} under {parent_uid}: {e}")
            return Result.fail(Errors.database(message=str(e), operation="organize"))

    async def unorganize(self, parent_uid: str, child_uid: str) -> Result[bool]:
        """Remove organization relationship between Kus."""
        query = """
        MATCH (parent:Ku {uid: $parent_uid})-[r:ORGANIZES]->(child:Ku {uid: $child_uid})
        DELETE r
        RETURN true AS success
        """

        try:
            records, _, _ = await self.driver.execute_query(
                query,
                {"parent_uid": parent_uid, "child_uid": child_uid},
            )

            success = bool(records and records[0]["success"])
            if success:
                self.logger.info(f"Removed organization of {child_uid} from {parent_uid}")

            return Result.ok(success)

        except Exception as e:
            self.logger.error(f"Error removing organization: {e}")
            return Result.fail(Errors.database(message=str(e), operation="unorganize"))

    async def reorder(self, parent_uid: str, child_uid: str, new_order: int) -> Result[bool]:
        """Change the order of a child Ku within its parent."""
        query = """
        MATCH (parent:Ku {uid: $parent_uid})-[r:ORGANIZES]->(child:Ku {uid: $child_uid})
        SET r.order = $new_order
        RETURN true AS success
        """

        try:
            records, _, _ = await self.driver.execute_query(
                query,
                {"parent_uid": parent_uid, "child_uid": child_uid, "new_order": new_order},
            )

            return Result.ok(bool(records and records[0]["success"]))

        except Exception as e:
            self.logger.error(f"Error reordering: {e}")
            return Result.fail(Errors.database(message=str(e), operation="reorder"))

    # =========================================================================
    # DISCOVERY OPERATIONS
    # =========================================================================

    async def find_organizers(self, ku_uid: str) -> Result[list[dict[str, Any]]]:
        """Find all parent Kus that organize the given Ku."""
        query = """
        MATCH (parent:Ku)-[r:ORGANIZES]->(ku:Ku {uid: $ku_uid})
        RETURN parent.uid AS uid, parent.title AS title, r.order AS order
        ORDER BY parent.title
        """

        try:
            records, _, _ = await self.driver.execute_query(
                query,
                {"ku_uid": ku_uid},
            )

            organizers = [
                {"uid": r["uid"], "title": r["title"], "order": r["order"]} for r in records
            ]

            return Result.ok(organizers)

        except Exception as e:
            self.logger.error(f"Error finding organizers of {ku_uid}: {e}")
            return Result.fail(Errors.database(message=str(e), operation="find_organizers"))

    async def list_root_organizers(self, limit: int = 50) -> Result[list[dict[str, Any]]]:
        """List Kus that organize others but are not themselves organized (root organizers)."""
        query = """
        MATCH (root:Ku)-[:ORGANIZES]->(:Ku)
        WHERE NOT EXISTS((:Ku)-[:ORGANIZES]->(root))
        WITH DISTINCT root
        OPTIONAL MATCH (root)-[:ORGANIZES]->(child:Ku)
        RETURN root.uid AS uid, root.title AS title, count(child) AS child_count
        ORDER BY root.title
        LIMIT $limit
        """

        try:
            records, _, _ = await self.driver.execute_query(
                query,
                {"limit": limit},
            )

            roots = [
                {"uid": r["uid"], "title": r["title"], "child_count": r["child_count"]}
                for r in records
            ]

            return Result.ok(roots)

        except Exception as e:
            self.logger.error(f"Error listing root organizers: {e}")
            return Result.fail(Errors.database(message=str(e), operation="list_root_organizers"))

    async def get_organized_children(self, ku_uid: str) -> Result[list[dict[str, Any]]]:
        """Get direct children of a Ku organized by ORGANIZES relationship."""
        query = """
        MATCH (parent:Ku {uid: $ku_uid})-[r:ORGANIZES]->(child:Ku)
        RETURN child.uid AS uid, child.title AS title, r.order AS order
        ORDER BY r.order ASC
        """

        try:
            records, _, _ = await self.driver.execute_query(
                query,
                {"ku_uid": ku_uid},
            )

            children = [
                {"uid": r["uid"], "title": r["title"], "order": r["order"]} for r in records
            ]

            return Result.ok(children)

        except Exception as e:
            self.logger.error(f"Error getting organized children: {e}")
            return Result.fail(Errors.database(message=str(e), operation="get_organized_children"))
