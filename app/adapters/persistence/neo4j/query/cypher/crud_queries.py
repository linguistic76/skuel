"""
CRUD Queries - Dynamic Query Generation for Neo4j
==================================================

Model-introspection based query builders for CRUD operations.
These are infrastructure-level utilities used by services.

Methods:
- build_search_query: Dynamic filtering with operators (eq, gt, lt, contains, in)
- build_text_search_query: Multi-field text search with OR semantics
- build_relationship_traversal_query: Single-query traversal (eliminates N+1)
- build_get_by_field_query: Get entities by field value
- build_list_query: Paginated listing with sorting
- build_count_query: Count entities with optional filters
"""

from dataclasses import fields, is_dataclass
from typing import Any, get_origin, get_type_hints

from adapters.persistence.neo4j._backend_helpers import direction_clause
from core.models.enums import EntityType, ExerciseScope, PublicationState, SearchVisibility
from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName
from core.models.type_hints import Neo4jProperties, Neo4jValue, UserUID
from core.utils.logging import get_logger

from ._helpers import convert_value_for_neo4j
from ._helpers import validate_identifier as _validate_identifier
from ._helpers import validate_label as _validate_label
from ._types import T

logger = get_logger(__name__)


def _is_sequence_field(entity_class: type, field_name: str) -> bool:
    """
    True when the model annotates ``field_name`` as list or tuple.

    Frozen domain models use ``tuple[str, ...]`` (e.g. ``tags``, ``nous``),
    DTOs use ``list[str]`` — both are array properties in Neo4j, so operators
    that branch on shape (``contains``, ``has``) must treat them alike.
    """
    try:
        type_hints = get_type_hints(entity_class)
        field_type = type_hints.get(field_name)
        origin = get_origin(field_type) if field_type else None
        return origin in (list, tuple)
    # intentional-broad: type introspection may raise arbitrary errors
    except Exception:
        return False


def build_search_query(
    entity_class: type[T], filters: dict[str, Any], label: str | None = None
) -> tuple[str, dict[str, Neo4jValue]]:
    """
    Auto-generate search query based on model fields.

    The plant grows on the lattice: Add a field to your model ->
    it's automatically queryable via this method!

    Args:
        entity_class: Domain model class (must be dataclass)
        filters: Dictionary of field_name: value to filter by
        label: Neo4j label (defaults to class name)

    Returns:
        Tuple of (cypher_query, parameters)

    Supported operators (via double underscore):
        - eq (default): Exact match
        - gt, lt, gte, lte: Comparisons
        - contains: String matching (array fields: element membership)
        - has: Exact match (array fields: element membership)
        - in: List membership

    Examples:
        # Simple equality
        query, params = build_search_query(
            Task,
            {'priority': 'high', 'status': 'in_progress'}
        )

        # Comparison operators
        query, params = build_search_query(
            Task,
            {'due_date__gte': date.today(), 'estimated_hours__lt': 5.0}
        )
    """
    if not is_dataclass(entity_class):
        raise ValueError(f"Entity class must be a dataclass, got {entity_class}")

    label = label or getattr(entity_class, "_neo4j_label", None) or entity_class.__name__
    field_names = {f.name for f in fields(entity_class)}

    where_clauses = []
    params: dict[str, Neo4jValue] = {}

    for filter_key, filter_value in filters.items():
        # Parse operator from filter key (e.g., "due_date__gte" -> "due_date", "gte")
        if "__" in filter_key:
            field_name, operator = filter_key.rsplit("__", 1)
        else:
            field_name, operator = filter_key, "eq"

        # Validate field exists in model
        if field_name not in field_names:
            logger.warning(f"Filter field '{field_name}' not in {entity_class.__name__}, skipping")
            continue

        # Convert value for Neo4j
        param_name = filter_key.replace("__", "_")
        neo4j_value = convert_value_for_neo4j(filter_value)

        # Build WHERE clause based on operator
        if operator == "eq":
            where_clauses.append(f"n.{field_name} = ${param_name}")
            params[param_name] = neo4j_value
        elif operator == "gt":
            where_clauses.append(f"n.{field_name} > ${param_name}")
            params[param_name] = neo4j_value
        elif operator == "lt":
            where_clauses.append(f"n.{field_name} < ${param_name}")
            params[param_name] = neo4j_value
        elif operator == "gte":
            where_clauses.append(f"n.{field_name} >= ${param_name}")
            params[param_name] = neo4j_value
        elif operator == "lte":
            where_clauses.append(f"n.{field_name} <= ${param_name}")
            params[param_name] = neo4j_value
        elif operator == "contains":
            # For list/array fields, use IN operator (reversed: value IN array)
            # For string fields, use CONTAINS (substring matching)
            if _is_sequence_field(entity_class, field_name):
                where_clauses.append(f"${param_name} IN n.{field_name}")
            else:
                where_clauses.append(f"n.{field_name} CONTAINS ${param_name}")

            params[param_name] = neo4j_value
        elif operator == "has":
            # Exact-match membership: scalar fields compare with `=`, array
            # fields check element membership (reversed: value IN array).
            # Unlike `contains`, scalar matching is exact, not substring —
            # the right semantics for category filtering (e.g. Ku/PS `nous`
            # lists vs Goals' scalar `domain`).
            if _is_sequence_field(entity_class, field_name):
                where_clauses.append(f"${param_name} IN n.{field_name}")
            else:
                where_clauses.append(f"n.{field_name} = ${param_name}")

            params[param_name] = neo4j_value
        elif operator == "in":
            where_clauses.append(f"n.{field_name} IN ${param_name}")
            params[param_name] = [convert_value_for_neo4j(v) for v in filter_value]
        elif operator == "not_in":
            where_clauses.append(f"NOT n.{field_name} IN ${param_name}")
            params[param_name] = [convert_value_for_neo4j(v) for v in filter_value]
        else:
            logger.warning(f"Unknown operator '{operator}', skipping")
            continue

    # Build final query
    where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

    query = f"""
    MATCH (n:{label})
    WHERE {where_clause}
    RETURN n
    """

    return query, params


