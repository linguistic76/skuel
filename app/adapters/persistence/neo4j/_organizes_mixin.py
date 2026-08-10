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

    from core.models.type_hints import Neo4jProperties


class _OrganizesMixin:
    """ORGANIZES relationship management operations.

    Domain backends that manage ORGANIZES hierarchies should:
    1. Add ``_OrganizesMixin`` to their class bases.

    All methods return raw records — the service layer converts to typed models.

    Requires on concrete class:
        execute_query: async (query, params) -> Result[list[dict]]
        logger: logging.Logger
    """

    if TYPE_CHECKING:
        logger: logging.Logger

        async def execute_query(
            self, query: str, params: dict[str, Any] | None = None
        ) -> Result[builtins.list[dict[str, Any]]]: ...

    async def is_organizer(self, entity_uid: str) -> Result[bool]:
        """Check if an entity has organized children. Returns error if not found."""
        query = """
        MATCH (n:Entity {uid: $entity_uid})
        OPTIONAL MATCH (n)-[:ORGANIZES]->(child:Entity)
        RETURN n IS NOT NULL AS entity_exists, count(child) > 0 AS is_organizer
        """
        result = await self.execute_query(query, {"entity_uid": entity_uid})
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
        self, parent_uid: str, limit: int | None = None
    ) -> Result[list[OrganizerResult]]:
        """Get direct ORGANIZES children of an entity, ordered by position."""
        query = """
        MATCH (parent:Entity {uid: $parent_uid})-[r:ORGANIZES]->(child:Entity)
        RETURN child.uid AS uid, child.title AS title, r.order AS order,
               child.entity_type AS entity_type
        ORDER BY r.order ASC
        """
        params: dict[str, Any] = {"parent_uid": parent_uid}
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

    async def find_organizers(self, entity_uid: str) -> Result[list[OrganizerResult]]:
        """Find all parent entities that organize the given entity."""
        query = """
        MATCH (parent:Entity)-[r:ORGANIZES]->(n:Entity {uid: $entity_uid})
        RETURN parent.uid AS uid, parent.title AS title, r.order AS order,
               parent.entity_type AS entity_type
        ORDER BY parent.title
        """
        result = await self.execute_query(query, {"entity_uid": entity_uid})
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

    async def list_root_organizers(self, limit: int = 50) -> Result[list[RootOrganizerResult]]:
        """List entities that organize others but are not themselves organized (root organizers)."""
        # Discovery: the MOC browse entry point — an unanchored listing of every
        # root organizer, which on this graph is largely Kus and PathSteps.
        # Draft curriculum withheld; NULL-tolerant (#1006).
        published, published_params = build_publication_clause("root")
        query = f"""
        MATCH (root:Entity)-[:ORGANIZES]->(:Entity)
        WHERE NOT EXISTS((:Entity)-[:ORGANIZES]->(root))
          AND {published}
        WITH DISTINCT root
        OPTIONAL MATCH (root)-[:ORGANIZES]->(child:Entity)
        RETURN root.uid AS uid, root.title AS title, count(child) AS child_count
        ORDER BY root.title
        LIMIT $limit
        """
        result = await self.execute_query(query, {"limit": limit, **published_params})
        if result.is_error:
            return Result.fail(result)
        roots: list[RootOrganizerResult] = [
            {"uid": r["uid"], "title": r["title"], "child_count": r["child_count"]}
            for r in (result.value or [])
        ]
        return Result.ok(roots)

    async def get_organized_children_deep(
        self, parent_uid: str, depth: int
    ) -> Result[list[Neo4jProperties]]:
        """Get children organized under parent at specified depth."""
        query = f"""
        MATCH (parent:Entity {{uid: $parent_uid}})-[r:ORGANIZES*1..{depth}]->(child:Entity)
        RETURN child, r
        ORDER BY r[0].order ASC
        """
        return await self.execute_query(query, {"parent_uid": parent_uid})

    async def get_parent_organizers_raw(
        self, entity_uid: EntityUID
    ) -> Result[list[Neo4jProperties]]:
        """Find all parents that organize a given entity."""
        query = """
        MATCH (parent:Entity)-[:ORGANIZES]->(child:Entity {uid: $entity_uid})
        RETURN parent
        ORDER BY parent.title
        """
        return await self.execute_query(query, {"entity_uid": entity_uid})

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

    async def create_organizes(
        self, parent_uid: str, child_uid: str, order: int, importance: str
    ) -> Result[list[Neo4jProperties]]:
        """Create ORGANIZES relationship with order and importance."""
        query = """
        MATCH (parent:Entity {uid: $parent_uid})
        MATCH (child:Entity {uid: $child_uid})
        MERGE (parent)-[r:ORGANIZES]->(child)
        SET r.order = $order,
            r.importance = $importance,
            r.created_at = COALESCE(r.created_at, datetime()),
            r.updated_at = datetime()
        RETURN r
        """
        return await self.execute_query(
            query,
            {
                "parent_uid": parent_uid,
                "child_uid": child_uid,
                "order": order,
                "importance": importance,
            },
        )

    async def delete_organizes(
        self, parent_uid: str, child_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Remove ORGANIZES relationship."""
        query = """
        MATCH (parent:Entity {uid: $parent_uid})-[r:ORGANIZES]->(child:Entity {uid: $child_uid})
        DELETE r
        RETURN count(r) as deleted
        """
        return await self.execute_query(query, {"parent_uid": parent_uid, "child_uid": child_uid})
