"""
Hierarchy Mixin
===============

Generic sub-entity hierarchy operations for domain backends.

Provides parent-child hierarchy management (get children, get parent, get full
hierarchy, create/remove bidirectional relationships, cycle detection) that all
6 Activity Domain backends share.

Each domain backend sets a ``_hierarchy_config`` class attribute to parameterize
the relationship names and node labels. The mixin reads that config to build
Cypher queries.

Requires on concrete class:
    execute_query, logger  (provided by UniversalNeo4jBackend)

See: /docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    import builtins
    import logging


@dataclass(frozen=True)
class HierarchyConfig:
    """Configuration for a domain's parent-child hierarchy.

    Attributes:
        forward_rel: Forward relationship name, e.g. ``"HAS_SUBTASK"``.
        inverse_rel: Inverse relationship name, e.g. ``"SUBTASK_OF"``.
        node_label: Neo4j node label for MATCH clauses, e.g. ``"Entity"``.
        domain_name: Human-readable child name for error messages, e.g. ``"subtask"``.
        node_filter: Extra property filter appended inside MATCH ``{{}}``,
            e.g. ``", entity_type: 'choice'"`` for Choices multi-label pattern.
            Defaults to ``""`` (no extra filter).
    """

    forward_rel: str
    inverse_rel: str
    node_label: str
    domain_name: str
    node_filter: str = ""


class _HierarchyMixin:
    """Generic sub-entity hierarchy operations.

    Domain backends that support parent-child hierarchies should:
    1. Add ``_HierarchyMixin`` to their class bases.
    2. Set ``_hierarchy_config`` as a class attribute.

    All methods return raw ``dict`` records — the service layer converts to
    typed domain models.

    Requires on concrete class:
        execute_query: async (query, params) -> Result[list[dict]]
        logger: logging.Logger
    """

    if TYPE_CHECKING:
        logger: logging.Logger
        _hierarchy_config: HierarchyConfig

        async def execute_query(
            self, query: str, params: dict[str, Any] | None = None
        ) -> Result[builtins.list[dict[str, Any]]]: ...

    # ========================================================================
    # READ OPERATIONS
    # ========================================================================

    async def get_children_raw(
        self, parent_uid: str, depth: int = 1
    ) -> Result[list[dict[str, Any]]]:
        """Get child nodes as raw dicts at the given traversal depth.

        Args:
            parent_uid: Parent entity UID.
            depth: Traversal depth (1 = direct children, 2 = + grandchildren, etc.).

        Returns:
            Result containing list of raw node property dicts, ordered by created_at.
        """
        cfg = self._hierarchy_config
        query = f"""
        MATCH (parent:{cfg.node_label} {{uid: $parent_uid{cfg.node_filter}}})
        MATCH (parent)-[:{cfg.forward_rel}*1..{depth}]->(child:{cfg.node_label})
        RETURN child
        ORDER BY child.created_at
        """
        result = await self.execute_query(query, {"parent_uid": parent_uid})
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["child"] for record in (result.value or [])])

    async def get_parent_raw(self, child_uid: str) -> Result[dict[str, Any] | None]:
        """Get immediate parent node as a raw dict, or None if root-level.

        Args:
            child_uid: Child entity UID.

        Returns:
            Result containing parent node dict, or None if no parent.
        """
        cfg = self._hierarchy_config
        query = f"""
        MATCH (child:{cfg.node_label} {{uid: $child_uid{cfg.node_filter}}})
        MATCH (parent:{cfg.node_label})-[:{cfg.forward_rel}]->(child)
        RETURN parent
        LIMIT 1
        """
        result = await self.execute_query(query, {"child_uid": child_uid})
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.ok(None)
        return Result.ok(result.value[0]["parent"])

    async def get_hierarchy_raw(self, entity_uid: str) -> Result[dict[str, Any]]:
        """Get full hierarchy context: ancestors, siblings, children as raw dicts.

        Args:
            entity_uid: Entity UID to get hierarchy context for.

        Returns:
            Result containing dict with keys:
            - ``ancestors``: list[dict] (root to immediate parent, excludes current)
            - ``siblings``: list[dict] (other children of same parent)
            - ``children``: list[dict] (immediate children)
        """
        cfg = self._hierarchy_config
        uid_param = "entity_uid"
        params: dict[str, Any] = {uid_param: entity_uid}

        ancestors_query = f"""
        MATCH path = (root:{cfg.node_label})-[:{cfg.forward_rel}*]->(current:{cfg.node_label} {{uid: $entity_uid{cfg.node_filter}}})
        WHERE NOT EXISTS((root)<-[:{cfg.forward_rel}]-())
        RETURN nodes(path) as ancestors
        """

        siblings_query = f"""
        MATCH (current:{cfg.node_label} {{uid: $entity_uid{cfg.node_filter}}})
        OPTIONAL MATCH (parent:{cfg.node_label})-[:{cfg.forward_rel}]->(current)
        OPTIONAL MATCH (parent)-[:{cfg.forward_rel}]->(sibling:{cfg.node_label})
        WHERE sibling.uid <> $entity_uid
        RETURN collect(sibling) as siblings
        """

        children_query = f"""
        MATCH (current:{cfg.node_label} {{uid: $entity_uid{cfg.node_filter}}})
        OPTIONAL MATCH (current)-[:{cfg.forward_rel}]->(child:{cfg.node_label})
        RETURN collect(child) as children
        """

        ancestors_result = await self.execute_query(ancestors_query, params)
        siblings_result = await self.execute_query(siblings_query, params)
        children_result = await self.execute_query(children_query, params)

        # Process ancestors (exclude current node = last in path)
        ancestors: list[dict[str, Any]] = []
        if (
            not ancestors_result.is_error
            and ancestors_result.value
            and ancestors_result.value[0]["ancestors"]
        ):
            ancestors.extend(ancestors_result.value[0]["ancestors"][:-1])

        # Process siblings
        siblings: list[dict[str, Any]] = []
        if (
            not siblings_result.is_error
            and siblings_result.value
            and siblings_result.value[0]["siblings"]
        ):
            siblings.extend(
                node for node in siblings_result.value[0]["siblings"] if node
            )

        # Process children
        children: list[dict[str, Any]] = []
        if (
            not children_result.is_error
            and children_result.value
            and children_result.value[0]["children"]
        ):
            children.extend(
                node for node in children_result.value[0]["children"] if node
            )

        return Result.ok(
            {
                "ancestors": ancestors,
                "siblings": siblings,
                "children": children,
            }
        )

    # ========================================================================
    # WRITE OPERATIONS
    # ========================================================================

    async def create_hierarchy_relationship(
        self,
        parent_uid: str,
        child_uid: str,
        forward_props: dict[str, Any] | None = None,
    ) -> Result[bool]:
        """Create bidirectional parent-child relationship with cycle detection.

        Creates both forward (parent→child) and inverse (child→parent)
        relationships atomically. Rejects if the relationship would create a cycle.

        Args:
            parent_uid: Parent entity UID.
            child_uid: Child entity UID.
            forward_props: Properties for the forward relationship
                (e.g. ``{"progress_weight": 1.0}``). ``created_at`` is always added.

        Returns:
            Result[bool] — True on success, validation error on cycle.
        """
        # Check for cycles first
        cycle_result = await self.would_create_cycle(parent_uid, child_uid)
        if cycle_result.is_error:
            return Result.fail(cycle_result)
        if cycle_result.value:
            cfg = self._hierarchy_config
            return Result.fail(
                Errors.validation(
                    f"Cannot create {cfg.domain_name} relationship: would create cycle "
                    f"({child_uid} is ancestor of {parent_uid})"
                )
            )

        cfg = self._hierarchy_config

        # Build forward relationship property assignments
        prop_assignments = "created_at: datetime()"
        if forward_props:
            extra = ", ".join(f"{k}: ${k}" for k in forward_props)
            prop_assignments = f"{extra}, {prop_assignments}"

        query = f"""
        MATCH (parent:{cfg.node_label} {{uid: $parent_uid{cfg.node_filter}}})
        MATCH (child:{cfg.node_label} {{uid: $child_uid{cfg.node_filter}}})

        CREATE (parent)-[:{cfg.forward_rel} {{
            {prop_assignments}
        }}]->(child)

        CREATE (child)-[:{cfg.inverse_rel} {{
            created_at: datetime()
        }}]->(parent)

        RETURN true as success
        """

        params: dict[str, Any] = {"parent_uid": parent_uid, "child_uid": child_uid}
        if forward_props:
            params.update(forward_props)

        result = await self.execute_query(query, params)

        if result.is_error:
            return Result.fail(
                Errors.database(
                    operation="create",
                    message=f"Failed to create {cfg.domain_name} relationship",
                )
            )
        if result.value:
            self.logger.info(f"Created {cfg.domain_name} relationship: {parent_uid} -> {child_uid}")
            return Result.ok(True)

        return Result.fail(
            Errors.database(
                operation="create",
                message=f"Failed to create {cfg.domain_name} relationship",
            )
        )

    async def remove_hierarchy_relationship(self, parent_uid: str, child_uid: str) -> Result[bool]:
        """Remove bidirectional parent-child relationship.

        Deletes both the forward and inverse relationship edges.

        Args:
            parent_uid: Parent entity UID.
            child_uid: Child entity UID.

        Returns:
            Result[bool] — True if relationships were deleted.
        """
        cfg = self._hierarchy_config
        query = f"""
        MATCH (parent:{cfg.node_label} {{uid: $parent_uid{cfg.node_filter}}})-[r1:{cfg.forward_rel}]->(child:{cfg.node_label} {{uid: $child_uid{cfg.node_filter}}})
        MATCH (child)-[r2:{cfg.inverse_rel}]->(parent)
        DELETE r1, r2
        RETURN count(r1) + count(r2) as deleted_count
        """

        result = await self.execute_query(query, {"parent_uid": parent_uid, "child_uid": child_uid})

        if result.is_error:
            return Result.fail(
                Errors.database(
                    operation="delete",
                    message=f"Failed to remove {cfg.domain_name} relationship",
                )
            )

        deleted = result.value[0]["deleted_count"] > 0 if result.value else False
        if deleted:
            self.logger.info(f"Removed {cfg.domain_name} relationship: {parent_uid} -> {child_uid}")
        return Result.ok(deleted)

    async def would_create_cycle(self, parent_uid: str, child_uid: str) -> Result[bool]:
        """Check if adding parent→child would create a cycle.

        Args:
            parent_uid: Proposed parent UID.
            child_uid: Proposed child UID.

        Returns:
            Result[bool] — True if a cycle would be created.
        """
        cfg = self._hierarchy_config
        query = f"""
        MATCH (child:{cfg.node_label} {{uid: $child_uid{cfg.node_filter}}})
        MATCH path = (child)-[:{cfg.forward_rel}*]->(parent:{cfg.node_label} {{uid: $parent_uid{cfg.node_filter}}})
        RETURN count(path) > 0 as would_create_cycle
        """

        result = await self.execute_query(query, {"parent_uid": parent_uid, "child_uid": child_uid})

        if result.is_error:
            # On error, assume no cycle (fail-open for reads)
            return Result.ok(False)
        if result.value:
            return Result.ok(result.value[0]["would_create_cycle"])
        return Result.ok(False)