def build_publication_clause(entity_alias: str = "n") -> tuple[str, dict[str, str]]:
    """Build the WHERE fragment that withholds unpublished curriculum content.

    THE single publication predicate — every reader that shows curriculum to a
    learner audience composes THIS, never a hand-written equivalent.

    **NULL-tolerant on purpose, and load-bearing.** Ingestion does not write
    absent frontmatter keys, so every node authored before ``publication_state``
    existed carries no such property. A bare ``= 'published'`` test would
    silently hide the entire existing corpus; the predicate therefore withholds
    only what is EXPLICITLY marked draft.

    Orthogonal to ``build_search_visibility_clause`` (audience/ownership) — this
    one asks "is it finished?", not "whose is it?".

    Returns:
        ``(fragment, params)`` — a parenthesized WHERE fragment plus the
        parameters it introduces.
    """
    _validate_identifier(entity_alias, context="entity alias")
    return (
        f"({entity_alias}.publication_state IS NULL"
        f" OR {entity_alias}.publication_state <> $publication_draft)",
        {"publication_draft": PublicationState.DRAFT.value},
    )


def build_knowledge_read_clause(
    entity_alias: str = "n", *, apply_publication_gate: bool = True
) -> tuple[str, Neo4jProperties]:
    """Build the WHERE fragment that scopes a read to visible curriculum knowledge.

    THE single composition point for "this query is about knowledge" — every
    reader that means *knowledge* rather than *any node* composes THIS.

    Three predicates, one call, because they failed together:

    1. **Type.** ``MATCH (ku:Entity)`` matches EVERY entity type, so a query
       named ``find_ready_to_learn`` was returning Tasks, Choices, Resources and
       — the reason this is a security fix, not a tidy-up — other users'
       UserEntry titles and summaries. The membership test is sourced from
       ``EntityType.is_knowledge()`` so the vocabulary keeps ONE definition
       (PathStep + Ku; see ADR-046, which is why PathStep belongs here).
    2. **Audience.** Delegated to ``build_search_visibility_clause`` rather than
       hand-written. Knowledge is ``SearchVisibility.PUBLIC`` — shared content,
       so the ownership half is deliberately EMPTY today. Composing it anyway is
       the point: if curriculum ever becomes scope-aware, every caller of this
       helper follows without being revisited.
    3. **Publication.** Rides along inside the visibility clause (PUBLIC is a
       gated visibility), so a knowledge read is NULL-tolerantly draft-gated by
       construction — no separate ``build_publication_clause`` call to forget.

    Excluding non-knowledge types is what actually closes the disclosure; the
    audience clause is the guard that keeps the next query honest.

    ``apply_publication_gate`` defaults True so a READ is gated by construction.
    Set it False for a WRITER that maintains a cached structural property
    (``compute_hub_scores``): the publication gate answers "should this be
    SHOWN", which is not a question a degree count should be asking. A writer
    that skipped drafts would leave them with no cached score, and nothing
    recomputes on publish — the value would still be missing or stale the moment
    the content became visible (Codex P2, #1009). Same spelling as
    ``build_search_visibility_clause``'s flag, and the same rule: the dangerous
    direction is a listing that leaks, not a maintenance pass that is thorough.

    Returns:
        ``(fragment, params)`` — a parenthesized WHERE fragment plus the
        parameters it introduces. Merge the params in verbatim.
    """
    _validate_identifier(entity_alias, context="entity alias")
    params: Neo4jProperties = {
        "knowledge_entity_types": sorted(t.value for t in EntityType if t.is_knowledge())
    }
    predicates = [f"{entity_alias}.entity_type IN $knowledge_entity_types"]

    visibility = (
        build_search_visibility_clause(
            SearchVisibility.PUBLIC, entity_alias=entity_alias, has_user=False
        )
        if apply_publication_gate
        else None
    )
    if visibility is not None:
        fragment, visibility_params = visibility
        predicates.append(fragment)
        params.update(visibility_params)

    return f"({' AND '.join(predicates)})", params


