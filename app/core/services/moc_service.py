"""
MOC Service - KU-Based Architecture
====================================

THE single owner for all Map of Content operations in SKUEL.

**January 2026 - MOC as KU Architecture:**
MOC is NOT a separate entity - it IS a Knowledge Unit that organizes other KUs.
A KU "is" a MOC when it has outgoing ORGANIZES relationships.

This service is a thin facade over MocNavigationService, providing
MOC-specific semantics on top of KU operations.

**Key Concepts:**
- MOC = KU with children (ORGANIZES relationships)
- Section = KU with children within a MOC
- Same KU can be in multiple MOCs (many-to-many)
- Progress tracked on KU itself (unified across LS and MOC paths)

**Two Paths to Knowledge (Montessori-Inspired):**
- LS Path: Structured, linear, teacher-directed curriculum
- MOC Path: Unstructured, graph, learner-directed exploration

Same KU, two access paths - progress is tracked on the KU itself.

Following SKUEL principles:
- One path forward: MOCService delegates to MocNavigationService
- Fail-fast: Requires ku_service and driver
- No backward compatibility: Old MapOfContent/MOCSection entities removed

Version: 2.0.0 (KU-based architecture)
Date: 2026-01-20
"""

from typing import TYPE_CHECKING, Any

from core.services.moc.moc_navigation_service import MocNavigationService, MocView
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from core.services.ku_service import KuService

logger = get_logger(__name__)


class MOCService:
    """
    Facade for Map of Content operations.

    MOC is a KU that organizes other KUs via ORGANIZES relationships.
    This service provides MOC-specific semantics on top of KuService.

    **Architecture (January 2026 - KU-based):**
    - MocNavigationService: All MOC navigation and organization operations
    - KuService: Underlying KU CRUD operations

    **Usage:**
    ```python
    # Check if a KU acts as a MOC
    is_moc = await moc_service.is_moc("ku.python-reference")

    # Get MOC view (KU with organized children)
    moc_view = await moc_service.get("ku.python-reference")

    # Organize KUs (create MOC structure)
    await moc_service.organize("ku.python-reference", "ku.python-basics", order=1)

    # Find MOCs containing a KU
    mocs = await moc_service.find_mocs_containing("ku.python-basics")
    ```
    """

    def __init__(
        self,
        ku_service: "KuService",
        driver: "AsyncDriver",
    ) -> None:
        """
        Initialize MOC service.

        FAIL-FAST: Both ku_service and driver are REQUIRED.

        Args:
            ku_service: KuService for KU operations - REQUIRED
            driver: Neo4j AsyncDriver for graph operations - REQUIRED
        """
        if not ku_service:
            raise ValueError(
                "MOCService ku_service is REQUIRED. SKUEL follows fail-fast architecture."
            )
        if not driver:
            raise ValueError("MOCService driver is REQUIRED. SKUEL follows fail-fast architecture.")

        self.ku_service = ku_service
        self.driver = driver
        self.navigation = MocNavigationService(ku_service=ku_service, driver=driver)
        self.logger = logger

        logger.debug("MOCService initialized (KU-based architecture)")

    # =========================================================================
    # MOC IDENTITY OPERATIONS
    # =========================================================================

    async def is_moc(self, ku_uid: str) -> Result[bool]:
        """
        Check if a KU is acting as a MOC (has organized children).

        A KU "is" a MOC when it has outgoing ORGANIZES relationships.

        Args:
            ku_uid: Knowledge Unit UID

        Returns:
            Result[bool]: True if KU has organized children
        """
        return await self.navigation.is_moc(ku_uid)

    async def get(self, ku_uid: str, max_depth: int = 3) -> Result[MocView]:
        """
        Get a KU as a MOC view (with organized children hierarchy).

        Args:
            ku_uid: Root KU UID
            max_depth: Maximum depth to traverse (default 3)

        Returns:
            Result[MocView]: The MOC view with hierarchy
        """
        return await self.navigation.get_moc_view(ku_uid, max_depth)

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
            Result[bool]: True if relationship created
        """
        return await self.navigation.organize(parent_uid, child_uid, order)

    async def unorganize(self, parent_uid: str, child_uid: str) -> Result[bool]:
        """
        Remove organization relationship between KUs.

        Args:
            parent_uid: Parent KU UID
            child_uid: Child KU UID

        Returns:
            Result[bool]: True if relationship removed
        """
        return await self.navigation.unorganize(parent_uid, child_uid)

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
        return await self.navigation.reorder(parent_uid, child_uid, new_order)

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
        return await self.navigation.find_mocs_containing(ku_uid)

    async def list_root_mocs(self, limit: int = 50) -> Result[list[dict[str, Any]]]:
        """
        List KUs that act as root MOCs (organize others, not organized themselves).

        These are top-level entry points for MOC navigation.

        Args:
            limit: Maximum number to return

        Returns:
            Result[list]: List of root MOC KUs
        """
        return await self.navigation.list_root_mocs(limit)

    async def get_children(self, ku_uid: str) -> Result[list[dict[str, Any]]]:
        """
        Get direct children of a KU organized by ORGANIZES relationship.

        Args:
            ku_uid: Parent KU UID

        Returns:
            Result[list]: List of child KUs with order
        """
        return await self.navigation.get_organized_children(ku_uid)

    # =========================================================================
    # KU CRUD DELEGATION
    # =========================================================================

    async def create_ku(self, **kwargs: Any) -> Result[Any]:
        """
        Create a new KU (delegates to KuService).

        To make this KU a MOC, use organize() to add children.

        Args:
            **kwargs: KU creation parameters

        Returns:
            Result: Created KU
        """
        return await self.ku_service.create(**kwargs)

    async def get_ku(self, ku_uid: str) -> Result[Any]:
        """
        Get a KU by UID (delegates to KuService).

        Args:
            ku_uid: KU UID

        Returns:
            Result: KU or None
        """
        return await self.ku_service.get(ku_uid)

    async def delete_ku(self, ku_uid: str) -> Result[bool]:
        """
        Delete a KU (delegates to KuService).

        Warning: This will also remove all ORGANIZES relationships.

        Args:
            ku_uid: KU UID

        Returns:
            Result[bool]: True if deleted
        """
        return await self.ku_service.delete(ku_uid)
