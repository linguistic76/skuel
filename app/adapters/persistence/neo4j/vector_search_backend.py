"""
Vector Search Backend
======================

Backend for Neo4j vector index queries and full-text search.
Does NOT extend UniversalNeo4jBackend — takes a Neo4jQueryExecutor directly.

Migrates 5 execute_query calls from Neo4jVectorSearchService.

See: /docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from adapters.persistence.neo4j.query.cypher import build_publication_clause
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger(__name__)

if TYPE_CHECKING:
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
    from core.models.enums.neo_labels import NeoLabel
    from core.models.type_hints import FilterParams
    from core.ports.query_types import SemanticSearchChunkResult


# Facet-scoped chunk search post-filters AFTER the vector index ranks by score
# (Neo4j 5.26 has no pre-filtered vector search), so higher-scoring off-facet
# chunks can crowd out valid in-scope ones. Widen the candidate pool through
# this schedule until `limit` in-scope chunks survive — early-exit for
# well-populated facets, ceiling (last step) for narrow ones. Unscoped search
# keeps a single 2x over-fetch. Superseded by pre-filtered vector search at scale.
_SCOPED_CANDIDATE_SCHEDULE: tuple[int, ...] = (10, 40, 160)


class VectorSearchBackend:
    """Backend for vector search persistence operations."""

    def __init__(self, executor: Neo4jQueryExecutor) -> None:
        self._executor = executor

    async def query_vector_index(
        self, index_name: str, limit: int, embedding: list[float], min_score: float
    ) -> Result[list[dict[str, Any]]]:
        """Query a Neo4j vector index for similar nodes, excluding draft curriculum.

        THE vector-discovery chokepoint — gating here covers every similarity
        surface at once rather than per-caller. The related-concepts chips on
        /explore/{ku,ps}/{uid} filtered on score alone, so a draft-marked Ku or
        PathStep surfaced with its title, UID and a direct link — discoverable
        despite the contract that drafts stay unlisted (Codex #1006).

        The predicate is NULL-tolerant, so it is inert for every non-curriculum
        vector (Goal/Task/UserEntry nodes carry no ``publication_state``) and for
        the pre-``publication_state`` corpus. It withholds only what an author
        explicitly marked draft.
        """
        published, published_params = build_publication_clause("node")
        return await self._executor.execute_query(
            f"""
            // Vector similarity search using native index
            CALL db.index.vector.queryNodes($index_name, $limit, $embedding)
            YIELD node, score
            WHERE score >= $min_score AND {published}
            RETURN node, score
            ORDER BY score DESC
            """,
            {
                "index_name": index_name,
                "limit": limit,
                "embedding": embedding,
                "min_score": min_score,
                **published_params,
            },
        )

    async def get_node_embedding(self, label: NeoLabel, uid: str) -> Result[list[dict[str, Any]]]:
        """Get the embedding vector for a specific node."""
        # Label is validated by the service layer (comes from config, not user input)
        return await self._executor.execute_query(
            f"""
            MATCH (source:{label} {{uid: $uid}})
            RETURN source.embedding as embedding
            """,
            {"uid": uid},
        )

    async def query_fulltext_index(
        self, index_name: str, query_text: str, limit: int
    ) -> Result[list[dict[str, Any]]]:
        """Query a Neo4j full-text index, excluding draft curriculum.

        The fulltext twin of ``query_vector_index``'s gate: hybrid search reads
        both doors, so an ungated fulltext path would resurface draft-marked
        curriculum that the vector gate withholds (Codex #1006 class). Same
        NULL-tolerant predicate — inert for nodes without ``publication_state``.
        """
        published, published_params = build_publication_clause("node")
        return await self._executor.execute_query(
            f"""
            CALL db.index.fulltext.queryNodes($index_name, $query_text)
            YIELD node, score
            WHERE {published}
            RETURN node, score
            ORDER BY score DESC
            LIMIT $limit
            """,
            {
                "index_name": index_name,
                "query_text": query_text,
                "limit": limit,
                **published_params,
            },
        )

    async def get_semantic_relationships(
        self, entity_uid: str, context_uids: list[str]
    ) -> Result[list[dict[str, Any]]]:
        """Get semantic relationships between entity and context UIDs."""
        return await self._executor.execute_query(
            """
            MATCH (entity:Entity {uid: $entity_uid})
            MATCH (context:Entity)
            WHERE context.uid IN $context_uids
            MATCH (entity)-[r]->(context)
            WHERE r.confidence IS NOT NULL
            RETURN
                COALESCE(r.semantic_type, type(r)) as relationship_type,
                r.confidence as confidence,
                COALESCE(r.strength, 1.0) as strength
            """,
            {"entity_uid": entity_uid, "context_uids": context_uids},
        )

    async def semantic_search_chunks(
        self,
        query_embedding: list[float],
        limit: int,
        threshold: float,
        chunk_types: list[str] | None = None,
        parent_uid: str | None = None,
        parent_filters: FilterParams | None = None,
        owner_uid: str | None = None,
    ) -> Result[list[SemanticSearchChunkResult]]:
        """Vector search across :ContentChunk nodes for precise RAG retrieval.

        Targets `contentchunk_embedding_idx` and joins back through
        :HAS_CHUNK / :HAS_CONTENT to surface the owning Entity (typically a
        PathStep) so callers can cite the parent in responses.

        ``parent_filters`` scopes results to chunks whose owning Entity matches
        the active facets (e.g. ``{"nous": "body", "learning_level": "beginner"}``)
        — the same facet→property mapping faceted search applies to entities, now
        applied to the chunk's parent so body hits honor the facets instead of
        leaking across topics. List-vs-scalar membership matches `_search_raw_mixin`.

        ``owner_uid`` is the canon-P3 vault scope: only chunks whose parent the
        given user OWNS and that is not marked ``private: true`` survive. The
        owner rides the parent's OWNS edge — chunks never carry an owner
        property — and the private gate is belt-and-suspenders (a private note
        structurally has no chunks; the WHERE guarantees it anyway). Scoped
        rows additionally return ``parent_metadata`` (the raw metadata JSON,
        carrying ``vault_file_path`` for citations). With ``owner_uid=None``
        the emitted Cypher is byte-identical to the unscoped query — guarded by
        ``test_unscoped_query_is_single_pass_and_unchanged``.
        """
        parts = [
            """CALL db.index.vector.queryNodes(
            'contentchunk_embedding_idx',
            $candidate_limit,
            $query_embedding
        ) YIELD node AS chunk, score
        WHERE score >= $threshold"""
        ]
        if chunk_types:
            parts.append("AND chunk.chunk_type IN $chunk_types")
        if parent_uid:
            parts.append(
                """AND EXISTS {
                MATCH (chunk)<-[:HAS_CHUNK]-(content:Content {uid: $parent_uid})
            }"""
            )
        parts.append(
            """MATCH (chunk)<-[:HAS_CHUNK]-(content:Content)<-[:HAS_CONTENT]-(parent:Entity)"""
        )
        params: dict[str, Any] = {
            "query_embedding": query_embedding,
            "limit": limit,
            "threshold": threshold,
            "chunk_types": chunk_types,
            "parent_uid": parent_uid,
        }
        scope_clauses: list[str] = []
        # Owner scope (canon P3): OWNS edge on the parent + the hard private
        # exclusion. Ordered ahead of the facet clauses so the cheap edge
        # check prunes before property comparisons.
        if owner_uid:
            scope_clauses.append("EXISTS { MATCH (parent)<-[:OWNS]-(:User {uid: $owner_uid}) }")
            scope_clauses.append("coalesce(parent.private, false) = false")
            params["owner_uid"] = owner_uid
        # Parent-facet scope on the owning Entity — mirrors the list-vs-scalar
        # membership `_search_raw_mixin` applies to entity property filters, so
        # `nous` (array) and scalar facets behave identically across both paths.
        if parent_filters:
            for field, value in parent_filters.items():
                pname = f"pf_{field}"
                if isinstance(value, list):
                    scope_clauses.append(f"parent.{field} = ${pname}")
                else:
                    scope_clauses.append(
                        f"(CASE WHEN parent.{field} IS :: LIST<ANY> "
                        f"THEN ${pname} IN parent.{field} "
                        f"ELSE parent.{field} = ${pname} END)"
                    )
                params[pname] = value
        if scope_clauses:
            parts.append("WHERE " + " AND ".join(scope_clauses))
        metadata_return = ",\n            parent.metadata as parent_metadata" if owner_uid else ""
        parts.append(
            f"""RETURN
            chunk.uid as chunk_uid,
            chunk.chunk_type as chunk_type,
            chunk.text as text,
            chunk.context_window as context_window,
            score as similarity_score,
            parent.uid as parent_uid,
            parent.title as parent_title,
            parent.entity_type as parent_entity_type{metadata_return}
        ORDER BY score DESC
        LIMIT $limit"""
        )
        cypher = "\n".join(parts)

        # Escalate the candidate pool until `limit` in-scope chunks survive the
        # scope filter (unscoped → single 2x pass, unchanged). Each pass is a
        # strict superset of the last, so the final result stands alone.
        scoped = bool(parent_filters or owner_uid)
        schedule = _SCOPED_CANDIDATE_SCHEDULE if scoped else (2,)
        # boundary: query_executor returns dict rows; the Cypher's RETURN
        # clause matches SemanticSearchChunkResult by construction.
        last: Result[list[Any]] = Result.ok([])
        for multiplier in schedule:
            params["candidate_limit"] = limit * multiplier
            last = await self._executor.execute_query(cypher, params)
            if last.is_error or len(last.value) >= limit:
                break
        if scoped and last.is_ok:
            # Growth tripwire: when the ceiling pass still under-fills, the
            # corpus has outgrown the schedule — time for pre-filtered search.
            logger.debug(
                "Scoped chunk search: %d candidates → %d in-scope (limit=%d)",
                params["candidate_limit"],
                len(last.value),
                limit,
            )
        return cast("Result[list[SemanticSearchChunkResult]]", last)

    async def get_learning_states_batch(
        self, user_uid: str, ku_uids: list[str]
    ) -> Result[list[dict[str, Any]]]:
        """Batch fetch learning states (VIEWED/IN_PROGRESS/MASTERED) for KU UIDs."""
        return await self._executor.execute_query(
            """
            UNWIND $ku_uids as ku_uid
            MATCH (ku:Entity {uid: ku_uid})
            MATCH (u:User {uid: $user_uid})
            OPTIONAL MATCH (u)-[v:VIEWED]->(ku)
            OPTIONAL MATCH (u)-[p:IN_PROGRESS]->(ku)
            OPTIONAL MATCH (u)-[m:MASTERED]->(ku)
            RETURN
                ku.uid as ku_uid,
                v IS NOT NULL as has_viewed,
                p IS NOT NULL as has_in_progress,
                m IS NOT NULL as has_mastered
            """,
            {"user_uid": user_uid, "ku_uids": ku_uids},
        )