def build_search_visibility_clause(
    visibility: SearchVisibility | None,
    *,
    entity_alias: str = "n",
    has_user: bool,
    apply_publication_gate: bool = True,
    ownership_property: str = "user_uid",
) -> tuple[str, dict[str, str]] | None:
    """
    Build the WHERE fragment that scopes search results to their audience.

    ``apply_publication_gate`` (default True) additionally withholds
    draft-marked curriculum. It defaults ON so a NEW discovery surface is
    gated by construction — the dangerous direction is a listing that leaks
    unfinished content, not a fetch that is over-strict. The one sanctioned
    opt-out is a direct by-UID read (see ``_crud_mixin.get_visible_to_user``):
    the gate belongs to DISCOVERY, so a draft stays unlisted rather than
    forbidden and its author can still open it.

    THE single ownership/visibility mechanism for every search strategy
    (text, tags, graph traversal, faceted) — one composition point so no
    strategy grows its own ad-hoc filter. The fragment references
    ``$user_uid`` when ``has_user`` is True; callers must add it to params
    (they own the value). Constants the clause itself references (the
    curriculum scope literal) come back in the returned params dict —
    merge it into the query params verbatim.

    Semantics per SearchVisibility:
        None: no declaration — falls back to OWNER_ONLY when a user is
            present (scoping-by-default: a caller passing a user gets a
            scoped query unless the domain explicitly declares PUBLIC).
        PUBLIC: shared content — no ownership clause, but the publication
            predicate still applies (a draft PathStep has no audience yet).
        OWNER_ONLY: property scope on the domain's declared
            ``ownership_property`` (``DomainConfig.ownership_property``,
            default ``user_uid``; Group declares ``owner_uid`` — ADR-086).
            The property name is identifier-validated before interpolation —
            it comes from a frozen declaration, never from user input.
            ⚠ Without a user this applies NO clause — external surfaces
            (SearchRouter) are responsible for not exposing unscoped
            user-owned searches (fail-closed skip); internal callers keep
            today's semantics. A caller holding a ``user_uid`` that may be
            None must therefore pass ``has_user=True`` anyway and let the
            emitted predicate do the work: ``entity.user_uid = $user_uid``
            on a null parameter is a null predicate and matches nothing.
            Deriving ``has_user`` from ``user_uid is not None`` inverts that
            into a cross-user disclosure — it drops the predicate exactly
            when it is needed.
        SCOPE_AWARE: CURRICULUM-scope entities are always visible; owned
            scopes require the ``owner_uid`` claim, :OWNS, :SHARES_WITH, or
            group membership (:MEMBER_OF + :SHARED_WITH_GROUP). Without a
            user, only CURRICULUM survives — shared content is the
            fail-closed floor.

            ``owner_uid`` is checked alongside the :OWNS edge because the two
            are a dual write whose halves can be split in stored data: on
            Exercise the node persists first, and until the ADR-086 hardening
            (2026-08-28) a failed OWNS write only *warned*, so an owner could
            hold a create that reported success while the edge was missing.
            ``create()`` now returns that failure, but nodes written before it
            remain. Trusting the edge alone hides such an entity from its own
            owner. Reading either half keeps the owner's claim whole; both
            halves are written only by paths that already own the entity, so
            this widens the audience by nothing else.

    Returns:
        ``(fragment, params)`` — a parenthesized WHERE fragment plus the
        parameters it introduces — or None when no scoping applies.
    """
    if visibility is None:
        visibility = SearchVisibility.OWNER_ONLY if has_user else None

    # Curriculum-facing visibilities also carry the publication gate. OWNER_ONLY
    # domains (Activities, UserEntry) are excluded deliberately: they are not
    # curriculum, carry no publication_state, and their owner sees their own
    # work regardless of how finished it is.
    gated = apply_publication_gate and visibility in (
        SearchVisibility.PUBLIC,
        SearchVisibility.SCOPE_AWARE,
    )
    published, published_params = build_publication_clause(entity_alias) if gated else ("", {})
    if gated and visibility is SearchVisibility.PUBLIC:
        return published, published_params

    if visibility is None or visibility is SearchVisibility.PUBLIC:
        return None

    _validate_identifier(entity_alias, context="entity alias")
    alias = entity_alias

    if visibility is SearchVisibility.OWNER_ONLY:
        if not has_user:
            return None
        _validate_identifier(ownership_property, context="ownership property")
        return f"({alias}.{ownership_property} = $user_uid)", {}

    # SCOPE_AWARE — the scope value rides as a parameter (SKUEL021: only
    # identifiers that Cypher cannot parameterize, like relationship types
    # and labels, are interpolated — property VALUES never are).
    #
    # The publication gate binds to the CURRICULUM half only: shared curriculum
    # must be finished to face an audience, but an owner always sees their own
    # unfinished work (gating the owned half would hide a user's draft from
    # the user who is drafting it).
    scope_params = {
        "visibility_curriculum_scope": ExerciseScope.CURRICULUM.value,
        **published_params,
    }
    curriculum = (
        f"({alias}.scope = $visibility_curriculum_scope AND {published})"
        if gated
        else f"({alias}.scope = $visibility_curriculum_scope)"
    )
    if not has_user:
        return f"({curriculum})", scope_params
    owns = RelationshipName.OWNS.value
    shares = RelationshipName.SHARES_WITH.value
    member_of = RelationshipName.MEMBER_OF.value
    shared_with_group = RelationshipName.SHARED_WITH_GROUP.value
    group_label = NeoLabel.GROUP.value
    return (
        f"({curriculum}"
        f" OR {alias}.owner_uid = $user_uid"
        f" OR EXISTS {{ MATCH (:User {{uid: $user_uid}})-[:{owns}]->({alias}) }}"
        f" OR EXISTS {{ MATCH (:User {{uid: $user_uid}})-[:{shares}]->({alias}) }}"
        f" OR EXISTS {{ MATCH (:User {{uid: $user_uid}})-[:{member_of}]->"
        f"(:{group_label})<-[:{shared_with_group}]-({alias}) }})",
        scope_params,
    )


def build_text_search_query(
    entity_class: type[T],
    query: str,
    search_fields: tuple[str, ...] | list[str] | None = None,
    label: str | None = None,
    limit: int = 50,
    order_by: str = "created_at",
    order_desc: bool = True,
    visibility: SearchVisibility | None = None,
    user_uid: UserUID | None = None,
    ownership_property: str = "user_uid",
) -> tuple[str, dict[str, Neo4jValue]]:
    """
    Build text search query across multiple fields with OR semantics.

    Generates case-insensitive CONTAINS search across specified fields.
    This eliminates the need for hand-written text search Cypher in search services.

    Args:
        entity_class: Domain model class (must be dataclass)
        query: Search text (case-insensitive)
        search_fields: Fields to search (default: ("title", "description"))
        label: Neo4j label (defaults to class name)
        limit: Maximum results (default 50)
        order_by: Field to sort by (default "created_at")
        order_desc: Sort descending (default True)
        visibility: Domain search-visibility declaration; composed into the
            WHERE clause via build_search_visibility_clause()
        user_uid: Requesting user for the visibility clause
        ownership_property: The domain's declared ownership property for the
            OWNER_ONLY clause (DomainConfig.ownership_property)

    Returns:
        Tuple of (cypher_query, parameters)

    Example:
        # Search goals by title and description
        query, params = build_text_search_query(
            Goal,
            "health improvement",
            search_fields=("title", "description"),
            limit=20
        )
    """
    if not is_dataclass(entity_class):
        raise ValueError(f"Entity class must be a dataclass, got {entity_class}")

    label = label or entity_class.__name__

    # Default to title and description if not specified
    if search_fields is None:
        search_fields = ("title", "description")

    # Validate search fields exist in model
    valid_fields = {f.name for f in fields(entity_class)}
    validated_search_fields = []
    for field in search_fields:
        if field in valid_fields:
            validated_search_fields.append(field)
        else:
            logger.warning(f"Search field '{field}' not in {entity_class.__name__}, skipping")

    if not validated_search_fields:
        raise ValueError(
            f"No valid search fields for {entity_class.__name__}. "
            f"Requested: {search_fields}, Available: {valid_fields}"
        )

    # Build OR clauses for text search. Parenthesized so the visibility
    # clause can be ANDed safely — a bare OR-chain would let any non-first
    # field match bypass the ownership filter (AND binds tighter than OR).
    where_clauses = [
        f"toLower(n.{field}) CONTAINS toLower($query)" for field in validated_search_fields
    ]
    where_clause = f"({' OR '.join(where_clauses)})"

    params: dict[str, Neo4jValue] = {"query": query, "limit": limit}
    # ⚠ has_user=True is deliberate and load-bearing — do NOT derive it from
    # `user_uid is not None`. OWNER_ONLY must always emit its predicate: on a
    # null $user_uid it is a null predicate and matches nothing (fail-closed),
    # whereas dropping it returns EVERY user's rows. The clause's own docstring
    # names that inversion. All five clause-composing builders hold this one
    # convention themselves rather than each leaning on an upstream refusal in
    # another module — SearchRouter's skip keys on EntityType.is_user_owned(),
    # a different signal from the search_visibility the clause reads, and the
    # two agreeing today is a coincidence no builder should depend on.
    visibility_scope = build_search_visibility_clause(
        visibility,
        entity_alias="n",
        has_user=True,
        ownership_property=ownership_property,
    )
    if visibility_scope:
        visibility_clause, visibility_params = visibility_scope
        where_clause = f"{visibility_clause} AND {where_clause}"
        params.update(visibility_params)
        # Bind $user_uid whenever the clause references it — even when None, so
        # the emitted predicate can fail closed rather than error unbound. A
        # clause that does not reference it (PUBLIC's publication gate) still
        # never receives the caller's identity.
        if "$user_uid" in visibility_clause:
            params["user_uid"] = user_uid

    # Build ORDER BY clause
    direction = "DESC" if order_desc else "ASC"
    order_clause = ""
    if order_by and order_by in valid_fields:
        order_clause = f"ORDER BY n.{order_by} {direction}"
    elif order_by:
        logger.warning(f"Order field '{order_by}' not in {entity_class.__name__}, ignoring")

    cypher = f"""
    MATCH (n:{label})
    WHERE {where_clause}
    RETURN n
    {order_clause}
    LIMIT $limit
    """

    return cypher, params


