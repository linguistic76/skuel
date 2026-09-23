"""
Organizes Mixin
===============

ORGANIZES relationship management for domain backends.

Provides hierarchy operations via ORGANIZES relationships: create, delete,
reorder, traverse, cycle detection, and root discovery. Used by PsBackend
for content organization and by UserEntryBackend for MOC reads (a user
entry with ORGANIZES edges is an emergent MOC — its children render on
/gradebook/{uid}).

Requires on concrete class:
    execute_query, logger  (provided by UniversalNeo4jBackend)

See: /docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.persistence.neo4j.query.cypher import build_publication_clause
from core.models.type_hints import EntityUID
from core.ports.base_protocols import HierarchyContextRaw
from core.ports.query_types import OrganizerResult, RootOrganizerResult
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    import builtins
    import logging
    from collections.abc import Sequence

    from core.models.type_hints import Neo4jProperties


class _OrganizesMixin:
    """ORGANIZES relationship management operations.

    Domain backends that manage ORGANIZES hierarchies should:
    1. Add ``_OrganizesMixin`` to their class bases.

    All methods return raw records — the service layer converts to typed models.

    Every statement matches ``:Entity`` — an organizer or a child can be any
    entity type, which is what makes MOC identity emergent. The three reads that
    return other nodes' uids and titles (``get_organized_children``,
    ``find_organizers``, ``list_root_organizers``) therefore take an optional
    ``entity_type`` scope: a caller serving shared content passes the curriculum
    types so a user-owned entity (a personal-vault ``moc: true`` map) is never
    returned through an unauthenticated read; an owner-verified caller
    (``UserEntryBackend`` behind ``/gradebook/{uid}``) passes none. The scope is
    the caller's policy; the mixin only applies it.

    Requires on concrete class:
        execute_query: async (query, params) -> Result[list[dict]]
        logger: logging.Logger
    """

    if TYPE_CHECKING:
        logger: logging.Logger

        async def execute_query(
            self, query: str, params: dict[str, Any] | None = None
        ) -> Result[builtins.list[dict[str, Any]]]: ...

    async def is_organizer(
        self, entity_uid: str, *, child_types: Sequence[str] | None = None
    ) -> Result[bool]:
        """Check if an entity has organized children. Returns error if not found.

        ``child_types`` — when given, only children whose ``entity_type`` is in it
        count, so the answer agrees with a ``get_organized_children`` call under the
        same scope (an edge to a hidden entity reads as no edge).
        """
        scope = "WHERE child.entity_type IN $child_types" if child_types is not None else ""
        query = f"""
        MATCH (n:Entity {{uid: $entity_uid}})
        OPTIONAL MATCH (n)-[:ORGANIZES]->(child:Entity)
        {scope}
        RETURN n IS NOT NULL AS entity_exists, count(child) > 0 AS is_organizer
        """
        params: dict[str, Any] = {"entity_uid": entity_uid}
        if child_types is not None:
            params["child_types"] = list(child_types)
        result = await self.execute_query(query, params)
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.fail(Errors.not_found(resource="Entity", identifier=entity_uid))
        record = result.value[0]
        if not record["entity_exists"]:
            return Result.fail(Errors.not_found(resource="Entity", identifier=entity_uid))
        return Result.ok(record["is_organizer"])

    async def organize(self, parent_uid: str, child_uid: str, order: int = 0) -> Result[bool]:
        """Create ORGANIZES relationship between two entities."""
        query = """
        MATCH (parent:Entity {uid: $parent_uid})
        MATCH (child:Entity {uid: $child_uid})
        MERGE (parent)-[r:ORGANIZES]->(child)
        SET r.order = $order
        RETURN true AS success
        """
        result = await self.execute_query(
            query,
            {"parent_uid": parent_uid, "child_uid": child_uid, "order": order},
        )
        if result.is_error:
            return Result.fail(result)
        success = bool(result.value and result.value[0]["success"])
        if success:
            self.logger.info(f"Organized {child_uid} under {parent_uid} at position {order}")
        return Result.ok(success)

    async def unorganize(self, parent_uid: str, child_uid: str) -> Result[bool]:
        """Remove ORGANIZES relationship between two entities."""
        query = """
        MATCH (parent:Entity {uid: $parent_uid})-[r:ORGANIZES]->(child:Entity {uid: $child_uid})
        DELETE r
        RETURN true AS success
        """
        result = await self.execute_query(
            query,
            {"parent_uid": parent_uid, "child_uid": child_uid},
        )
        if result.is_error:
            return Result.fail(result)
        success = bool(result.value and result.value[0]["success"])
        if success:
            self.logger.info(f"Removed organization of {child_uid} from {parent_uid}")
        return Result.ok(success)

    async def reorder(self, parent_uid: str, child_uid: str, new_order: int) -> Result[bool]:
        """Change the order of a child entity within its parent organizer."""
        query = """
        MATCH (parent:Entity {uid: $parent_uid})-[r:ORGANIZES]->(child:Entity {uid: $child_uid})
        SET r.order = $new_order
        RETURN true AS success
        """
        result = await self.execute_query(
            query,
            {"parent_uid": parent_uid, "child_uid": child_uid, "new_order": new_order},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(bool(result.value and result.value[0]["success"]))

    async def get_organized_children(
        self,
        parent_uid: str,
        limit: int | None = None,
        *,
        child_types: Sequence[str] | None = None,
    ) -> Result[list[OrganizerResult]]:
        """Get direct ORGANIZES children of an entity, ordered by position.

        ``child_types`` — when given, only children whose ``entity_type`` is in
        it are returned (the shared-content scope; see the class docstring).
        """
        scope = "WHERE child.entity_type IN $child_types" if child_types is not None else ""
        query = f"""
        MATCH (parent:Entity {{uid: $parent_uid}})-[r:ORGANIZES]->(child:Entity)
        {scope}
        RETURN child.uid AS uid, child.title AS title, r.order AS order,
               child.entity_type AS entity_type
        ORDER BY r.order ASC
        """
        params: dict[str, Any] = {"parent_uid": parent_uid}
        if child_types is not None:
            params["child_types"] = list(child_types)
        if limit is not None:
            query += "\nLIMIT $limit"
            params["limit"] = limit
        result = await self.execute_query(query, params)
        if result.is_error:
            return Result.fail(result)
        children: list[OrganizerResult] = [
            {
                "uid": r["uid"],
                "title": r["title"],
                "order": r["order"],
                "entity_type": r["entity_type"],
            }
            for r in (result.value or [])
        ]
        return Result.ok(children)

    async def find_organizers(
        self, entity_uid: str, *, organizer_types: Sequence[str] | None = None
    ) -> Result[list[OrganizerResult]]:
        """Find all parent entities that organize the given entity.

        ``organizer_types`` — when given, only parents whose ``entity_type`` is
        in it are returned (the shared-content scope; see the class docstring).
        """
        scope = (
            "WHERE parent.entity_type IN $organizer_types" if organizer_types is not None else ""
        )
        query = f"""
        MATCH (parent:Entity)-[r:ORGANIZES]->(n:Entity {{uid: $entity_uid}})
        {scope}
        RETURN parent.uid AS uid, parent.title AS title, r.order AS order,
               parent.entity_type AS entity_type
        ORDER BY parent.title
        """
        params: dict[str, Any] = {"entity_uid": entity_uid}
        if organizer_types is not None:
            params["organizer_types"] = list(organizer_types)
        result = await self.execute_query(query, params)
        if result.is_error:
            return Result.fail(result)
        organizers: list[OrganizerResult] = [
            {
                "uid": r["uid"],
                "title": r["title"],
                "order": r["order"],
                "entity_type": r["entity_type"],
            }
            for r in (result.value or [])
        ]
        return Result.ok(organizers)

    async def list_root_organizers(
        self, limit: int = 50, *, root_types: Sequence[str] | None = None
    ) -> Result[list[RootOrganizerResult]]:
        """List entities that organize others but are not themselves organized (root organizers).

        ``root_types`` — when given, the listing is computed as if only entities of
        those types existed: a root is one of them that organizes at least one of
        them and is organized by none of them, and ``child_count`` counts only
        them (the shared-content scope; see the class docstring — an edge to or
        from a hidden entity reads as no edge, so the listing agrees with
        ``get_organized_children`` and ``find_organizers`` under the same scope).
        An unanchored listing is the one read that can enumerate the whole graph,
        so the unauthenticated caller must scope it.
        """
        # Discovery: the MOC browse entry point — an unanchored listing of every
        # root organizer. Draft curriculum withheld; NULL-tolerant (#1006).
        published, published_params = build_publication_clause("root")
        if root_types is None:
            first_scope = organizer_scope = child_scope = ""
        else:
            first_scope = "AND root.entity_type IN $root_types AND first.entity_type IN $root_types"
            organizer_scope = "WHERE organizer.entity_type IN $root_types"
            child_scope = "WHERE child.entity_type IN $root_types"
        query = f"""
        MATCH (root:Entity)-[:ORGANIZES]->(first:Entity)
        WHERE NOT EXISTS {{ (organizer:Entity)-[:ORGANIZES]->(root) {organizer_scope} }}
          AND {published}
          {first_scope}
        WITH DISTINCT root
        OPTIONAL MATCH (root)-[:ORGANIZES]->(child:Entity)
        {child_scope}
        RETURN root.uid AS uid, root.title AS title, count(child) AS child_count
        ORDER BY root.title
        LIMIT $limit
        """
        params: dict[str, Any] = {"limit": limit, **published_params}
        if root_types is not None:
            params["root_types"] = list(root_types)
        result = await self.execute_query(query, params)
        if result.is_error:
            return Result.fail(result)
        roots: list[RootOrganizerResult] = [
            {"uid": r["uid"], "title": r["title"], "child_count": r["child_count"]}
            for r in (result.value or [])
        ]
        return Result.ok(roots)

    async def get_hierarchy_raw(self, entity_uid: EntityUID) -> Result[HierarchyContextRaw]:
        """Get full hierarchy context: ancestors, children, siblings."""
        ancestors_query = """
        MATCH path = (ancestor:Entity)-[:ORGANIZES*]->(ku:Entity {uid: $entity_uid})
        RETURN ancestor, length(path) as depth
        ORDER BY depth DESC
        """
        children_query = """
        MATCH (ku:Entity {uid: $entity_uid})-[:ORGANIZES]->(child:Entity)
        RETURN child
        ORDER BY child.title
        """
        siblings_query = """
        MATCH (parent:Entity)-[:ORGANIZES]->(sibling:Entity)
        WHERE (parent)-[:ORGANIZES]->(:Entity {uid: $entity_uid})
        AND sibling.uid <> $entity_uid
        RETURN DISTINCT sibling
        ORDER BY sibling.title
        """
        params = {"entity_uid": entity_uid}
        ancestors_result = await self.execute_query(ancestors_query, params)
        if ancestors_result.is_error:
            return Result.fail(ancestors_result)
        children_result = await self.execute_query(children_query, params)
        if children_result.is_error:
            return Result.fail(children_result)
        siblings_result = await self.execute_query(siblings_query, params)
        if siblings_result.is_error:
            return Result.fail(siblings_result)
        return Result.ok(
            {
                "ancestors": ancestors_result.value or [],
                "children": children_result.value or [],
                "siblings": siblings_result.value or [],
            }
        )

    async def check_organizes_cycle(
        self, parent_uid: str, child_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Check if creating ORGANIZES would create a cycle."""
        query = """
        MATCH path = (child:Entity {uid: $child_uid})-[:ORGANIZES*]->(parent:Entity {uid: $parent_uid})
        RETURN length(path) as cycle_length
        LIMIT 1
        """
        return await self.execute_query(query, {"parent_uid": parent_uid, "child_uid": child_uid})
