"""
CRUD Mixin
==========

CrudOperations[T] protocol implementation.

Provides:
    create: Create entity with auto-user OWNS relationship
    get: Get entity by UID
    get_visible_to_user: Get entity by UID only if the user is in its audience
    get_or_fail: Get entity by UID, not-found as error Result
    get_many: Batch entity retrieval (N+1 prevention)
    update: Partial update with updated_at timestamp
    update_with_status_guard: Partial update whose conditions are evaluated at write
        time against the node's prior status, under its write-lock (ADR-087)
    delete: Delete with optional cascade (DETACH DELETE)
    list: List entities with filters, pagination, sorting

Requires on concrete class:
    driver, logger, entity_class, label, default_filters, _create_labels,
    query_builder, prometheus_metrics, _track_db_metrics, _default_filter_clause,
    _default_filter_params, _inject_default_filters, _is_driver_closed
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from adapters.persistence.neo4j.neo4j_mapper import from_neo4j_node, to_neo4j_node
from core.models.protocols import DomainModelProtocol
from core.models.relationship_names import RelationshipName
from core.models.type_hints import FilterParams, Neo4jProperties, UserUID
from core.models.update_contracts import StatusGuardedOutcome, StatusWriteGuard
from core.utils.error_boundary import safe_backend_operation
from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    import builtins
    import logging

    from neo4j import AsyncDriver, Record

    from adapters.persistence.neo4j.query import UnifiedQueryBuilder
    from core.infrastructure.monitoring.prometheus_metrics import PrometheusMetrics
    from core.models.enums import SearchVisibility
    from core.models.enums.neo_labels import NeoLabel


class _CrudMixin[T: DomainModelProtocol]:
    """
    CrudOperations[T] — create, get, get_visible_to_user, get_many, update,
    update_with_status_guard, delete, list.

    Requires on concrete class:
        driver: AsyncDriver
        logger: logging.Logger
        entity_class: type[T]
        label: NeoLabel
        default_filters: FilterParams
        _create_labels: str
        query_builder: UnifiedQueryBuilder
        prometheus_metrics: PrometheusMetrics | None
        _track_db_metrics: method
        _default_filter_clause: method
        _default_filter_params: method
        _inject_default_filters: method
        _is_driver_closed: method
    """

    if TYPE_CHECKING:
        driver: AsyncDriver

        # Session-run chokepoint (Neo4jSessionRunner)
        async def _run_single(
            self, query: str, params: dict[str, Any] | None = None
        ) -> Record | None: ...

        async def _run_records(
            self, query: str, params: dict[str, Any] | None = None
        ) -> list[dict[str, Any]]: ...

        logger: logging.Logger
        entity_class: type[T]
        label: NeoLabel
        default_filters: FilterParams
        _create_labels: str
        query_builder: UnifiedQueryBuilder
        prometheus_metrics: PrometheusMetrics | None

        def _track_db_metrics(
            self, operation: str, duration: float, is_error: bool = False
        ) -> None: ...

        def _default_filter_clause(self, node_var: str = "n") -> str: ...

        def _default_filter_params(self) -> FilterParams: ...

        def _inject_default_filters(
            self,
            where_clauses: builtins.list[str],
            params: dict[str, Any],
            node_var: str = "n",
        ) -> None: ...

        def _is_driver_closed(self) -> bool: ...

        async def count(self, **filters: Any) -> Result[int]: ...

    # ============================================================================
    # UNIVERSAL CRUD - WORKS FOR ANY ENTITY TYPE
    # ============================================================================

    async def _create_node(
        self,
        entity: T,
        operation: str,
        match_clause: str = "",
        extra_cypher: str = "",
        params: dict[str, Any] | None = None,
        failure_message: str | None = None,
    ) -> Result[T]:
        """
        Shared body of create() and create_with_spawned_from().

        Serializes the entity, CREATEs the multi-label node, optionally wraps
        it with a caller-supplied MATCH prefix / extra Cypher (e.g. the
        SPAWNED_FROM edge), and — when the entity carries a ``user_uid`` —
        writes the ``(User)-[:OWNS]->(entity)`` edge in the SAME statement, so
        node and owner edge commit together or not at all. Metrics are tracked
        under ``operation``; exceptions propagate to the callers'
        @safe_backend_operation decorators.

        The owner is ``MATCH``ed, so a ``user_uid`` naming a user that does not
        exist fails the create rather than persisting a node no owner-scoped
        read can reach. This is what holds the ``user_uid property == :OWNS
        owner`` invariant on the CRUD door; the ingestion door holds the same
        invariant in ``build_node_upsert_template``. The halves must not be
        separable: a property-only node stays visible to property-scoped reads
        (text search, ``find_by(user_uid=…)``) while vanishing from every
        :OWNS-traversing read (faceted search, ``get_user_entities``, the GDPR
        cascade) — which is how a 2026-07 ingest batch left an owner's own
        Principles absent from ``/search``.
        """
        start_time = time.time()
        node_data = to_neo4j_node(entity)

        # Ensure default_filter properties are set on new nodes (e.g., entity_type)
        node_data.update(self.default_filters)

        # Owner edge — composed into THIS statement rather than a follow-up
        # query. Edge properties (created_at/last_accessed/access_count/is_active)
        # are the shared :OWNS edge shape every write door stores (ADR-086).
        user_uid = node_data.get("user_uid")
        owner_match = ""
        owns_clause = ""
        owns_params: Neo4jProperties = {}
        if user_uid:
            owner_match = "MATCH (owner:User {uid: $owns_owner_uid})"
            owns_clause = f"""
        MERGE (owner)-[owns:{RelationshipName.OWNS.value}]->(n)
        ON CREATE SET
            owns.created_at = $owns_timestamp,
            owns.last_accessed = $owns_timestamp,
            owns.access_count = 0,
            owns.is_active = true"""
            owns_params = {
                "owns_owner_uid": user_uid,
                "owns_timestamp": datetime.now().isoformat(),
            }

        query = f"""
        {match_clause}
        {owner_match}
        CREATE (n:{self._create_labels})
        SET n = $props
        {extra_cypher}
        {owns_clause}
        RETURN n
        """

        record = await self._run_single(
            query, {"props": node_data, **owns_params, **(params or {})}
        )

        if not record:
            # Track error metrics
            self._track_db_metrics(operation, time.time() - start_time, is_error=True)
            default_message = f"Failed to create {self.label}"
            if user_uid:
                default_message += f" (owner {user_uid} must be an existing User)"
            return Result.fail(Errors.database(operation, failure_message or default_message))

        created = from_neo4j_node(dict(record["n"]), self.entity_class)

        # Track metrics
        self._track_db_metrics(operation, time.time() - start_time, is_error=False)

        return Result.ok(created)

    @safe_backend_operation("create")
    async def create(self, entity: T) -> Result[T]:
        """
        Create any entity type.

        AUTO-CREATES USER RELATIONSHIP: If entity has a user_uid field, the
        (User)-[:OWNS]->(Entity) edge is written in the same statement as the
        node — both or neither. A user_uid naming a non-existent User fails
        the create; see ``_create_node`` for why the halves are inseparable.

        Multi-label CREATE: When base_label is set, creates nodes with
        dual labels: ``(n:Entity:Task)``.
        """
        return await self._create_node(entity, "create")

    @safe_backend_operation("create_with_spawned_from")
    async def create_with_spawned_from(self, entity: T, template_uid: str) -> Result[T]:
        """Create entity node + atomic ``(entity)-[:SPAWNED_FROM]->(template)`` edge.

        Used by the PsEngagement spawn orchestrator to write the graph-native
        back-reference from a spawned activity to the template that produced it
        — node and edge succeed or fail together in one Cypher transaction.
        There is no parallel ``template_uid`` property on the node; the edge
        is THE relationship.

        Like ``create()``, writes ``(User)-[:OWNS]->(entity)`` in the same
        statement when the entity carries a ``user_uid`` — so node, template
        edge and owner edge all commit together or not at all.
        """
        return await self._create_node(
            entity,
            "create_with_spawned_from",
            match_clause="MATCH (t {uid: $template_uid})",
            extra_cypher="CREATE (n)-[r:SPAWNED_FROM]->(t)\n        SET r.spawned_at = datetime()",
            params={"template_uid": template_uid},
            failure_message=f"Failed to create {self.label} or locate template {template_uid}",
        )

    @safe_backend_operation("get")
    async def get(self, uid: str) -> Result[T | None]:
        """
        Get any entity by UID.

        Retrieves a single entity from the Neo4j database by its unique identifier.
        Returns None if the entity does not exist.

        Args:
            uid: Unique identifier of the entity (e.g., "task:123", "event:456")

        Returns:
            Result[T | None]: Success with entity if found, Success with None if not found,
                             or Failure if database error occurs

        Example:
            ```python
            backend = UniversalNeo4jBackend[Task](driver, "Task", Task)
            result = await backend.get("task:123")

            if result.is_ok:
                task = result.value
                if task:
                    print(f"Found task: {task.title}")
                else:
                    print("Task not found")
            else:
                print(f"Error: {result.error}")
            ```

        Note:
            - This method does NOT raise exceptions - all errors are wrapped in Result
            - Not found is NOT an error - returns Result.ok(None)
            - For batch retrieval, use get_many() to avoid N+1 queries
        """
        return await self._get_by_uid(uid)

    async def _get_by_uid(
        self,
        uid: str,
        extra_where: str = "",
        extra_params: Neo4jProperties | None = None,
    ) -> Result[T | None]:
        """
        THE single MATCH-by-UID read body, behind get() and get_visible_to_user().

        ``extra_where`` is ANDed onto the default-filter conditions, so an
        audience predicate rides as a parameter on this one walk rather than
        as a second, drift-prone copy of it.
        """
        conditions = [c for c in (self._default_filter_clause(), extra_where) if c]
        where_line = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        query = f"""
        MATCH (n:{self.label} {{uid: $uid}})
        {where_line}
        RETURN n
        """

        params: dict[str, Any] = {"uid": uid}
        params.update(self._default_filter_params())
        if extra_params:
            params.update(extra_params)

        record = await self._run_single(query, params)

        if not record:
            return Result.ok(None)

        entity = from_neo4j_node(dict(record["n"]), self.entity_class)
        return Result.ok(entity)

    @safe_backend_operation("get_visible_to_user")
    async def get_visible_to_user(
        self,
        uid: str,
        user_uid: UserUID,
        visibility: SearchVisibility | None,
        ownership_property: str = "user_uid",
    ) -> Result[T | None]:
        """
        Get an entity by UID only if this user is in its audience.

        The single-entity twin of search's ownership scoping: both compose the
        audience predicate from ``build_search_visibility_clause()``, so a
        direct read and a search of the same domain agree by construction
        instead of by two hand-maintained policies.

        Not-found and not-visible are deliberately the SAME outcome
        (``Result.ok(None)``) — a caller cannot distinguish "no such UID" from
        "not yours", which is what keeps the 404-equivalent refusal in
        OWNERSHIP_VERIFICATION.md honest.

        Note the declaration decides the scoping: a domain declaring
        ``PUBLIC`` yields no predicate and this read is deliberately as open
        as ``get()``. Pass the domain's own ``search_visibility``, never a
        literal chosen at the call site.

        The publication gate is deliberately NOT applied here
        (``apply_publication_gate=False``): it belongs to DISCOVERY — search
        and listings — so draft curriculum is *unlisted*, not forbidden. A
        by-UID read is how an author opens their own draft to check it, and
        curriculum is ownerless (SHARED), so this read cannot tell an author
        from a learner to gate one and not the other. Gating here would also
        split the two by-UID paths: plain ``get()`` returns a draft, and this
        would not.

        Args:
            uid: Entity UID to read.
            user_uid: The requesting user, referenced by the predicate.
            visibility: The domain's SearchVisibility declaration.
            ownership_property: The domain's declared ownership property
                (DomainConfig.ownership_property) for the OWNER_ONLY clause.

        Returns:
            Result[T | None]: the entity when visible, None when absent or
            out of audience.
        """
        from adapters.persistence.neo4j.query.cypher import build_search_visibility_clause

        visibility_scope = build_search_visibility_clause(
            visibility,
            entity_alias="n",
            has_user=True,
            apply_publication_gate=False,
            ownership_property=ownership_property,
        )
        extra_where, scope_params = visibility_scope or ("", {})
        params: Neo4jProperties = {"user_uid": user_uid, **scope_params}
        return await self._get_by_uid(uid, extra_where=extra_where, extra_params=params)

    async def get_or_fail(self, uid: str) -> Result[T]:
        """
        Get an entity by UID, converting "not found" into an error Result.

        THE generic body behind the domain backends' get_task/get_goal/...
        wrappers (contrast with get(), where not-found is Result.ok(None)).
        The not-found resource name is the domain model class name.
        """
        get_result = await self.get(uid)
        if get_result.is_error:
            return Result.fail(get_result)
        if not get_result.value:
            return Result.fail(
                Errors.not_found(resource=self.entity_class.__name__, identifier=uid)
            )
        return Result.ok(get_result.value)

    @safe_backend_operation("get_many")
    async def get_many(self, uids: builtins.list[str]) -> Result[builtins.list[T | None]]:
        """
        Get multiple entities by UIDs in a single batched query.

        This method prevents N+1 query problems by fetching all requested
        entities in ONE database roundtrip using Neo4j's WHERE IN clause.

        Args:
            uids: List of entity UIDs to fetch

        Returns:
            Result[List[T]] with entities in the SAME ORDER as input UIDs.
            Missing entities are represented as None in the list to maintain
            position correspondence with the input UIDs (DataLoader requirement).

        Example:
            # Fetch 10 knowledge units in one query instead of 10 separate queries
            result = await backend.get_many([
                "ku.python.basics",
                "ku.python.functions",
                "ku.python.classes"
            ])
            # Returns list with 3 KnowledgeUnit objects in same order

        Performance:
            - 10 entities: 10 queries → 1 query (~10x faster)
            - 100 entities: 100 queries → 1 query (~100x faster)
        """
        if not uids:
            return Result.ok([])

        # Guard: Skip operation if driver is closed (test teardown)
        if self._is_driver_closed():
            return Result.ok([])

        df_clause = self._default_filter_clause()
        extra_where = f" AND {df_clause}" if df_clause else ""

        query = f"""
        MATCH (n:{self.label})
        WHERE n.uid IN $uids{extra_where}
        RETURN n
        """

        params: dict[str, Any] = {"uids": uids}
        params.update(self._default_filter_params())

        records = await self._run_records(query, params)

        # Create uid-to-entity map for fast lookup
        entity_map = {}
        for record in records:
            entity = from_neo4j_node(record["n"], self.entity_class)
            entity_map[entity.uid] = entity

        # Return entities in same order as input UIDs (DataLoader requirement)
        # Missing entities are None to maintain correspondence
        entities = [entity_map.get(uid) for uid in uids]

        self.logger.debug(
            f"Batched get_many: fetched {len(records)} of {len(uids)} {self.label} entities"
        )
        return Result.ok(entities)

    @safe_backend_operation("get_content")
    async def get_content(self, uid: str) -> Result[str | None]:
        """
        Get an entity's body content from its :Content node.

        Body content for chunked entity types (PathStep, Ku) lives on a
        separate ``(:Entity)-[:HAS_CONTENT]->(:Content)`` node, never as an
        entity property — ingestion pops the body pre-upsert (ADR-074). This
        is the read counterpart consumed by the
        ``ContextOperationsMixin.get_with_content`` inline-first fallback.

        Args:
            uid: Unique identifier of the entity

        Returns:
            Result[str | None]: the :Content node's body, or None when the
            entity has no content subtree (not an error).
        """
        query = f"""
        MATCH (n:{self.label} {{uid: $uid}})-[:HAS_CONTENT]->(c:Content)
        RETURN c.body AS body
        """

        record = await self._run_single(query, {"uid": uid})

        if not record:
            return Result.ok(None)
        return Result.ok(record["body"])

    @safe_backend_operation("update")
    async def update(self, uid: str, updates: dict[str, Any]) -> Result[T]:
        """
        Update any entity by UID.

        Performs a partial update of an entity, modifying only the fields specified
        in the updates dictionary. Automatically sets updated_at timestamp.

        Args:
            uid: Unique identifier of the entity to update
            updates: Dictionary of field names to new values (partial update)

        Returns:
            Result[T]: Success with updated entity, or Failure if entity not found
                      or database error occurs

        Example:
            ```python
            backend = UniversalNeo4jBackend[Task](driver, "Task", Task)

            # Update specific fields
            result = await backend.update(
                "task:123",
                {
                    "status": "completed",
                    "priority": "high",
                    "completion_notes": "Finished ahead of schedule",
                },
            )

            if result.is_ok:
                task = result.value
                print(f"Updated task: {task.title}")
            ```

        Note:
            - Uses Neo4j's += operator for partial updates (preserves other fields)
            - Automatically adds updated_at timestamp
            - Returns error if entity doesn't exist (use get() first to check)
            - Empty updates dictionary returns validation error
        """
        start_time = time.time()

        if not updates:
            self._track_db_metrics("update", time.time() - start_time, is_error=True)
            return Result.fail(Errors.validation("No updates provided", field="updates"))

        # Add updated_at timestamp
        updates["updated_at"] = datetime.now().isoformat()

        # Prevent overwriting default_filter properties (e.g., entity_type)
        for k in self.default_filters:
            updates.pop(k, None)

        # Serialize complex types for Neo4j (dicts → JSON strings, enums → values, etc.)
        # This matches what to_neo4j_node() does for create(), closing the SoC gap
        # where services previously had to manually json.dumps() before calling update().
        updates = to_neo4j_node(updates)

        df_clause = self._default_filter_clause()
        where_line = f"WHERE {df_clause}" if df_clause else ""

        query = f"""
        MATCH (n:{self.label} {{uid: $uid}})
        {where_line}
        SET n += $updates
        RETURN n
        """

        params: dict[str, Any] = {"uid": uid, "updates": updates}
        params.update(self._default_filter_params())

        record = await self._run_single(query, params)

        if not record:
            self._track_db_metrics("update", time.time() - start_time, is_error=True)
            return Result.fail(Errors.not_found("resource", f"{self.label} {uid} not found"))

        updated = from_neo4j_node(dict(record["n"]), self.entity_class)

        # Track metrics
        self._track_db_metrics("update", time.time() - start_time, is_error=False)

        return Result.ok(updated)

    @safe_backend_operation("update_with_status_guard")
    async def update_with_status_guard(
        self,
        uid: str,
        # boundary: pre-serialization patch — genuinely heterogeneous, and NOT
        # Neo4jProperties. Callers hand this `intent.to_changes()`, which can carry a
        # `list[dict]` (GoalUpdateIntent.milestones), a bare `dict`
        # (GoalUpdateIntent.metadata), or an enum — none of them Neo4jValue members.
        # `to_neo4j_node` below is what turns them into storable properties; declaring
        # the parameter Neo4jProperties would claim a contract the callers do not meet
        # and this method does not require. Same shape as `update` above, deliberately.
        updates: dict[str, Any],
        guard: StatusWriteGuard,
    ) -> Result[StatusGuardedOutcome[T]]:
        """Update an entity with its guard evaluated at write time, under the node's lock.

        The write-side peer of :meth:`update`, and the ONE way a status-bearing write is
        done (ADR-087). ``update`` writes a patch a caller already decided on; this
        captures the node's status *inside* the write statement — after taking the node's
        write-lock — chooses ``guard``'s conditional patches from that prior, and returns
        the prior so the caller can derive its transition verdicts exactly. The lock is
        what makes them exact: a prior captured under it cannot be changed by another
        writer before this statement's SET (ADR-087 § Mechanics measures it).

        Contract:
            - **Not found** (no row matched, same default-filter semantics as ``update``)
              → ``Result.fail(not_found)``. Guard evaluation happens after the MATCH, so
              a returned row proves existence and no row proves absence — one query leg
              distinguishes them.
            - **Guarded out** (prior in ``guard.refuse_if_prior_in``) → ``Result.ok`` with
              ``applied=False`` and the node byte-identical, ``updated_at`` included.
              Callers branch on it; it is an outcome, never an error.
            - ``updated_at`` is stamped Python-side into ``updates`` (as ``update`` does),
              so it rides the same conditional merge and only lands when the write applies.
            - All three payloads pass through ``to_neo4j_node``, so storage shapes match
              every other write (dates/datetimes → ISO strings) and a ``None`` survives to
              ``SET n += {field: null}``, which REMOVES the property — the reopen clear.

        Args:
            uid: UID of the entity to update.
            updates: The unconditional partial patch (may be empty iff ``guard`` carries
                a conditional patch).
            guard: The prior-status conditions. A default ``StatusWriteGuard()`` makes
                this exactly ``update`` plus a returned prior.

        Returns:
            ``Result[StatusGuardedOutcome[T]]`` — ``applied``, ``prior_status`` (read
            under the lock; ``None`` when the property is absent), and ``entity``.
        """
        start_time = time.time()

        if not updates and not guard.has_patches():
            self._track_db_metrics(
                "update_with_status_guard", time.time() - start_time, is_error=True
            )
            return Result.fail(
                Errors.validation("No updates or conditional patches provided", field="updates")
            )

        updates = dict(updates)
        updates["updated_at"] = datetime.now().isoformat()

        # Prevent overwriting default_filter properties (e.g. entity_type) — mirrors update().
        for k in self.default_filters:
            updates.pop(k, None)

        # Serialize exactly as update() does. Skipping this would let a caller's raw
        # ``date``/enum/collection reach the driver and persist in a DIFFERENT shape
        # than every other writer stores (a native Date instead of an ISO string) —
        # the writer decides the storage type, so both write paths must decide alike.
        updates = to_neo4j_node(updates)

        patch_in_statuses, patch_in = self._guard_patch(guard.patch_if_prior_in)
        patch_not_in_statuses, patch_not_in = self._guard_patch(guard.patch_if_prior_not_in)

        df_clause = self._default_filter_clause()
        where_line = f"WHERE {df_clause}" if df_clause else ""

        # Lock BEFORE the read. MATCH takes no write-lock, so a plain read — or a
        # `WHERE n.status = $x` compare-and-set — lets two concurrent writers observe
        # the same prior. This first SET acquires the node's exclusive write-lock
        # (ADR-030's sentinel mechanism, single-statement form) and every clause below
        # runs under it; the sentinel is removed in the same statement, so it never
        # lingers. Measured: 4 concurrent completes on one node, 40 trials — exactly one
        # writer saw a non-completed prior every time, versus 39/40 trials producing 2-4
        # such writers without the lock. A unique token per call (rather than a constant)
        # keeps this a genuine property write no same-value optimization can elide.
        #
        # One statement in an auto-commit tx suffices because — unlike ADR-030's JSON
        # append — the conditional merge is fully Cypher-expressible, so no Python runs
        # between the read and the write. `_run_single` gives at-most-once execution (no
        # managed retry): a rare transient surfaces as a Result.fail the caller
        # propagates, never a silent re-run whose returned prior misreports the verdict.
        query = f"""
        MATCH (n:{self.label} {{uid: $uid}})
        {where_line}
        SET n.`_sg_lock` = $lock_token
        WITH n, n.status AS prior
        REMOVE n.`_sg_lock`
        WITH n, prior, coalesce(prior, '') AS prior_key
        WITH n, prior, prior_key, (NOT prior_key IN $refuse_statuses) AS applied
        SET n += CASE WHEN applied THEN $updates ELSE {{}} END
        SET n += CASE WHEN applied AND prior_key IN $patch_in_statuses THEN $patch_in ELSE {{}} END
        SET n += CASE
            WHEN applied AND NOT prior_key IN $patch_not_in_statuses THEN $patch_not_in ELSE {{}}
        END
        RETURN n AS node, prior AS prior, applied AS applied
        """

        params: dict[str, Any] = {
            "uid": uid,
            "lock_token": uuid4().hex,
            "updates": updates,
            # `x IN []` is false and `NOT x IN []` is true, so an unused knob is a no-op:
            # the first patch never fires, the second merges an empty map.
            "refuse_statuses": sorted(guard.refuse_if_prior_in),
            "patch_in_statuses": patch_in_statuses,
            "patch_in": patch_in,
            "patch_not_in_statuses": patch_not_in_statuses,
            "patch_not_in": patch_not_in,
        }
        params.update(self._default_filter_params())

        record = await self._run_single(query, params)

        if not record:
            self._track_db_metrics(
                "update_with_status_guard", time.time() - start_time, is_error=True
            )
            return Result.fail(Errors.not_found("resource", f"{self.label} {uid} not found"))

        # Status is written as a string everywhere (the mapper emits `EntityStatus.value`);
        # anything else is treated as absent, which is what `_coerce_status` would do with
        # it at the service anyway.
        raw_prior = record["prior"]
        entity = from_neo4j_node(dict(record["node"]), self.entity_class)

        self._track_db_metrics("update_with_status_guard", time.time() - start_time, is_error=False)

        return Result.ok(
            StatusGuardedOutcome(
                applied=bool(record["applied"]),
                prior_status=raw_prior if isinstance(raw_prior, str) else None,
                entity=entity,
            )
        )

    @staticmethod
    def _guard_patch(
        conditional: tuple[frozenset[str], Neo4jProperties] | None,
    ) -> tuple[builtins.list[str], dict[str, Any]]:
        """Split a guard's conditional patch into its (statuses, serialized patch) params.

        ``None`` yields the no-op pair — an empty status list (so the membership test
        decides nothing) and an empty map (so the merge writes nothing).
        """
        if conditional is None:
            return [], {}
        statuses, patch = conditional
        return sorted(statuses), to_neo4j_node(dict(patch))

    @safe_backend_operation("atomic_append_dual_track_checkin")
    async def atomic_append_dual_track_checkin(
        self, uid: str, snapshot: dict[str, Any], history_limit: int
    ) -> Result[bool]:
        """Atomically append a per-entity dual-track check-in snapshot (ADR-030).

        Node-lock-serialized so two near-simultaneous check-ins on the SAME entity
        can't lose a snapshot (the read-modify-write of the JSON ``dual_track_checkins``
        log runs under a Neo4j node write-lock). Replaces the former get()+update()
        read-modify-write in ``BaseAnalyticsService._store_dual_track_checkin``.

        Backend: ``_dual_track_checkin_store.atomic_append_checkin`` (flat list — the
        per-entity log has no dimension key).

        Args:
            uid: Entity UID.
            snapshot: ``DualTrackResult.to_checkin_snapshot`` dict.
            history_limit: Max snapshots retained (oldest dropped).

        Returns:
            Result[bool]: True if appended, NotFound if the entity does not exist.
        """
        from adapters.persistence.neo4j._dual_track_checkin_store import atomic_append_checkin

        appended = await atomic_append_checkin(
            self.driver,
            label=str(self.label),
            uid=uid,
            snapshot=snapshot,
            history_limit=history_limit,
        )
        if not appended:
            return Result.fail(Errors.not_found("resource", f"{self.label} {uid} not found"))
        return Result.ok(True)

    @safe_backend_operation("delete")
    async def delete(self, uid: str, cascade: bool = False) -> Result[bool]:
        """
        Delete any entity by UID.

        Removes an entity from the Neo4j database. Optionally deletes all relationships
        (cascade=True) or requires manual relationship cleanup (cascade=False).

        Args:
            uid: Unique identifier of the entity to delete
            cascade: If True, deletes entity and all its relationships (DETACH DELETE).
                    If False, fails if entity has relationships (requires manual cleanup).

        Returns:
            Result[bool]: Success with True if deleted, False if not found,
                         or Failure if database error occurs (e.g., relationships exist)

        Example:
            ```python
            backend = UniversalNeo4jBackend[Task](driver, "Task", Task)

            # Delete with relationships (cascade)
            result = await backend.delete("task:123", cascade=True)

            if result.is_ok and result.value:
                print("Task and all relationships deleted")

            # Delete without relationships (fails if relationships exist)
            result = await backend.delete("task:456", cascade=False)
            ```

        Warning:
            - cascade=True deletes ALL relationships (incoming and outgoing)
            - cascade=False will fail if entity has any relationships
            - Deletion is permanent - no soft delete or recovery
            - Consider backing up data before cascade delete operations

        Note:
            - Returns True even if entity didn't exist (idempotent)
            - Use cascade=True for most deletions to avoid orphaned relationships
        """
        start_time = time.time()

        df_clause = self._default_filter_clause()
        where_line = f"WHERE {df_clause}" if df_clause else ""

        if cascade:
            # DETACH DELETE removes entity AND all relationships
            query = f"""
            MATCH (n:{self.label} {{uid: $uid}})
            {where_line}
            DETACH DELETE n
            RETURN count(n) as deleted
            """
        else:
            # DELETE only - intentionally fails if relationships exist (safety check).
            # Use cascade=True to remove relationships too.
            query = f"""
            MATCH (n:{self.label} {{uid: $uid}})
            {where_line}
            DELETE n // noqa: CYP002 - intentional: non-DETACH DELETE is the safety check
            RETURN count(n) as deleted
            """

        params: dict[str, Any] = {"uid": uid}
        params.update(self._default_filter_params())

        async with self.driver.session() as session:
            try:
                result = await session.run(query, params)
                summary = await result.consume()

                deleted = summary.counters.nodes_deleted > 0

                # Track metrics
                self._track_db_metrics("delete", time.time() - start_time, is_error=False)

                return Result.ok(deleted)
            except NEO4J_EXCEPTIONS as e:
                error_msg = str(e)
                # Neo4j constraint error when trying to delete node with relationships
                if "Cannot delete" in error_msg and "relationship" in error_msg.lower():
                    self._track_db_metrics("delete", time.time() - start_time, is_error=True)
                    return Result.fail(
                        Errors.business(
                            rule="delete_with_relationships",
                            message=f"Cannot delete {self.label} '{uid}' - has existing relationships. "
                            "Use cascade=True to delete with relationships.",
                        )
                    )
                # Track error for other exceptions
                self._track_db_metrics("delete", time.time() - start_time, is_error=True)
                raise

    @safe_backend_operation("list")
    async def list(
        self,
        limit: int = 100,
        offset: int = 0,
        filters: dict[str, Any] | None = None,
        sort_by: str | None = None,
        sort_order: str = "asc",
    ) -> Result[tuple[builtins.list[T], int]]:
        """
        List any entity type with dynamic filters.

        Now uses UnifiedQueryBuilder with fluent API.
        Add a field to your model → it's automatically filterable!

        Returns:
            Result[tuple[list[T], int]]: (page of entities, total matching count).
            The total ignores limit/offset so callers can paginate — it mirrors
            ``get_user_entities`` and is what every consumer + the protocol expect.
        """
        # Build query using UnifiedQueryBuilder fluent API
        # Pass label explicitly to ensure correct Neo4j label is used
        builder = (
            self.query_builder.for_model(self.entity_class, label=self.label)
            .limit(limit)
            .offset(offset)
        )

        # Inject default_filters for Ku-type discrimination
        if self.default_filters:
            builder = builder.filter(**self.default_filters)

        if filters:
            builder = builder.filter(**filters)

        if sort_by:
            builder = builder.order_by(sort_by, desc=(sort_order == "desc"))

        query, params = builder.build()

        records = await self._run_records(query, params)

        entities = [from_neo4j_node(r["n"], self.entity_class) for r in records]

        # Total count ignores pagination; count() re-applies default_filters itself.
        count_result = await self.count(**(filters or {}))
        if count_result.is_error:
            return Result.fail(count_result)

        return Result.ok((entities, count_result.value))