def build_relationship_traversal_query(
    source_uid: str,
    relationship_type: str,
    target_label: NeoLabel,
    direction: str = "outgoing",
    limit: int = 100,
    visibility: SearchVisibility | None = None,
    user_uid: UserUID | None = None,
    ownership_property: str = "user_uid",
) -> tuple[str, dict[str, Neo4jValue]]:
    """
    Build single-query relationship traversal returning full target entities.

    Eliminates N+1 pattern by returning complete entities in one query.

    Args:
        source_uid: UID of the source entity
        relationship_type: Relationship type name (e.g., "FULFILLS_GOAL")
        target_label: Neo4j label of target entities (e.g., "Task", "Goal")
        direction: "outgoing", "incoming", or "both" (default "outgoing")
        limit: Maximum results (default 100)
        visibility: Domain search-visibility declaration; composed into the
            WHERE clause via build_search_visibility_clause() (ADR-085 G3 —
            traversal targets are scoped to their audience like every other
            search strategy)
        user_uid: Requesting user for the visibility clause
        ownership_property: The domain's declared ownership property for the
            OWNER_ONLY clause (DomainConfig.ownership_property)

    Returns:
        Tuple of (cypher_query, parameters)

    Example:
        # Get all tasks that fulfill a specific goal (incoming to goal)
        query, params = build_relationship_traversal_query(
            source_uid="goal:health-2025",
            relationship_type="FULFILLS_GOAL",
            target_label="Task",
            direction="incoming"
        )
    """
    from core.utils.validation_helpers import validate_field_name, validate_relationship_type

    # Validate inputs before Cypher interpolation
    if not validate_relationship_type(relationship_type):
        raise ValueError(f"Invalid relationship type: {relationship_type}")
    if not validate_field_name(target_label):
        raise ValueError(f"Invalid target label: {target_label}")

    # Build direction pattern
    arrow = direction_clause(direction, None, relationship_type)
    pattern = f"(source {{uid: $source_uid}}){arrow}(target:{target_label})"

    params: dict[str, Neo4jValue] = {"source_uid": source_uid, "limit": limit}
    where_line = ""
    # ⚠ has_user=True is deliberate and load-bearing — do NOT derive it from
    # `user_uid is not None`. This builder feeds get_by_relationship, which has
    # NO upstream fail-closed refusal (unlike the SearchRouter strategies), so
    # OWNER_ONLY must always emit its predicate: on a null $user_uid it is a
    # null predicate and matches nothing — fail-closed, not unscoped
    # (Codex P1 on #1120; same convention as faceted_search_raw).
    visibility_scope = build_search_visibility_clause(
        visibility, entity_alias="target", has_user=True, ownership_property=ownership_property
    )
    if visibility_scope:
        visibility_clause, visibility_params = visibility_scope
        where_line = f"WHERE {visibility_clause}"
        params.update(visibility_params)
        # Bind $user_uid whenever the clause references it — even when None,
        # so the emitted predicate can fail closed rather than error unbound.
        if "$user_uid" in visibility_clause:
            params["user_uid"] = user_uid

    cypher = f"""
    MATCH {pattern}
    {where_line}
    RETURN target
    LIMIT $limit
    """

    return cypher, params


