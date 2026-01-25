"""
MOC Navigation Service - KU-Based MOC Architecture
===================================================

Navigation service for MOC patterns on KUs.

**January 2026 - MOC as KU Architecture:**
MOC is NOT a separate entity - it IS a Knowledge Unit that organizes other KUs.
A KU "is" a MOC when it has outgoing ORGANIZES relationships.

This service provides convenient access patterns for MOC-style navigation
while the underlying data is stored as KU nodes with ORGANIZES relationships.

**Key Concepts:**
- MOC = KU with children (ORGANIZES relationships)
- Section = KU with children within a MOC
- Same KU can be in multiple MOCs (many-to-many)
- Progress tracked on KU itself (unified across LS and MOC paths)

**Montessori-Inspired Pedagogy:**
MOC provides unstructured, learner-directed exploration as a parallel path
to LS (structured, teacher-directed curriculum).

Usage:
    # Check if a KU is a MOC (has organized children)
    is_moc = await moc_nav.is_moc("ku.python-reference")

    # Get a KU with its organized structure (the "MOC view")
    moc_view = await moc_nav.get_moc_view("ku.python-reference")

    # Organize one KU under another
    await moc_nav.organize("ku.python-reference", "ku.python-basics", order=1)

    # Find all MOCs that contain a KU
    mocs = await moc_nav.find_mocs_containing("ku.python-basics")

Version: 1.0.0
Date: 2026-01-20
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
    """A KU with its position in a MOC structure."""

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
class MocView:
    """
    A MOC view of a KU - the KU with its organized children hierarchy.

    This represents a KU acting as a MOC (Map of Content), showing
    the hierarchical organization of child KUs.
    """

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
            "is_moc": len(self.children) > 0,
        }


class MocNavigationService:
    """
    Navigation service for MOC patterns on KUs.

    MOC is not a separate entity - it's a KU with ORGANIZES relationships.
    This service provides convenient access patterns for MOC navigation.

    Two Paths to Knowledge (Montessori-Inspired):
    - LS Path: Structured, linear, teacher-directed curriculum
    - MOC Path: Unstructured, graph, learner-directed exploration

    Same KU, two access paths - progress is tracked on the KU itself.
    """

    def __init__(
        self,
        ku_service: "KuService",
        driver: "AsyncDriver",
    ) -> None:
        """
        Initialize MOC navigation service.

        Args:
            ku_service: KuService for KU operations
            driver: Neo4j driver for direct queries
        """
        self.ku_service = ku_service
        self.driver = driver
        self.logger = logger

    # =========================================================================
    # MOC IDENTITY OPERATIONS
    # =========================================================================

    async def is_moc(self, ku_uid: str) -> Result[bool]:
        """
        Check if a KU is acting as a MOC (has organized children).

        A KU "is" a MOC when it has outgoing ORGANIZES relationships.
        This is emergent identity - no special flag needed.

        Args:
            ku_uid: Knowledge Unit UID

        Returns:
            Result[bool]: True if KU has organized children
        """
        query = """
        MATCH (ku:Ku {uid: $ku_uid})
        OPTIONAL MATCH (ku)-[:ORGANIZES]->(child:Ku)
        RETURN ku IS NOT NULL AS ku_exists, count(child) > 0 AS is_moc
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

            return Result.ok(record["is_moc"])

        except Exception as e:
            self.logger.error(f"Error checking MOC status for {ku_uid}: {e}")
            return Result.fail(Errors.database(message=str(e), operation="is_moc"))

    async def get_moc_view(self, ku_uid: str, max_depth: int = 3) -> Result[MocView]:
        """
        Get a KU with its organized children hierarchy (the "MOC view").

        Returns the KU as a MOC root with all its organized children
        up to the specified depth.

        Args:
            ku_uid: Root KU UID
            max_depth: Maximum depth to traverse (default 3)

        Returns:
            Result[MocView]: The MOC view with hierarchy
        """
        # First verify the KU exists
        ku_result = await self.ku_service.get(ku_uid)
        if ku_result.is_error:
            return Result.fail(ku_result.expect_error())

        ku = ku_result.value
        if not ku:
            return Result.fail(Errors.not_found(resource="Ku", identifier=ku_uid))

        # Get organized children recursively
        children, total = await self._get_organized_children(ku_uid, max_depth)

        moc_view = MocView(
            root_uid=ku_uid,
            root_title=ku.title,
            children=children,
            total_kus=total,
        )

        return Result.ok(moc_view)

    async def _get_organized_children(
        self, parent_uid: str, max_depth: int, current_depth: int = 0
    ) -> tuple[list[OrganizedKu], int]:
        """
        Recursively get organized children of a KU.

        Returns:
            Tuple of (children list, total count)
        """
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

                # Recursively get grandchildren
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
    # MOC ORGANIZATION OPERATIONS
    # =========================================================================

    async def organize(
        self,
        parent_uid: str,
        child_uid: str,
        order: int = 0,
    ) -> Result[bool]:
        """
        Organize a KU under another KU (create ORGANIZES relationship).

        This makes the parent KU act as a MOC for the child KU.

        Args:
            parent_uid: Parent KU UID (the MOC/section)
            child_uid: Child KU UID (the content being organized)
            order: Order position (0-indexed)

        Returns:
            Result[bool]: True if relationship created successfully
        """
        # Verify both KUs exist
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

        # Create ORGANIZES relationship
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
                self.logger.info(f"Organized KU {child_uid} under {parent_uid} at position {order}")
                return Result.ok(True)

            return Result.ok(False)

        except Exception as e:
            self.logger.error(f"Error organizing {child_uid} under {parent_uid}: {e}")
            return Result.fail(Errors.database(message=str(e), operation="organize"))

    async def unorganize(self, parent_uid: str, child_uid: str) -> Result[bool]:
        """
        Remove organization relationship between KUs.

        Args:
            parent_uid: Parent KU UID
            child_uid: Child KU UID

        Returns:
            Result[bool]: True if relationship removed
        """
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
        """
        Change the order of a child KU within its parent MOC.

        Args:
            parent_uid: Parent KU UID
            child_uid: Child KU UID
            new_order: New order position

        Returns:
            Result[bool]: True if order updated
        """
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
    # MOC DISCOVERY OPERATIONS
    # =========================================================================

    async def find_mocs_containing(self, ku_uid: str) -> Result[list[dict[str, Any]]]:
        """
        Find all MOCs (parent KUs) that organize the given KU.

        Args:
            ku_uid: KU UID to find parents for

        Returns:
            Result[list]: List of parent MOCs with order info
        """
        query = """
        MATCH (moc:Ku)-[r:ORGANIZES]->(ku:Ku {uid: $ku_uid})
        RETURN moc.uid AS uid, moc.title AS title, r.order AS order
        ORDER BY moc.title
        """

        try:
            records, _, _ = await self.driver.execute_query(
                query,
                {"ku_uid": ku_uid},
            )

            mocs = [{"uid": r["uid"], "title": r["title"], "order": r["order"]} for r in records]

            return Result.ok(mocs)

        except Exception as e:
            self.logger.error(f"Error finding MOCs containing {ku_uid}: {e}")
            return Result.fail(Errors.database(message=str(e), operation="find_mocs_containing"))

    async def list_root_mocs(self, limit: int = 50) -> Result[list[dict[str, Any]]]:
        """
        List KUs that act as MOCs (have organized children) but are not
        themselves organized by other KUs (root MOCs).

        These are the top-level entry points for MOC navigation.

        Args:
            limit: Maximum number to return

        Returns:
            Result[list]: List of root MOC KUs
        """
        query = """
        MATCH (moc:Ku)-[:ORGANIZES]->(:Ku)
        WHERE NOT EXISTS((:Ku)-[:ORGANIZES]->(moc))
        WITH DISTINCT moc
        OPTIONAL MATCH (moc)-[:ORGANIZES]->(child:Ku)
        RETURN moc.uid AS uid, moc.title AS title, count(child) AS child_count
        ORDER BY moc.title
        LIMIT $limit
        """

        try:
            records, _, _ = await self.driver.execute_query(
                query,
                {"limit": limit},
            )

            mocs = [
                {"uid": r["uid"], "title": r["title"], "child_count": r["child_count"]}
                for r in records
            ]

            return Result.ok(mocs)

        except Exception as e:
            self.logger.error(f"Error listing root MOCs: {e}")
            return Result.fail(Errors.database(message=str(e), operation="list_root_mocs"))

    async def get_organized_children(self, ku_uid: str) -> Result[list[dict[str, Any]]]:
        """
        Get direct children of a KU organized by ORGANIZES relationship.

        Args:
            ku_uid: Parent KU UID

        Returns:
            Result[list]: List of child KUs with order
        """
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