def build_graph_aware_search_query(
    entity_class: type[T],
    query: str,
    source_uid: str,
    relationship_type: str,
    search_fields: tuple[str, ...] | list[str] | None = None,
    label: str | None = None,
    direction: str = "outgoing",
    limit: int = 50,
    order_by: str = "created_at",
    order_desc: bool = True,
    visibility: SearchVisibility | None = None,
    user_uid: UserUID | None = None,
    ownership_property: str = "user_uid",
) -> tuple[str, dict[str, Neo4jValue]]:
    """
    Build graph-aware search: text search + relationship traversal in ONE query.

    This is Neo4j's unique value proposition - combining property search
    with graph traversal in a single query. Answers questions like:
    - "Find KUs containing 'python' that ENABLE content I've mastered"
    - "Find tasks containing 'review' that FULFILL my health goal"

    Args:
        entity_class: Domain model class (must be dataclass)
        query: Search text (case-insensitive)
        source_uid: UID of the related entity to traverse from
        relationship_type: Relationship type name (e.g., "ENABLES_KNOWLEDGE", "FULFILLS_GOAL")
        search_fields: Fields to search (default: ("title", "description"))
        label: Neo4j label (defaults to class name)
        direction: "outgoing", "incoming", or "both" (default "outgoing")
        limit: Maximum results (default 50)
        order_by: Field to sort by (default "created_at")
        order_desc: Sort descending (default True)

    Returns:
        Tuple of (cypher_query, parameters)

    Example:
        # Find KUs containing "machine learning" connected to a mastered KU
        query, params = build_graph_aware_search_query(
            Ku,
            query="machine learning",
            source_uid="ku.python-basics",
            relationship_type="ENABLES_KNOWLEDGE",
            search_fields=("title", "content"),
            direction="incoming", # KUs that are enabled BY python-basics
        )

        # Find tasks containing "review" that fulfill a specific goal
        query, params = build_graph_aware_search_query(
            Task,
            query="review",
            source_uid="goal:health-2025",
            relationship_type="FULFILLS_GOAL",
            direction="incoming", # Tasks that fulfill this goal
        )
    """
    if not is_dataclass(entity_class):
        raise ValueError(f"Entity class must be a dataclass, got {entity_class}")

    label = label or entity_class.__name__

    # Default to title and description if not specified
    if search_fields is None:
        search_fields = ("title", "description")

    # Validate search fields exist in model
    valid_fields = {f.name for f in fields(entity_class)}
    validated_search_fields = []
    for field in search_fields:
        if field in valid_fields:
            validated_search_fields.append(field)
        else:
            logger.warning(f"Search field '{field}' not in {entity_class.__name__}, skipping")

    if not validated_search_fields:
        raise ValueError(
            f"No valid search fields for {entity_class.__name__}. "
            f"Requested: {search_fields}, Available: {valid_fields}"
        )

    from core.utils.validation_helpers import validate_relationship_type as _validate_rel_type

    # Validate relationship_type before Cypher interpolation
    if not _validate_rel_type(relationship_type):
        raise ValueError(f"Invalid relationship type: {relationship_type}")

    # Build direction pattern for relationship
    arrow = direction_clause(direction, None, relationship_type)
    rel_pattern = f"(source {{uid: $source_uid}}){arrow}(target:{label})"

    # Build OR clauses for text search on target. Parenthesized so the
    # visibility clause can be ANDed safely (AND binds tighter than OR).
    text_where_clauses = [
        f"toLower(target.{field}) CONTAINS toLower($query)" for field in validated_search_fields
    ]
    text_where = f"({' OR '.join(text_where_clauses)})"

    params: dict[str, Neo4jValue] = {"source_uid": source_uid, "query": query, "limit": limit}
    # ⚠ has_user=True is deliberate and load-bearing — do NOT derive it from
    # `user_uid is not None`. OWNER_ONLY must always emit its predicate: on a
    # null $user_uid it is a null predicate and matches nothing (fail-closed),
    # whereas dropping it returns EVERY user's rows. The clause's own docstring
    # names that inversion. All five clause-composing builders hold this one
    # convention themselves rather than each leaning on an upstream refusal in
    # another module — SearchRouter's skip keys on EntityType.is_user_owned(),
    # a different signal from the search_visibility the clause reads, and the
    # two agreeing today is a coincidence no builder should depend on.
    visibility_scope = build_search_visibility_clause(
        visibility,
        entity_alias="target",
        has_user=True,
        ownership_property=ownership_property,
    )
    if visibility_scope:
        visibility_clause, visibility_params = visibility_scope
        text_where = f"{visibility_clause} AND {text_where}"
        params.update(visibility_params)
        # Bind $user_uid whenever the clause references it — even when None, so
        # the emitted predicate can fail closed rather than error unbound. A
        # clause that does not reference it (PUBLIC's publication gate) still
        # never receives the caller's identity.
        if "$user_uid" in visibility_clause:
            params["user_uid"] = user_uid

    # Build ORDER BY clause
    direction_str = "DESC" if order_desc else "ASC"
    order_clause = ""
    if order_by and order_by in valid_fields:
        order_clause = f"ORDER BY target.{order_by} {direction_str}"
    elif order_by:
        logger.warning(f"Order field '{order_by}' not in {entity_class.__name__}, ignoring")

    # Combine relationship traversal with text search
    cypher = f"""
    MATCH {rel_pattern}
    WHERE {text_where}
    RETURN target
    {order_clause}
    LIMIT $limit
    """

    return cypher, params


def build_array_contains_query(
    label: NeoLabel,
    field: str,
    value: str,
    limit: int = 50,
    order_by: str | None = "created_at",
    order_desc: bool = True,
    visibility: SearchVisibility | None = None,
    user_uid: UserUID | None = None,
    ownership_property: str = "user_uid",
) -> tuple[str, dict[str, Neo4jValue]]:
    """
    Build query to find entities where array field contains a value.

    Uses case-insensitive matching via ANY() predicate.
    Ideal for searching tags, categories, or other array properties.

    Args:
        label: Neo4j node label (e.g., "Entity", "Task")
        field: Array field name (e.g., "tags")
        value: Value to search for (case-insensitive)
        limit: Maximum results (default 50)
        order_by: Field to sort by (default "created_at")
        order_desc: Sort descending (default True)
        visibility: Domain search-visibility declaration; composed into the
            WHERE clause via build_search_visibility_clause() (ADR-085 G5 —
            the shape its sibling build_array_any_match_query already has)
        user_uid: Requesting user for the visibility clause

    Returns:
        Tuple of (cypher_query, parameters)

    Example:
        # Find KUs tagged with "python"
        query, params = build_array_contains_query(
            label="Entity",
            field="tags",
            value="python",
            limit=20
        )

        # Find tasks with "urgent" tag
        query, params = build_array_contains_query(
            label="Task",
            field="tags",
            value="urgent"
        )
    """
    # Build ORDER BY clause
    order_clause = ""
    if order_by:
        direction = "DESC" if order_desc else "ASC"
        order_clause = f"ORDER BY n.{order_by} {direction}"

    # Case-insensitive array contains using ANY(). Parenthesized so the
    # visibility clause can be ANDed safely.
    match_where = f"(ANY(item IN n.{field} WHERE toLower(item) CONTAINS toLower($value)))"

    params: dict[str, Neo4jValue] = {"value": value, "limit": limit}
    # ⚠ has_user=True is deliberate and load-bearing — do NOT derive it from
    # `user_uid is not None`. This builder feeds search_array_field, which has
    # NO upstream fail-closed refusal (unlike the SearchRouter strategies), so
    # OWNER_ONLY must always emit its predicate: on a null $user_uid it is a
    # null predicate and matches nothing — fail-closed, not unscoped
    # (Codex P1 on #1120; same convention as faceted_search_raw).
    visibility_scope = build_search_visibility_clause(
        visibility, entity_alias="n", has_user=True, ownership_property=ownership_property
    )
    if visibility_scope:
        visibility_clause, visibility_params = visibility_scope
        match_where = f"{visibility_clause} AND {match_where}"
        params.update(visibility_params)
        # Bind $user_uid whenever the clause references it — even when None,
        # so the emitted predicate can fail closed rather than error unbound.
        if "$user_uid" in visibility_clause:
            params["user_uid"] = user_uid

    cypher = f"""
    MATCH (n:{label})
    WHERE {match_where}
    RETURN n
    {order_clause}
    LIMIT $limit
    """

    return cypher, params


def build_array_any_match_query(
    label: NeoLabel,
    field: str,
    values: list[str],
    match_all: bool = False,
    limit: int = 50,
    order_by: str | None = "created_at",
    order_desc: bool = True,
    visibility: SearchVisibility | None = None,
    user_uid: UserUID | None = None,
    ownership_property: str = "user_uid",
) -> tuple[str, dict[str, Neo4jValue]]:
    """
    Build query to find entities matching any/all values in array field.

    Supports two modes:
    - match_all=False: OR semantics (any value matches)
    - match_all=True: AND semantics (all values must match)

    Args:
        label: Neo4j node label
        field: Array field name (e.g., "tags")
        values: List of values to search for
        match_all: If True, require ALL values; if False, ANY value
        limit: Maximum results (default 50)
        order_by: Field to sort by (default "created_at")
        order_desc: Sort descending (default True)

    Returns:
        Tuple of (cypher_query, parameters)

    Example:
        # Find KUs with ANY of these tags
        query, params = build_array_any_match_query(
            label="Entity",
            field="tags",
            values=["python", "ml", "data-science"],
            match_all=False
        )

        # Find KUs with ALL of these tags
        query, params = build_array_any_match_query(
            label="Entity",
            field="tags",
            values=["python", "beginner"],
            match_all=True
        )
    """
    # Build ORDER BY clause
    order_clause = ""
    if order_by:
        direction = "DESC" if order_desc else "ASC"
        order_clause = f"ORDER BY n.{order_by} {direction}"

    if match_all:
        # AND semantics: ALL values must be in the array
        # Use ALL() predicate with case-insensitive matching
        match_where = f"""ALL(v IN $values WHERE
            ANY(item IN n.{field} WHERE toLower(item) = toLower(v))
        )"""
    else:
        # OR semantics: ANY value matches
        match_where = f"""ANY(v IN $values WHERE
            ANY(item IN n.{field} WHERE toLower(item) CONTAINS toLower(v))
        )"""

    result_values: list[str | int | float] = list(values)
    params: dict[str, Neo4jValue] = {"values": result_values, "limit": limit}
    # ⚠ has_user=True is deliberate and load-bearing — do NOT derive it from
    # `user_uid is not None`. OWNER_ONLY must always emit its predicate: on a
    # null $user_uid it is a null predicate and matches nothing (fail-closed),
    # whereas dropping it returns EVERY user's rows. The clause's own docstring
    # names that inversion. All five clause-composing builders hold this one
    # convention themselves rather than each leaning on an upstream refusal in
    # another module — SearchRouter's skip keys on EntityType.is_user_owned(),
    # a different signal from the search_visibility the clause reads, and the
    # two agreeing today is a coincidence no builder should depend on.
    visibility_scope = build_search_visibility_clause(
        visibility,
        entity_alias="n",
        has_user=True,
        ownership_property=ownership_property,
    )
    if visibility_scope:
        visibility_clause, visibility_params = visibility_scope
        match_where = f"{visibility_clause} AND {match_where}"
        params.update(visibility_params)
        # Bind $user_uid whenever the clause references it — even when None, so
        # the emitted predicate can fail closed rather than error unbound. A
        # clause that does not reference it (PUBLIC's publication gate) still
        # never receives the caller's identity.
        if "$user_uid" in visibility_clause:
            params["user_uid"] = user_uid

    cypher = f"""
    MATCH (n:{label})
    WHERE {match_where}
    RETURN n
    {order_clause}
    LIMIT $limit
    """

    return cypher, params


def build_get_by_field_query(
    entity_class: type[T], field_name: str, field_value: Any, label: str | None = None
) -> tuple[str, dict[str, Neo4jValue]]:
    """
    Generate query to get entities by a specific field value.

    Args:
        entity_class: Domain model class
        field_name: Field to filter by
        field_value: Value to match
        label: Neo4j label (defaults to class name)

    Returns:
        Tuple of (cypher_query, parameters)

    Example:
        query, params = build_get_by_field_query(Task, 'uid', 'task-123')
    """
    if not is_dataclass(entity_class):
        raise ValueError(f"Entity class must be a dataclass, got {entity_class}")

    field_names = {f.name for f in fields(entity_class)}
    if field_name not in field_names:
        raise ValueError(f"Field '{field_name}' not found in {entity_class.__name__}")

    label = label or entity_class.__name__
    neo4j_value = convert_value_for_neo4j(field_value)

    query = f"""
    MATCH (n:{label})
    WHERE n.{field_name} = $field_value
    RETURN n
    """

    return query, {"field_value": neo4j_value}


def build_list_query(
    entity_class: type[T],
    label: str | None = None,
    limit: int = 100,
    skip: int = 0,
    order_by: str | None = None,
    order_desc: bool = False,
) -> tuple[str, dict[str, Neo4jValue]]:
    """
    Generate query to list entities with pagination and sorting.

    Args:
        entity_class: Domain model class
        label: Neo4j label
        limit: Maximum number of results
        skip: Number of results to skip
        order_by: Field to order by
        order_desc: Sort descending

    Returns:
        Tuple of (cypher_query, parameters)

    Example:
        query, params = build_list_query(
            Task,
            limit=20,
            order_by='created_at',
            order_desc=True
        )
    """
    if not is_dataclass(entity_class):
        raise ValueError(f"Entity class must be a dataclass, got {entity_class}")

    label = label or getattr(entity_class, "_neo4j_label", None) or entity_class.__name__

    # Validate order_by field if provided
    if order_by:
        field_names = {f.name for f in fields(entity_class)}
        if order_by not in field_names:
            logger.warning(f"Order field '{order_by}' not in {entity_class.__name__}, ignoring")
            order_by = None

    order_clause = ""
    if order_by:
        direction = "DESC" if order_desc else "ASC"
        order_clause = f"ORDER BY n.{order_by} {direction}"

    query = f"""
    MATCH (n:{label})
    RETURN n
    {order_clause}
    SKIP $skip
    LIMIT $limit
    """

    return query, {"limit": limit, "skip": skip}


def build_count_query(
    entity_class: type[T], filters: dict[str, Any] | None = None, label: str | None = None
) -> tuple[str, dict[str, Neo4jValue]]:
    """
    Generate query to count entities with optional filters.

    Args:
        entity_class: Domain model class
        filters: Optional filters (uses same syntax as build_search_query)
        label: Neo4j label

    Returns:
        Tuple of (cypher_query, parameters)

    Example:
        query, params = build_count_query(
            Task,
            {'priority': 'high', 'status': 'completed'}
        )
    """
    if filters:
        # Reuse search query logic but return count
        search_query, params = build_search_query(entity_class, filters, label)
        # Replace RETURN n with RETURN count(n)
        count_query = search_query.replace("RETURN n", "RETURN count(n) as count")
        return count_query, params
    else:
        label = label or entity_class.__name__
        query = f"MATCH (n:{label}) RETURN count(n) as count"
        return query, {}


def get_filterable_fields(entity_class: type[T]) -> list[str]:
    """
    Get list of field names that can be used for filtering.

    Args:
        entity_class: Domain model class

    Returns:
        List of field names

    Example:
        fields = get_filterable_fields(Task)
        # ['uid', 'title', 'priority', 'status', 'due_date', ...]
    """
    if not is_dataclass(entity_class):
        raise ValueError(f"Entity class must be a dataclass, got {entity_class}")

    return [f.name for f in fields(entity_class)]


def get_supported_operators() -> list[str]:
    """Get list of supported filter operators."""
    return ["eq", "gt", "lt", "gte", "lte", "contains", "in", "not_in"]


# =============================================================================
# CONSOLIDATION - Extended Query Builders (January 2026)
# =============================================================================


def build_distinct_values_query(
    label: NeoLabel,
    field: str,
    user_uid: UserUID | None = None,
) -> tuple[str, dict[str, Neo4jValue]]:
    """
    Build query to get distinct values from a field, with occurrence counts.

    Used for category listing, dynamic filter options, and frequency-ranked
    facet vocabularies (library tag chips). Each row carries ``value`` plus
    ``count`` — how many nodes (array elements, for list fields) carry it —
    so callers that only need the distinct values read ``value`` and callers
    that rank by usage read ``count`` from the same query.

    Args:
        label: Neo4j node label
        field: Field name to get distinct values from
        user_uid: Optional user filter (multi-tenant)

    Returns:
        Tuple of (cypher_query, parameters)

    Example:
        # Get all categories for a user
        query, params = build_distinct_values_query("Task", "category", user_uid="user:123")

        # Get all categories globally (admin only)
        query, params = build_distinct_values_query("Task", "category")
    """
    _validate_label(label)
    _validate_identifier(field)

    params: dict[str, Neo4jValue] = {}

    # Array-valued fields (e.g. Ku/PS `nous` topic lists) contribute each
    # element as its own distinct value; scalar fields pass through unchanged.
    unwind_clause = (
        f"UNWIND (CASE WHEN n.{field} IS :: LIST<ANY> THEN n.{field} ELSE [n.{field}] END) AS value"
    )

    # This builds a public FACET VOCABULARY (the library tag/nous chips), so a
    # draft's unique tag would otherwise appear as a selectable filter that
    # returns nothing — unpublished taxonomy leaking through a gated catalogue
    # (Codex #1006). NULL-tolerant, hence inert for non-curriculum labels.
    published, published_params = build_publication_clause("n")
    params.update(published_params)

    # `is not None`, never truthiness: an empty-string uid must produce NO rows,
    # not silently fall through to the corpus-wide branch. This query is a
    # multi-tenant scope key — the failure direction has to be "shows nothing",
    # never "shows everyone" (the OWNER_ONLY tag vocabulary reaches this).
    if user_uid is not None:
        query = f"""
        MATCH (n:{label})
        WHERE n.user_uid = $user_uid AND n.{field} IS NOT NULL AND {published}
        {unwind_clause}
        RETURN value, count(*) AS count
        ORDER BY value
        """
        params["user_uid"] = user_uid
    else:
        query = f"""
        MATCH (n:{label})
        WHERE n.{field} IS NOT NULL AND {published}
        {unwind_clause}
        RETURN value, count(*) AS count
        ORDER BY value
        """

    return query, params


# The live FORWARD (parent)->(child) containment vocabulary: the six HAS_SUB*
# edges `_HierarchyMixin` writes, plus HAS_STEP and ORGANIZES. Copied from the
# canonical alternation in `query/graph_traversal.py:69-72`, which traverses the
# same bidirectional parent/child shape.
#
# Forward-only is deliberate. `build_hierarchy_query` walks both directions
# EXPLICITLY — `(parent)-[:R]->(n)` and `(n)-[:R]->(child)` — so adding the
# inverse `SUB*_OF` legs would make each child match as its own parent.
#
# Was `["CONTAINS", "AGGREGATES", "HAS_STEP"]`: neither CONTAINS nor AGGREGATES
# is a RelationshipName member or exists in the graph, so this read had only
# ever matched HAS_STEP and every activity hierarchy was invisible to it — the
# same bug as `get_siblings` (CYPHER_VOCABULARY_FINDINGS.md § 5).
_HIERARCHY_FORWARD_EDGES: tuple[str, ...] = (
    RelationshipName.HAS_SUBTASK.value,
    RelationshipName.HAS_SUBGOAL.value,
    RelationshipName.HAS_SUBHABIT.value,
    RelationshipName.HAS_SUBEVENT.value,
    RelationshipName.HAS_SUBCHOICE.value,
    RelationshipName.HAS_SUBPRINCIPLE.value,
    RelationshipName.HAS_STEP.value,
    RelationshipName.ORGANIZES.value,
)


def build_hierarchy_query(
    label: NeoLabel,
    uid: str,
    relationship_types: list[str] | None = None,
) -> tuple[str, dict[str, Neo4jValue]]:
    """
    Build query for hierarchical structure (parents and children).

    Returns the entity's position in containment hierarchy.

    Args:
        label: Neo4j node label
        uid: Entity UID
        relationship_types: Relationship types for hierarchy. Defaults to the
            live forward containment vocabulary (see ``_HIERARCHY_FORWARD_EDGES``).

    Returns:
        Tuple of (cypher_query, parameters)

    Example:
        query, params = build_hierarchy_query("Lp", "lp:python-basics")
    """
    _validate_label(label)
    rel_list = relationship_types or list(_HIERARCHY_FORWARD_EDGES)
    for rel in rel_list:
        _validate_identifier(rel, context="relationship type")
    rel_types = "|".join(rel_list)

    query = f"""
    MATCH (n:{label} {{uid: $uid}})

    // Find parent containers
    OPTIONAL MATCH (parent)-[:{rel_types}]->(n)
    WITH n, collect(DISTINCT {{
        uid: parent.uid,
        type: labels(parent)[0],
        title: parent.title
    }}) as parents

    // Find child elements
    OPTIONAL MATCH (n)-[:{rel_types}]->(child)
    WITH n, parents, collect(DISTINCT {{
        uid: child.uid,
        type: labels(child)[0],
        title: child.title,
        sequence: child.sequence
    }}) as children

    RETURN n, parents, children
    """

    return query, {"uid": uid}


def build_prerequisite_traversal_query(
    label: NeoLabel,
    uid: str,
    relationship_types: list[str],
    depth: int = 3,
    direction: str = "outgoing",
) -> tuple[str, dict[str, Neo4jValue]]:
    """
    Build query for prerequisite chain traversal.

    Supports both prerequisite chains (outgoing) and enabled-by queries (incoming).

    Args:
        label: Neo4j node label
        uid: Starting entity UID
        relationship_types: Relationship types for prerequisites (e.g., ["REQUIRES_KNOWLEDGE"])
        depth: Maximum traversal depth (1-10)
        direction: "outgoing" for prerequisites, "incoming" for enabled-by

    Returns:
        Tuple of (cypher_query, parameters)

    Example:
        # Get prerequisites
        query, params = build_prerequisite_traversal_query(
            "Entity", "ku:python-advanced", ["REQUIRES_KNOWLEDGE"], direction="outgoing"
        )

        # Get what this enables
        query, params = build_prerequisite_traversal_query(
            "Entity", "ku:python-basics", ["REQUIRES_KNOWLEDGE"], direction="incoming"
        )
    """
    rel_pattern = "|".join(relationship_types)

    # Prerequisites traverse forward from start (outgoing, farthest-first);
    # enabled-by inverts the traversal (incoming, nearest-first).
    is_outgoing = direction == "outgoing"
    arrow = direction_clause(
        "outgoing" if is_outgoing else "incoming", None, f"{rel_pattern}*1..{depth}"
    )
    order = "DESC" if is_outgoing else "ASC"
    # `WHERE n <> start` guards against a prerequisite cycle (A→B→A) binding the
    # traversal back to the start node — which would otherwise return the requested
    # entity as its own prerequisite. (Nothing upstream rejects cycles, so the
    # query must — same guard as build_prerequisite_chain_query.)
    query = f"""
    MATCH (start:{label} {{uid: $uid}})
    MATCH path = (start){arrow}(n:{label})
    WHERE n <> start
    WITH DISTINCT n, length(path) as distance
    ORDER BY distance {order}
    RETURN n
    """

    return query, {"uid": uid}


def build_prerequisite_chain_query(
    label: NeoLabel,
    uid: str,
    relationship_types: list[str],
    depth: int = 3,
) -> tuple[str, dict[str, Neo4jValue]]:
    """
    Build a flat, distance-annotated prerequisite-chain query.

    Unlike :func:`build_prerequisite_traversal_query` (which drops ``distance`` at
    ``RETURN n``), this returns each *distinct* prerequisite paired with its
    **minimum** hop distance from the start node — so a node reachable by several
    paths (diamond dependency) appears exactly once, at its nearest distance.
    That min-distance dedup is what makes downstream totals honest: counting the
    returned rows is a true count of distinct prerequisites, with no double-count.

    Always traverses outgoing (start → prerequisites), nearest-first.

    Args:
        label: Neo4j node label
        uid: Starting entity UID
        relationship_types: Prerequisite relationship type strings (any of them
            may connect a hop; e.g. ["REQUIRES_STEP", "REQUIRES_KNOWLEDGE"])
        depth: Maximum traversal depth (1-10)

    Returns:
        Tuple of (cypher_query, parameters). Each record has keys ``uid``,
        ``title``, ``domain``, ``entity_type`` and ``distance`` (int, ≥1),
        ordered by distance ascending. Fields are projected directly (not the
        node) so heterogeneous prerequisite types — Ku *and* PathStep — return
        uniformly without per-type model construction.
    """
    rel_pattern = "|".join(relationship_types)
    arrow = direction_clause("outgoing", None, f"{rel_pattern}*1..{depth}")
    # `WHERE n <> start` guards against a prerequisite cycle (A→B→A) binding the
    # traversal back to the start node — which would otherwise return the requested
    # entity as its own prerequisite and inflate the totals. (link_prerequisite does
    # not reject cycles, so the query must.)
    query = f"""
    MATCH (start:{label} {{uid: $uid}})
    MATCH path = (start){arrow}(n:{label})
    WHERE n <> start
    WITH n, min(length(path)) AS distance
    RETURN n.uid AS uid, n.title AS title, n.domain AS domain,
           n.entity_type AS entity_type, distance
    ORDER BY distance ASC
    """

    return query, {"uid": uid}
