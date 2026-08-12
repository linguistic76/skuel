"""Curriculum core backends: Ku, PathStep, LearningPath.

The Exercise/RevisedExercise/EntryReport trio lives in ``exercise_backends.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from adapters.persistence.neo4j._adaptive_mixin import _AdaptiveMixin
from adapters.persistence.neo4j._knowledge_context_mixin import _KnowledgeContextMixin
from adapters.persistence.neo4j._learning_state_mixin import _LearningStateMixin
from adapters.persistence.neo4j._lp_intelligence_mixin import _LpIntelligenceMixin
from adapters.persistence.neo4j._lp_progress_mixin import _LpProgressMixin
from adapters.persistence.neo4j._lp_step_mixin import _LpStepMixin
from adapters.persistence.neo4j._organizes_mixin import _OrganizesMixin
from adapters.persistence.neo4j._semantic_mixin import _SemanticMixin
from adapters.persistence.neo4j.query.cypher import (
    build_knowledge_read_clause,
    build_publication_clause,
)
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.constants import KnowledgeHealth
from core.models.enums.entity_enums import EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.enums.user_entry_enums import ExerciseScope
from core.models.ku.ku import Ku
from core.models.pathways.learning_path import LearningPath
from core.models.pathways.path_step import PathStep
from core.models.relationship_names import RelationshipName
from core.models.type_hints import Neo4jProperties, UserUID
from core.ports.query_types import (
    KnowledgeHealthRaw,
    KnowledgeOrphanKu,
    PsDeleteStepRow,
    PsEngagementCountsRow,
    PsKnowledgeSummaryResult,
)
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from datetime import date

    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
    from core.models.forms.form_template import FormTemplate  # noqa: F401
    from core.models.group.group import Group  # noqa: F401
    from core.models.interaction.interaction import Interaction  # noqa: F401
    from core.models.report_schedule import ReportSchedule  # noqa: F401
    from core.models.resource.resource import Resource  # noqa: F401


def _nous_subtopic_pairs_query(label: NeoLabel) -> tuple[str, dict[str, str]]:
    """Distinct co-occurring (nous, nous_subtopic) pairs on a single node label.

    Pairing is CO-OCCURRENCE: a (topic, sub-topic) pair exists once ≥1 entity
    carries both, so the dropdown follows wherever the content actually connects
    them — every offered pair has at least one matching entity. The two
    frontmatter lists are fully independent (any lengths, any combination);
    there is deliberately NO alignment/equal-length authoring contract (Mike's
    ruling, 2026-07-16: the design goes where whatever there is to share leads —
    no false restrictions).

    Each caller stays scoped to its OWN label; the cross-domain merge is a
    service-layer concern (`SearchRouter.nous_subtopic_map`), never a
    multi-label MATCH here.

    Args:
        label: The node label to scan. Typed ``NeoLabel`` rather than ``str``
            because SKUEL030 cannot see through the interpolation — the enum is
            what keeps an unknown label (which Neo4j answers with zero rows
            instead of an error) from reaching the graph.
    """
    published, published_params = build_publication_clause("n")
    return (
        f"""
        MATCH (n:{label.value})
        WHERE n.nous IS NOT NULL AND n.nous_subtopic IS NOT NULL AND {published}
        UNWIND n.nous AS nous
        UNWIND n.nous_subtopic AS subtopic
        RETURN DISTINCT nous, subtopic
        ORDER BY nous, subtopic
        """,
        published_params,
    )


class KuBackend(UniversalNeo4jBackend[Ku]):
    """Domain backend for atomic Knowledge Unit entities.

    Lightweight reference nodes with reverse-traversal methods:
    - get_path_steps_using(ku_uid) — PathSteps that USES_KU this Ku
    """

    async def get_path_steps_using(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get all PathSteps that use this atomic Ku via USES_KU."""
        query = """
        MATCH (ps:Entity)-[:USES_KU]->(ku:Entity {uid: $ku_uid})
        RETURN ps.uid AS uid, ps.title AS title,
               ps.description AS description
        ORDER BY ps.title
        """
        result = await self.execute_query(query, {"ku_uid": ku_uid})
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def get_cited_resources(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get the curated Resources this Ku cites via CITES_RESOURCE.

        Focused traversal on the Ku backend (the entity-agnostic
        ``_KnowledgeContextMixin.get_cited_resources`` is PS-oriented and not
        mixed into this lightweight backend). Rows carry a ``resource`` map plus
        the edge's ``locator`` free-string anchor (null for whole-work
        citations); the service flattens them for the shared resource chip.
        """
        query = """
        MATCH (source:Entity {uid: $ku_uid})-[cite:CITES_RESOURCE]->(r:Resource)
        RETURN r {.*} AS resource, cite.locator AS locator
        ORDER BY r.title
        """
        result = await self.execute_query(query, {"ku_uid": ku_uid})
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def get_usage_summary(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Count path steps using (USES_KU), training (TRAINS_KU), and organized children."""
        query = """
        MATCH (ku:Entity:Ku {uid: $ku_uid})
        OPTIONAL MATCH (uses:Entity)-[:USES_KU]->(ku)
        OPTIONAL MATCH (trains:Entity)-[:TRAINS_KU]->(ku)
        OPTIONAL MATCH (ku)-[:ORGANIZES]->(child:Entity)
        RETURN count(DISTINCT uses) as path_steps_using,
               count(DISTINCT trains) as path_steps_training,
               count(DISTINCT child) as organized_children
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    async def is_trained(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Check if any PathStep trains this Ku via TRAINS_KU."""
        query = """
        MATCH (ps:Entity)-[:TRAINS_KU]->(ku:Entity:Ku {uid: $ku_uid})
        RETURN count(ps) > 0 as trained
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    async def is_organized(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Check if this Ku has ORGANIZES children (acts as MOC)."""
        query = """
        MATCH (ku:Entity:Ku {uid: $ku_uid})-[:ORGANIZES]->(child:Entity)
        RETURN count(child) > 0 as organized
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    async def get_organization_depth(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get depth of the ORGANIZES tree below this Ku."""
        query = """
        MATCH path = (ku:Entity:Ku {uid: $ku_uid})-[:ORGANIZES*]->(descendant:Entity)
        RETURN max(length(path)) as max_depth
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    async def search_by_alias(self, alias: str) -> Result[list[Neo4jProperties]]:
        """Search Kus by alias (case-insensitive substring)."""
        # Discovery: a SEARCH over the whole Ku corpus — the same class as the
        # five text/graph/array strategies #1006 gated via
        # build_search_visibility_clause. NULL-tolerant.
        published, published_params = build_publication_clause("ku")
        query = f"""
        MATCH (ku:Entity:Ku)
        WHERE any(a IN ku.aliases WHERE toLower(a) CONTAINS toLower($alias))
          AND {published}
        RETURN ku
        ORDER BY ku.title ASC
        """
        return await self.execute_query(query, {"alias": alias, **published_params})

    async def nous_subtopic_pairs(self) -> Result[list[Neo4jProperties]]:
        """Distinct co-occurring (nous, nous_subtopic) pairs on this Ku's own label.

        The Ku contribution to the dependent nous→sub-topic /search dropdown.
        Scoped to `:Ku` only — cross-domain aggregation (folding in the PathStep
        contribution) belongs in the service layer, NOT the persistence layer
        (`SearchRouter.nous_subtopic_map` merges this with `PsBackend`'s pairs).
        Graph-derived so it can't drift from the vault vocabulary (content
        boundary — the taxonomy lives in the vault, never in the repo).

        See ``_nous_subtopic_pairs_query`` for the co-occurrence semantics.
        Returns rows with ``nous`` + ``subtopic`` keys.
        """
        return await self.execute_query(*_nous_subtopic_pairs_query(NeoLabel.KU))

    # ========================================================================
    # SUBSTANCE METRICS
    # ========================================================================

    async def batch_increment_substance(
        self,
        ku_uids: list[str],
        metric: str,
        timestamp_field: str,
        timestamp_str: str,
    ) -> Result[int]:
        """Atomically increment a substance metric for multiple KUs and connected PathSteps."""
        query = f"""
        UNWIND $ku_uids AS ku_uid
        MATCH (ku:Entity {{uid: ku_uid}})
        SET ku.{metric} = COALESCE(ku.{metric}, 0) + 1,
            ku.{timestamp_field} = datetime($timestamp),
            ku._substance_cache_timestamp = NULL
        WITH ku
        OPTIONAL MATCH (ps:PathStep)-[:USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU|TRAINS_KU]->(ku)
        WITH ps WHERE ps IS NOT NULL
        SET ps.{metric} = COALESCE(ps.{metric}, 0) + 1,
            ps.{timestamp_field} = datetime($timestamp),
            ps._substance_cache_timestamp = NULL
        RETURN count(ps) as updated_count
        """
        result = await self.execute_query(query, {"ku_uids": ku_uids, "timestamp": timestamp_str})
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        return Result.ok(records[0]["updated_count"] if records else 0)

    async def increment_substance(
        self,
        ku_uid: str,
        metric: str,
        timestamp_field: str,
        timestamp_str: str,
    ) -> Result[int]:
        """Atomically increment a substance metric for a single KU and connected PathSteps."""
        query = f"""
        MATCH (ku:Entity {{uid: $ku_uid}})
        SET ku.{metric} = COALESCE(ku.{metric}, 0) + 1,
            ku.{timestamp_field} = datetime($timestamp),
            ku._substance_cache_timestamp = NULL
        WITH ku
        OPTIONAL MATCH (ps:PathStep)-[:USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU|TRAINS_KU]->(ku)
        WITH ku, ps WHERE ps IS NOT NULL
        SET ps.{metric} = COALESCE(ps.{metric}, 0) + 1,
            ps.{timestamp_field} = datetime($timestamp),
            ps._substance_cache_timestamp = NULL
        RETURN ku.{metric} as new_count
        """
        result = await self.execute_query(query, {"ku_uid": ku_uid, "timestamp": timestamp_str})
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        return Result.ok(records[0]["new_count"] if records else 0)

    # ========================================================================
    # KU RELATIONSHIP QUERIES (migrated from ku_relationships.py helpers)
    # ========================================================================

    async def get_related_knowledge_uids(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get related knowledge units (RELATED_TO relationship)."""
        query = """
        MATCH (ku:Entity {uid: $ku_uid})-[:RELATED_TO]-(related:Entity)
        RETURN related.uid as uid
        LIMIT 50
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    async def get_broader_concept_uids(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get broader concepts (HAS_BROADER relationship)."""
        query = """
        MATCH (ku:Entity {uid: $ku_uid})-[:HAS_BROADER]->(broader:Entity)
        RETURN broader.uid as uid
        LIMIT 20
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    async def get_narrower_concept_uids(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get narrower concepts (HAS_NARROWER relationship)."""
        query = """
        MATCH (ku:Entity {uid: $ku_uid})-[:HAS_NARROWER]->(narrower:Entity)
        RETURN narrower.uid as uid
        LIMIT 50
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    async def get_learning_path_uids(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get learning paths containing this KU.

        Both arms of the old ``CONTAINS_KNOWLEDGE|INCLUDES_KNOWLEDGE`` alternation
        were wrong at this endpoint. ``INCLUDES_KNOWLEDGE`` is not a
        ``RelationshipName`` member at all, and ``CONTAINS_KNOWLEDGE`` is a
        PathStep→Ku edge, not a LearningPath→Ku one — so the query named a
        relationship pair the graph cannot hold (findings §8). A path reaches a Ku
        through its PathSteps, or directly via its ``required_knowledge``
        prerequisites.
        """
        # Discovery: a KU in hand surfaces the PATHS that reach it — curriculum
        # the caller never referenced. Gated by construction even though this
        # method currently has no caller: an ungated discovery query is a trap
        # for whoever wires it up. NULL-tolerant (#1006).
        # Discovery: a KU in hand surfaces the PATHS that reach it — curriculum
        # the caller never referenced. Gated by construction even though this
        # method currently has no caller: an ungated discovery query is a trap
        # for whoever wires it up. NULL-tolerant (#1006).
        #
        # The two arms are gated DIFFERENTLY, and deliberately (Codex P2, #1008).
        # The HAS_STEP arm's claim is carried by the bridging step, so that step
        # must be published too — the third of three KU→path surfaces, and the
        # one that hid the pattern because its step was an anonymous `(:Entity)`.
        # The REQUIRES_KNOWLEDGE arm has no bridge: the path states the
        # prerequisite itself, so only `lp` gates there.
        published_lp, lp_params = build_publication_clause("lp")
        published_step, step_params = build_publication_clause("step")
        query = f"""
        MATCH (ku:Entity {{uid: $ku_uid}})
        MATCH (lp:LearningPath)
        WHERE ((lp)-[:REQUIRES_KNOWLEDGE]->(ku)
           OR EXISTS {{
                 MATCH (lp)-[:HAS_STEP]->(step:Entity)
                       -[:USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU]->(ku)
                 WHERE {published_step}
               }})
          AND {published_lp}
        RETURN lp.uid as uid
        LIMIT 50
        """
        return await self.execute_query(query, {"ku_uid": ku_uid, **lp_params, **step_params})

    async def get_applying_task_uids(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get tasks applying this knowledge."""
        query = """
        MATCH (task:Task)-[:APPLIES_KNOWLEDGE]->(ku:Entity {uid: $ku_uid})
        RETURN task.uid as uid
        LIMIT 100
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    async def get_practicing_event_uids(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get events applying (practicing) this knowledge via APPLIES_KNOWLEDGE."""
        query = """
        MATCH (event:Event)-[:APPLIES_KNOWLEDGE]->(ku:Entity {uid: $ku_uid})
        RETURN event.uid as uid
        LIMIT 100
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    async def get_reinforcing_habit_uids(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get habits reinforcing this knowledge."""
        query = """
        MATCH (habit:Habit)-[:APPLIES_KNOWLEDGE|REINFORCES_KNOWLEDGE]->(ku:Entity {uid: $ku_uid})
        RETURN habit.uid as uid
        LIMIT 100
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    # ========================================================================
    # PREREQUISITE & DEPENDENCY QUERIES (migrated from ContextRetriever)
    # ========================================================================

    async def get_unmastered_prerequisites(
        self, ku_uid: str, user_uid: UserUID
    ) -> Result[list[Neo4jProperties]]:
        """Get unmastered prerequisites for a knowledge unit (depth 1..3).

        Traverses REQUIRES_KNOWLEDGE chains up to 3 hops, filtering out
        prerequisites the user has already MASTERED.

        Returns:
            Single record with 'prerequisites' key containing list of
            {uid, title} dicts.
        """
        query = """
        MATCH (ku:Entity {uid: $ku_uid})
        OPTIONAL MATCH (ku)-[:REQUIRES_KNOWLEDGE*1..3]->(prereq:Entity)
        WHERE NOT EXISTS {
            MATCH (u:User {uid: $user_uid})-[:MASTERED]->(prereq)
        }
        RETURN collect(DISTINCT {uid: prereq.uid, title: prereq.title}) AS prerequisites
        """
        return await self.execute_query(query, {"ku_uid": ku_uid, "user_uid": user_uid})

    async def count_dependents(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Count entities that depend on this knowledge unit via REQUIRES_KNOWLEDGE.

        Returns:
            Single record with 'unlocks_count' key.
        """
        query = """
        MATCH (ku:Entity {uid: $ku_uid})<-[:REQUIRES_KNOWLEDGE]-(dependent:Entity)
        RETURN count(DISTINCT dependent) AS unlocks_count
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    # ========================================================================
    # LEARNING STATE (Ku-native — two-tier: Studying + Understood)
    # ========================================================================

    async def mark_in_progress(
        self, user_uid: UserUID, ku_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Mark a Ku as actively being studied (IN_PROGRESS relationship)."""
        query = """
        MATCH (user:User {uid: $user_uid})
        MATCH (ku:Entity:Ku {uid: $ku_uid})
        MERGE (user)-[r:IN_PROGRESS]->(ku)
        ON CREATE SET
            r.started_at = datetime(),
            r.last_activity_at = datetime(),
            r.progress_score = 0.0
        ON MATCH SET
            r.last_activity_at = datetime()
        RETURN ku.uid AS uid
        """
        return await self.execute_query(query, {"user_uid": user_uid, "ku_uid": ku_uid})

    async def mark_mastered(
        self,
        user_uid: UserUID,
        ku_uid: str,
        mastery_score: float = 0.7,
        method: str = "self_report",
    ) -> Result[list[Neo4jProperties]]:
        """Mark a Ku as understood/mastered by the user."""
        query = """
        MATCH (user:User {uid: $user_uid})
        MATCH (ku:Entity:Ku {uid: $ku_uid})
        MERGE (user)-[r:MASTERED]->(ku)
        ON CREATE SET
            r.mastered_at = datetime(),
            r.mastery_score = $mastery_score,
            r.confidence = $mastery_score,
            r.method = $method
        ON MATCH SET
            r.mastery_score = CASE
                WHEN $mastery_score > r.mastery_score THEN $mastery_score
                ELSE r.mastery_score
            END,
            r.confidence = CASE
                WHEN $mastery_score > coalesce(r.confidence, 0) THEN $mastery_score
                ELSE r.confidence
            END,
            r.method = $method
        RETURN ku.uid AS uid
        """
        return await self.execute_query(
            query,
            {
                "user_uid": user_uid,
                "ku_uid": ku_uid,
                "mastery_score": mastery_score,
                "method": method,
            },
        )

    async def get_ku_learning_state(
        self, user_uid: UserUID, ku_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Get user's learning state for a Ku (IN_PROGRESS, MASTERED, MARKED_AS_READ)."""
        query = """
        MATCH (ku:Entity:Ku {uid: $ku_uid})
        OPTIONAL MATCH (u:User {uid: $user_uid})-[p:IN_PROGRESS]->(ku)
        OPTIONAL MATCH (u2:User {uid: $user_uid})-[m:MASTERED]->(ku)
        OPTIONAL MATCH (u3:User {uid: $user_uid})-[mr:MARKED_AS_READ]->(ku)
        RETURN
            p IS NOT NULL AS is_studying,
            m IS NOT NULL AS is_understood,
            mr IS NOT NULL AS is_marked_as_read
        """
        return await self.execute_query(query, {"user_uid": user_uid, "ku_uid": ku_uid})

    async def count_studying_kus(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Count Kus the user has marked as studying (IN_PROGRESS or MARKED_AS_READ)."""
        query = """
        MATCH (u:User {uid: $user_uid})-[:IN_PROGRESS|MARKED_AS_READ]->(ku:Entity:Ku)
        RETURN count(ku) AS cnt
        """
        return await self.execute_query(query, {"user_uid": user_uid})

    async def get_user_learning_states(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Get all Kus with their learning state for a user."""
        query = """
        MATCH (ku:Entity:Ku)
        WHERE EXISTS { (u:User {uid: $user_uid})-[:IN_PROGRESS|MASTERED|MARKED_AS_READ]->(ku) }
        OPTIONAL MATCH (u:User {uid: $user_uid})-[p:IN_PROGRESS]->(ku)
        OPTIONAL MATCH (u2:User {uid: $user_uid})-[m:MASTERED]->(ku)
        OPTIONAL MATCH (u3:User {uid: $user_uid})-[mr:MARKED_AS_READ]->(ku)
        RETURN ku.uid AS uid, ku.title AS title,
               (p IS NOT NULL OR mr IS NOT NULL) AS is_studying,
               m IS NOT NULL AS is_understood
        ORDER BY ku.title ASC
        """
        return await self.execute_query(query, {"user_uid": user_uid})


_ENGAGEMENT_EDGES = "|".join(
    (
        RelationshipName.IN_PROGRESS,
        RelationshipName.MASTERED,
        RelationshipName.MARKED_AS_READ,
    )
)
"""THE definition of "curriculum this learner has taken up".

Curriculum is OWNERLESS — KU/PS/LP are SHARED, so no curriculum node carries a
``user_uid`` and no property predicate can express "this learner's knowledge".
The learner's set is the one they wrote themselves, as EDGES.

Same three edges ``KuBackend.get_user_learning_states`` already calls a learning
state, so the vocabulary keeps one definition. VIEWED and BOOKMARKED are
deliberately OUT: a glance and a save-for-later are not uptake, and counting
them would inflate the denominator of every substance average with material the
learner never worked.
"""

_ENGAGED_AT = "coalesce(r.last_activity_at, r.mastered_at, r.marked_at, r.started_at)"
"""When the learner last touched the step, across the three engagement edges.

Each edge type stamps its own field (``mark_in_progress`` writes
``last_activity_at``, ``mark_mastered`` writes ``mastered_at``, ``mark_as_read``
writes ``marked_at``), so a single field name would silently window out two
thirds of the engagement set.
"""


class PsBackend(
    _OrganizesMixin,
    _LearningStateMixin,
    _SemanticMixin,
    _KnowledgeContextMixin,
    _AdaptiveMixin,
    UniversalNeo4jBackend[PathStep],
):
    """Domain backend for PathStep entities.

    Extends UniversalNeo4jBackend[PathStep] with:
    - Knowledge relationship CRUD (CONTAINS_KNOWLEDGE / USES_KU edges)
    - KU completion progress tracking
    - ``_OrganizesMixin`` — ORGANIZES relationship management (12 methods)
    - ``_LearningStateMixin`` — user progress tracking: VIEWED, IN_PROGRESS,
      MASTERED, BOOKMARKED, MARKED_AS_READ (13 methods)
    - ``_SemanticMixin`` — semantic relationships + graph analysis (11 methods)
    - ``_KnowledgeContextMixin`` — context, discovery, readiness (17 methods)
    - ``_AdaptiveMixin`` — practice + adaptive mastery tracking (6 methods)
    """

    # ========================================================================
    # LEARNER ENGAGEMENT (analytics reads — see _ENGAGEMENT_EDGES)
    # ========================================================================

    async def find_engaged_path_steps_by_date_range(
        self,
        user_uid: UserUID,
        start_date: date,
        end_date: date,
        limit: int | None = None,
    ) -> Result[list[PathStep]]:
        """PathSteps this learner engaged with inside a date window.

        The window is keyed on the LEARNER's engagement timestamp, not the
        node's ``updated_at``: an author editing shared curriculum is not
        something the learner did, and this feeds a personal weekly summary
        alongside six per-user activity metrics.

        Collapsing the edges with ``max()`` is load-bearing — a step held by
        both IN_PROGRESS and MASTERED is ONE step, and without the aggregation
        it would be counted twice, inflating every total and skewing the
        substance average toward whatever the learner engaged with hardest.

        Publication gate: composed with the gate OFF, deliberately. Registered
        USER_STATE in ``scripts/publication_gate_registry.py`` — withholding a
        step the learner has already worked would rewrite their history rather
        than hide unfinished curriculum.

        Args:
            limit: Optional cap. Defaults to NONE — unbounded — because the sole
                caller aggregates the whole result (counts, bands, averages,
                domain split), and a truncated read there is not a shorter list
                but a WRONG total. The set is already bounded by what one
                learner engaged with in one window; a page size would have to be
                a deliberate choice by a caller that paginates, not a default
                that silently caps arithmetic.

        Returns:
            Result[list[PathStep]]: newest engagement first (may be empty).
        """
        knowledge_clause, params = build_knowledge_read_clause("ps", apply_publication_gate=False)
        limit_clause = "LIMIT $limit" if limit is not None else ""
        query = f"""
        MATCH (u:User {{uid: $user_uid}})-[r:{_ENGAGEMENT_EDGES}]->(ps:Entity:{NeoLabel.PATH_STEP})
        WHERE {knowledge_clause}
        WITH ps, max({_ENGAGED_AT}) AS engaged_at
        WHERE engaged_at IS NOT NULL
          AND date(left(toString(engaged_at), 10)) >= date($start_date)
          AND date(left(toString(engaged_at), 10)) <= date($end_date)
        RETURN ps
        ORDER BY engaged_at DESC
        {limit_clause}
        """
        params.update(
            {
                "user_uid": user_uid,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            }
        )
        if limit is not None:
            params["limit"] = limit
        return self._records_to_steps(await self.execute_query(query, params))

    async def count_engaged_path_steps(self, user_uid: UserUID) -> Result[PsEngagementCountsRow]:
        """How much curriculum this learner has taken up, and how much mastered.

        All-time — the curriculum-progress counterpart to
        ``find_engaged_path_steps_by_date_range``, which windows the same set.
        ``collect(type(r))`` groups per step first, so ``total`` counts steps
        rather than edges and ``mastered`` is a strict subset of it.

        Publication gate: OFF for the same USER_STATE reason as its sibling.

        ``$mastered_edge`` is a parameter rather than an interpolated literal:
        the edge types in the MATCH pattern sit in IDENTIFIER position and must
        be interpolated, but this one is a VALUE compared against ``type(r)``,
        and a value belongs in the parameter map (CYP003).
        """
        knowledge_clause, params = build_knowledge_read_clause("ps", apply_publication_gate=False)
        query = f"""
        MATCH (u:User {{uid: $user_uid}})-[r:{_ENGAGEMENT_EDGES}]->(ps:Entity:{NeoLabel.PATH_STEP})
        WHERE {knowledge_clause}
        WITH ps, collect(type(r)) AS rels
        RETURN count(ps) AS total,
               sum(CASE WHEN $mastered_edge IN rels THEN 1 ELSE 0 END) AS mastered
        """
        params["user_uid"] = user_uid
        params["mastered_edge"] = RelationshipName.MASTERED.value
        result = await self.execute_query(query, params)
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.ok(PsEngagementCountsRow(total=0, mastered=0))
        row = records[0]
        return Result.ok(
            PsEngagementCountsRow(
                total=int(row.get("total") or 0), mastered=int(row.get("mastered") or 0)
            )
        )

    async def nous_subtopic_pairs(self) -> Result[list[Neo4jProperties]]:
        """Distinct co-occurring (nous, nous_subtopic) pairs on this PathStep label.

        The PathStep contribution to the dependent nous→sub-topic /search
        dropdown. Scoped to `:PathStep` only — mirror of `KuBackend.nous_subtopic_pairs`
        (see ``_nous_subtopic_pairs_query`` for the co-occurrence semantics); the
        cross-domain merge lives in `SearchRouter.nous_subtopic_map`, not here.
        Graph-derived (content boundary).
        """
        return await self.execute_query(*_nous_subtopic_pairs_query(NeoLabel.PATH_STEP))

    # ========================================================================
    # STEP SEQUENCE (for attach_step_to_path)
    # ========================================================================

    async def get_next_step_sequence(self, path_uid: str) -> Result[int]:
        """Get the next available sequence number for a path's steps."""
        query = """
        MATCH (p:Entity {uid: $path_uid})-[r:HAS_STEP]->()
        RETURN coalesce(max(r.sequence), -1) + 1 as next_sequence
        """
        result = await self.execute_query(query, {"path_uid": path_uid})
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.ok(0)
        return Result.ok(result.value[0].get("next_sequence", 0))

    # ========================================================================
    # KNOWLEDGE RELATIONSHIPS (CONTAINS_KNOWLEDGE edges — written at ingestion)
    # ========================================================================

    async def get_knowledge_summary(self, ps_uid: str) -> Result[PsKnowledgeSummaryResult]:
        """Aggregate count and UIDs of knowledge in this step."""
        query = """
        MATCH (ps:Entity {uid: $ps_uid})
        OPTIONAL MATCH (ps)-[r:CONTAINS_KNOWLEDGE]->(ku:Entity)
        RETURN count(r) as count, collect(ku.uid) as uids
        """
        result = await self.execute_query(query, {"ps_uid": ps_uid})
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.ok({"count": 0, "uids": []})
        record = records[0]
        return Result.ok(
            {
                "count": record["count"],
                "uids": [uid for uid in record["uids"] if uid],
            }
        )

    # ========================================================================
    # KU COMPLETION PROGRESS TRACKING
    # ========================================================================

    async def get_ku_completion_progress(
        self, ps_uid: str, user_uid: UserUID
    ) -> Result[Neo4jProperties]:
        """Return total and mastered KU counts for PathStep progress calculation.

        Progress = mastered_kus / total_kus (via USES_KU + CONTAINS_KNOWLEDGE).

        Args:
            ps_uid: PathStep UID
            user_uid: User UID

        Returns:
            Result containing dict with total_kus and mastered_kus
        """
        query = """
        MATCH (ps:Entity {uid: $ps_uid})-[:USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU]->(ku:Entity)
        WITH collect(DISTINCT ku) as all_kus, count(DISTINCT ku) as total
        OPTIONAL MATCH (user:User {uid: $user_uid})-[:MASTERED]->(mastered:Entity)
        WHERE mastered IN all_kus
        RETURN total as total_kus, count(DISTINCT mastered) as mastered_kus
        """
        result = await self.execute_query(query, {"ps_uid": ps_uid, "user_uid": user_uid})
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.ok({"total_kus": 0, "mastered_kus": 0})
        record = result.value[0]
        return Result.ok(
            {
                "total_kus": record["total_kus"],
                "mastered_kus": record["mastered_kus"],
            }
        )

    # ========================================================================
    # KU → PATHSTEP LOOKUP (for progress tracking)
    # ========================================================================

    async def find_path_steps_for_ku(self, ku_uid: str) -> Result[list[str]]:
        """Find all PathStep UIDs that contain a given KU via USES_KU or CONTAINS_KNOWLEDGE."""
        query = """
        MATCH (ps:Entity:PathStep)-[:USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU]->(ku:Entity {uid: $ku_uid})
        RETURN ps.uid as ps_uid
        """
        result = await self.execute_query(query, {"ku_uid": ku_uid})
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["ps_uid"] for record in (result.value or [])])

    # ========================================================================
    # CORE CRUD QUERIES (migrated from PsCoreService)
    # ========================================================================

    async def create_step_node(
        self,
        params: dict[str, Any],
        has_knowledge: bool = False,
        path_uid: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """Create step node with conditional knowledge and path relationships."""
        query = """
        CREATE (s:Entity {
            uid: $uid,
            entity_type: 'path_step',
            title: $title,
            intent: $intent,
            description: $description,
            learning_path_uid: $learning_path_uid,
            sequence: $sequence,
            mastery_threshold: $mastery_threshold,
            current_mastery: $current_mastery,
            estimated_hours: $estimated_hours,
            step_difficulty: $step_difficulty,
            status: $status,
            completed: $completed,
            domain: $domain
        })
        """
        if has_knowledge:
            query += """
            WITH s
            UNWIND $knowledge_uids AS ku_uid
            MATCH (ku:Entity {uid: ku_uid})
            MERGE (s)-[r:CONTAINS_KNOWLEDGE]->(ku)
            ON CREATE SET r.created_at = datetime()
            """
        if path_uid:
            query += """
            WITH s
            MATCH (p:Entity {uid: $path_uid})
            MERGE (p)-[r:HAS_STEP]->(s)
            ON CREATE SET r.sequence = $sequence
            """
        query += """
        WITH s
        RETURN s
        """
        return await self.execute_query(query, params)

    @staticmethod
    def _step_with_knowledge_to_model(record: dict[str, Any]) -> PathStep:
        """Reconstruct a PathStep from an ``s, knowledge_uids`` record.

        Enum conversion (domain, status, step_difficulty) and type coercion are
        handled by the generic node mapper. Defaults are injected for required
        fields that older nodes may be missing (pre-schema writes).

        GRAPH-NATIVE: knowledge_uids come from a CONTAINS_KNOWLEDGE traversal,
        not node properties, so they are injected into the data dict.
        """
        from adapters.persistence.neo4j.neo4j_mapper import from_neo4j_node

        data: dict[str, Any] = dict(record["s"])
        data.setdefault("title", "Path Step")
        data.setdefault("intent", "Complete this path step")
        data.setdefault("mastery_threshold", 0.7)
        data.setdefault("current_mastery", 0.0)
        data.setdefault("estimated_hours", 1.0)
        data.setdefault("domain", "PERSONAL")
        data["knowledge_uids"] = [uid for uid in record["knowledge_uids"] if uid]
        return from_neo4j_node(data, PathStep)

    async def get_step_with_knowledge(self, uid: str) -> Result[PathStep | None]:
        """Get a step (with its CONTAINS_KNOWLEDGE UIDs) as a typed model, or None."""
        query = """
        MATCH (s:Entity {uid: $uid})
        OPTIONAL MATCH (s)-[r:CONTAINS_KNOWLEDGE]->(ku:Entity)
        RETURN s, collect(ku.uid) as knowledge_uids
        """
        result = await self.execute_query(query, {"uid": uid})
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.ok(None)
        return Result.ok(self._step_with_knowledge_to_model(records[0]))

    async def update_step_fields(
        self, _uid: str, set_clauses: list[str], params: dict[str, Any]
    ) -> Result[PathStep | None]:
        """Update step fields; return the updated step as a typed model (None if absent)."""
        query = f"""
        MATCH (s:Entity {{uid: $uid}})
        SET {", ".join(set_clauses)}
        WITH s
        OPTIONAL MATCH (s)-[:CONTAINS_KNOWLEDGE]->(ku:Entity)
        RETURN s, collect(ku.uid) as knowledge_uids
        """
        result = await self.execute_query(query, params)
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.ok(None)
        return Result.ok(self._step_with_knowledge_to_model(records[0]))

    async def delete_step_node(self, uid: str) -> Result[list[PsDeleteStepRow]]:
        """Delete a step node and return deletion count."""
        query = """
        MATCH (s:Entity {uid: $uid})
        DETACH DELETE s
        RETURN count(s) as deleted_count
        """
        return cast(
            "Result[list[PsDeleteStepRow]]",
            await self.execute_query(query, {"uid": uid}),
        )

    async def list_steps_raw(
        self,
        path_uid: str | None,
        limit: int,
        offset: int,
        order_field: str,
        order_direction: str,
        user_uid: UserUID | None = None,
    ) -> Result[list[PathStep]]:
        """List steps (with knowledge UIDs) as typed models, with pagination and filters.

        Withholds draft-marked steps: this is the PathStep CATALOGUE, an
        audience surface. Composes ``build_publication_clause`` rather than
        spelling the predicate out — one definition, NULL-tolerant so the
        pre-``publication_state`` corpus keeps listing.
        """
        published, published_params = build_publication_clause("s")
        predicates = [published]
        if user_uid:
            predicates.append("s.user_uid = $user_uid")
        where_clause = f"WHERE {' AND '.join(predicates)} "

        if path_uid:
            query = f"""
            MATCH (p:Entity {{uid: $path_uid}})-[:HAS_STEP]->(s:Entity {{entity_type: 'path_step'}})
            {where_clause}
            OPTIONAL MATCH (s)-[:CONTAINS_KNOWLEDGE]->(ku:Entity)
            WITH s, collect(ku.uid) as knowledge_uids
            RETURN s, knowledge_uids
            ORDER BY {order_field} {order_direction}
            SKIP $offset
            LIMIT $limit
            """
        else:
            query = f"""
            MATCH (s:Entity {{entity_type: 'path_step'}})
            {where_clause}
            OPTIONAL MATCH (s)-[:CONTAINS_KNOWLEDGE]->(ku:Entity)
            WITH s, collect(ku.uid) as knowledge_uids
            RETURN s, knowledge_uids
            ORDER BY {order_field} {order_direction}
            SKIP $offset
            LIMIT $limit
            """

        params: dict[str, Any] = {"limit": limit, "offset": offset, **published_params}
        if path_uid:
            params["path_uid"] = path_uid
        if user_uid:
            params["user_uid"] = user_uid

        result = await self.execute_query(query, params)
        if result.is_error:
            return Result.fail(result)
        return Result.ok(
            [self._step_with_knowledge_to_model(record) for record in (result.value or [])]
        )

    # ========================================================================
    # SEARCH QUERIES (migrated from PsSearchService)
    # ========================================================================

    def _records_to_steps(
        self, result: Result[list[dict[str, Any]]], node_key: str = "ps"
    ) -> Result[list[PathStep]]:
        """Convert raw PS node records to PathStep models (Tier 6: conversion
        lives below the hexagonal boundary — services receive typed models)."""
        from adapters.persistence.neo4j.neo4j_mapper import from_neo4j_node

        if result.is_error:
            return Result.fail(result)
        return Result.ok(
            [from_neo4j_node(record[node_key], PathStep) for record in (result.value or [])]
        )

    async def get_standalone_steps(self, limit: int = 50) -> Result[list[PathStep]]:
        """Get PathStep nodes not belonging to any learning path.

        Args:
            limit: Maximum results

        Returns:
            Result containing PathStep models
        """
        published, published_params = build_publication_clause("ps")
        # Discovery: an unanchored enumeration of every orphan step — a browse
        # surface, so draft-marked steps are withheld. NULL-tolerant (#1006).
        query = f"""
        MATCH (ps:Entity {{entity_type: 'path_step'}})
        WHERE NOT (ps)<-[:HAS_STEP]-(:Entity {{entity_type: 'learning_path'}})
          AND {published}
        RETURN ps
        ORDER BY ps.updated_at DESC
        LIMIT $limit
        """
        return self._records_to_steps(
            await self.execute_query(query, {"limit": limit, **published_params})
        )

    async def get_prioritized_steps(
        self, user_uid: UserUID, limit: int = 20
    ) -> Result[list[PathStep]]:
        """Get PathStep nodes prioritized by user context.

        Prioritization order: in-progress first, then by status, then by priority,
        then by recency.

        Args:
            user_uid: User UID for personalization
            limit: Maximum results

        Returns:
            Result containing PathStep models
        """
        # A MIXED surface (Codex P2, #1008): an unanchored enumeration of every
        # step (catalogue -> gated) that is also ordered by the user's own
        # progress (user-state -> NOT gated). The gate therefore lands AFTER the
        # progress match and yields to it: a step the learner already started is
        # one they reference, so withholding it would delete their own history
        # from the list that exists to prioritise it — and drafts are UNLISTED,
        # not forbidden (the get_visible_to_user carve-out). A step marked draft
        # after they began it stays visible to them and to no one else.
        published, published_params = build_publication_clause("ps")
        query = f"""
        MATCH (ps:Entity {{entity_type: 'path_step'}})
        OPTIONAL MATCH (u:User {{uid: $user_uid}})-[progress:IN_PROGRESS]->(ps)
        WITH ps, progress
        WHERE progress IS NOT NULL OR {published}
        RETURN ps, progress
        ORDER BY
            CASE
                WHEN progress IS NOT NULL THEN 0
                ELSE 1
            END,
            CASE ps.status
                WHEN 'in_progress' THEN 0
                WHEN 'not_started' THEN 1
                ELSE 2
            END,
            CASE ps.priority
                WHEN 'critical' THEN 0
                WHEN 'high' THEN 1
                WHEN 'medium' THEN 2
                WHEN 'low' THEN 3
                ELSE 4
            END,
            ps.updated_at DESC
        LIMIT $limit
        """
        return self._records_to_steps(
            await self.execute_query(
                query, {"user_uid": user_uid, "limit": limit, **published_params}
            )
        )


class LpBackend(
    _LpStepMixin,
    _LpProgressMixin,
    _LpIntelligenceMixin,
    UniversalNeo4jBackend[LearningPath],
):
    """Domain backend for LearningPath entities.

    Extends UniversalNeo4jBackend[LearningPath] with:
    - ``_LpStepMixin`` — step management CRUD + path CRUD + exercise traversal (15 methods)
    - ``_LpProgressMixin`` — KU mastery progress + search queries (6 methods)
    - ``_LpIntelligenceMixin`` — intelligence + adaptive learning + knowledge scope (10 methods)
    """


# ============================================================================
# KNOWLEDGE-HEALTH BACKEND (ADR-080 Horizon-1 structural-health gauge)
# ============================================================================

# Structural edge sets, built from canonical RelationshipName members (typo-proof;
# SKUEL013/030). Every metric scopes BOTH endpoints to knowledge nodes: DEPENDS_ON
# is also the live Task-dependency edge, and BLOCKS/RELATED_TO/… are lateral edges
# on all six activity domains, so an unscoped count would fold activity structure
# into a *knowledge* gauge.
_COMPOSITION_EDGES = "|".join(
    (
        RelationshipName.USES_KU.value,
        RelationshipName.CONTAINS_KNOWLEDGE.value,
        RelationshipName.TRAINS_KU.value,
    )
)
# Hard prerequisites only — ENABLES/ENABLED_BY (soft enablement) are reported
# separately so ``prerequisite_edge_count`` stays the DAG the ZPD reasons over.
# Used for the broad edge COUNT + COVERAGE (direction doesn't matter there).
# Includes REQUIRES_STEP — the PathStep→PathStep prerequisite edge ingestion writes
# from a step's ``prerequisite_step_uids`` and PS-readiness checks read; a corpus
# with authored PathStep prerequisites but no Ku PREREQUISITE_FOR would otherwise
# read as an empty DAG (Codex #770 P2).
_DAG_EDGES = "|".join(
    (
        RelationshipName.PREREQUISITE_FOR.value,
        RelationshipName.DEPENDS_ON.value,
        RelationshipName.REQUIRES_PREREQUISITE.value,
        RelationshipName.REQUIRES_STEP.value,
    )
)
# For the DEPTH walk, direction matters: PREREQUISITE_FOR points prereq→dependent,
# while DEPENDS_ON / REQUIRES_PREREQUISITE (its lateral auto-inverse) point
# dependent→prereq. Mixing them in one directed variable-length pattern lets an
# inverse pair (A-PREREQUISITE_FOR→B, B-REQUIRES_PREREQUISITE→A) form a 2-cycle
# that inflates depth to the cap. So depth is the max over TWO direction-coherent
# traversals, never one mixed pattern.
_DAG_FORWARD_EDGES = RelationshipName.PREREQUISITE_FOR.value
_DAG_INVERSE_EDGES = "|".join(
    (RelationshipName.DEPENDS_ON.value, RelationshipName.REQUIRES_PREREQUISITE.value)
)
# Learner-state / preference edges. A *structural* gauge must ignore these — user
# activity (viewing, mastering, bookmarking a Ku) is not authoring connectivity,
# and would otherwise raise avg/max degree and un-orphan an isolated Ku as usage
# grows. Degree and orphans are scoped to exclude them (Codex #770 P2).
_TELEMETRY_EDGE_LIST = "[{}]".format(
    ", ".join(
        f"'{rel.value}'"
        for rel in (
            RelationshipName.VIEWED,
            RelationshipName.IN_PROGRESS,
            RelationshipName.MASTERED,
            RelationshipName.MARKED_AS_READ,
            RelationshipName.BOOKMARKED,
            RelationshipName.INTERESTED_IN,
            RelationshipName.PINNED,
            RelationshipName.PINNED_TODAY,
        )
    )
)
# Semantic / associative / structural laterals (the "lateral relationships" the
# UI exposes), EXCLUDING the prerequisite pair (counted in the DAG) and the
# enablement pair (counted separately).
_LATERAL_EDGES = "|".join(
    (
        RelationshipName.RELATED_TO.value,
        RelationshipName.SIMILAR_TO.value,
        RelationshipName.COMPLEMENTARY_TO.value,
        RelationshipName.ALTERNATIVE_TO.value,
        RelationshipName.BLOCKS.value,
        RelationshipName.BLOCKED_BY.value,
        RelationshipName.RECOMMENDED_WITH.value,
        RelationshipName.STACKS_WITH.value,
        RelationshipName.SIBLING.value,
        RelationshipName.COUSIN.value,
    )
)
_ENABLEMENT_EDGES = "|".join(
    (RelationshipName.LATERAL_ENABLES.value, RelationshipName.LATERAL_ENABLED_BY.value)
)
# The gauge matches knowledge nodes by ``entity_type``, NOT by domain label:
# ``create_step_node`` (and other API-create paths) persist ``:Entity {entity_type:
# 'path_step'}`` WITHOUT the ``:PathStep`` label, and the rest of this file reads
# PathSteps the same entity_type way. Label-only matching would silently drop those
# legitimate steps from the corpus census and coverage (Codex #770 P2).
_KNOWLEDGE_ENTITY_TYPES = (
    EntityType.KU.value,
    EntityType.PATH_STEP.value,
    EntityType.LEARNING_PATH.value,
    EntityType.EXERCISE.value,
)


def _knowledge_node(var: str) -> str:
    """``(var.entity_type IN ['ku','path_step',…])`` — in the knowledge subgraph."""
    types = ", ".join(f"'{t}'" for t in _KNOWLEDGE_ENTITY_TYPES)
    return f"({var}.entity_type IN [{types}])"


# One round-trip corpus measurement. ``__TOKEN__`` placeholders are substituted
# (not f-string braces — the query is dense with map / count{} / exists{} literals
# that would need doubling). Nodes are matched by ``entity_type`` (not domain
# label — some are persisted label-less). Degree counts incident edges per Ku
# EXCLUDING learner-state telemetry (``__TELEMETRY__``) so the gauge stays
# structural as usage grows (reproduces the ADR-080 measure: avg ≈ 2.16, 17
# orphans); every specialized slice scopes both endpoints to knowledge nodes via
# ``__KA__``/``__KB__``/``__KO__``.
_KNOWLEDGE_HEALTH_QUERY_TEMPLATE = """
CALL () { MATCH (k:Entity {entity_type: __ET_KU__}) RETURN count(k) AS total_kus }
CALL () { MATCH (ps:Entity {entity_type: __ET_PS__}) RETURN count(ps) AS total_path_steps }
CALL () { MATCH (lp:Entity {entity_type: __ET_LP__}) RETURN count(lp) AS total_learning_paths }
CALL () { MATCH (ex:Entity {entity_type: __ET_EX__}) RETURN count(ex) AS total_exercises }
CALL () {
    MATCH (k:Entity {entity_type: __ET_KU__})
    WITH k, count{ (k)-[r]-() WHERE NOT type(r) IN __TELEMETRY__ } AS deg
    RETURN coalesce(round(avg(deg), 4), 0.0) AS avg_ku_degree,
           coalesce(max(deg), 0) AS max_ku_degree,
           count(CASE WHEN deg = 0 THEN 1 END) AS orphan_ku_count
}
CALL () {
    MATCH (k:Entity {entity_type: __ET_KU__})
    WHERE count{ (k)-[r]-() WHERE NOT type(r) IN __TELEMETRY__ } = 0
    WITH k ORDER BY k.uid
    RETURN collect({ uid: k.uid, title: coalesce(k.title, k.uid) }) AS orphan_kus
}
CALL () {
    RETURN count{ (:Entity {entity_type: __ET_PS__})-[:__COMPOSITION__]->(:Entity {entity_type: __ET_KU__}) }
        AS composition_edge_count
}
CALL () {
    MATCH (k:Entity {entity_type: __ET_KU__})
    WHERE exists{ (:Entity {entity_type: __ET_PS__})-[:__COMPOSITION__]->(k) }
    RETURN count(k) AS composed_ku_count
}
CALL () {
    RETURN count{ (a)-[:__DAG__]->(b) WHERE __KA__ AND __KB__ } AS prerequisite_edge_count
}
CALL () {
    MATCH (k:Entity {entity_type: __ET_KU__})
    WHERE exists{ (k)-[:__DAG__]-(o) WHERE __KO__ }
    RETURN count(k) AS dag_ku_count
}
CALL () {
    // Depth over the forward Ku prerequisite chain (PREREQUISITE_FOR: prereq→dependent).
    OPTIONAL MATCH fp = (a:Entity {entity_type: __ET_KU__})-[:__DAG_FWD__*1..__DEPTH__]->(b:Entity {entity_type: __ET_KU__})
    RETURN coalesce(max(length(fp)), 0) AS fwd_depth
}
CALL () {
    // Depth over the inverse-direction Ku chain (DEPENDS_ON/REQUIRES_PREREQUISITE:
    // dependent→prereq). Kept in a SEPARATE pattern from the forward walk so an
    // inverse pair cannot form a depth-inflating cycle.
    OPTIONAL MATCH bp = (a:Entity {entity_type: __ET_KU__})-[:__DAG_INV__*1..__DEPTH__]->(b:Entity {entity_type: __ET_KU__})
    RETURN coalesce(max(length(bp)), 0) AS inv_depth
}
CALL () {
    // Depth over PathStep prerequisite chains (REQUIRES_STEP: dependent step→prereq
    // step), a coherent direction of its own.
    OPTIONAL MATCH sp = (a:Entity {entity_type: __ET_PS__})-[:__REQUIRES_STEP__*1..__DEPTH__]->(b:Entity {entity_type: __ET_PS__})
    RETURN coalesce(max(length(sp)), 0) AS step_depth
}
CALL () {
    RETURN count{ (a)-[:__ORGANIZES__]->(b) WHERE __KA__ AND __KB__ } AS organizes_edge_count
}
CALL () {
    MATCH (k:Entity {entity_type: __ET_KU__})
    WHERE exists{ (k)-[:__ORGANIZES__]-(o) WHERE __KO__ }
    RETURN count(k) AS organized_ku_count
}
CALL () {
    RETURN count{ (a)-[:__LATERAL__]->(b) WHERE __KA__ AND __KB__ } AS lateral_edge_count
}
CALL () {
    RETURN count{ (a)-[:__ENABLEMENT__]->(b) WHERE __KA__ AND __KB__ } AS enablement_edge_count
}
CALL () {
    // Practice coverage counts CURRICULUM-scoped exercises only: PERSONAL (and
    // ASSIGNED/ASSESSMENT) exercises dual-write the same HAS_EXERCISE edge, so an
    // unscoped check would count learner/teacher practice templates as corpus
    // authoring coverage and hide missing curriculum exercises.
    MATCH (ps:Entity {entity_type: __ET_PS__})
    WHERE exists{ (ps)-[:__HAS_EXERCISE__]->(ex:Entity {entity_type: __ET_EX__}) WHERE ex.scope = __CURRICULUM_SCOPE__ }
    RETURN count(ps) AS path_steps_with_exercise
}
CALL () {
    // Draft-marked curriculum (publication_state: draft) — COUNTED, not excluded.
    // This gauge is authoring guidance, so a draft's orphans and coverage gaps are
    // exactly what the author needs to see; silently dropping drafts would also
    // move the ADR-080 baseline. Learner-facing surfaces withhold drafts instead
    // (build_publication_clause). Reporting the count keeps the other totals
    // interpretable: "N of these are not published yet".
    MATCH (d:Entity)
    WHERE d.entity_type IN [__ET_KU__, __ET_PS__, __ET_LP__, __ET_EX__]
      AND d.publication_state = $publication_draft
    RETURN count(d) AS draft_curriculum_count
}
RETURN total_kus, total_path_steps, total_learning_paths, total_exercises,
       avg_ku_degree, max_ku_degree, orphan_ku_count, orphan_kus,
       composition_edge_count, composed_ku_count,
       prerequisite_edge_count, dag_ku_count,
       reduce(m = 0, x IN [fwd_depth, inv_depth, step_depth] | CASE WHEN x > m THEN x ELSE m END)
           AS dag_max_depth,
       organizes_edge_count, organized_ku_count,
       lateral_edge_count, enablement_edge_count, path_steps_with_exercise,
       draft_curriculum_count
"""


def _build_knowledge_health_query() -> str:
    """Substitute the structural edge sets, knowledge-node predicates, and depth
    cap into the corpus query. Built once at import time."""
    query = _KNOWLEDGE_HEALTH_QUERY_TEMPLATE
    substitutions = {
        "__COMPOSITION__": _COMPOSITION_EDGES,
        # Order matters: replace the longer __DAG_* tokens before __DAG__.
        "__DAG_FWD__": _DAG_FORWARD_EDGES,
        "__DAG_INV__": _DAG_INVERSE_EDGES,
        "__DAG__": _DAG_EDGES,
        "__ORGANIZES__": RelationshipName.ORGANIZES.value,
        "__LATERAL__": _LATERAL_EDGES,
        "__ENABLEMENT__": _ENABLEMENT_EDGES,
        "__REQUIRES_STEP__": RelationshipName.REQUIRES_STEP.value,
        "__HAS_EXERCISE__": RelationshipName.HAS_EXERCISE.value,
        "__CURRICULUM_SCOPE__": f"'{ExerciseScope.CURRICULUM.value}'",
        "__TELEMETRY__": _TELEMETRY_EDGE_LIST,
        "__DEPTH__": str(KnowledgeHealth.PREREQUISITE_DEPTH_CAP),
        "__ET_KU__": f"'{EntityType.KU.value}'",
        "__ET_PS__": f"'{EntityType.PATH_STEP.value}'",
        "__ET_LP__": f"'{EntityType.LEARNING_PATH.value}'",
        "__ET_EX__": f"'{EntityType.EXERCISE.value}'",
        "__KA__": _knowledge_node("a"),
        "__KB__": _knowledge_node("b"),
        "__KO__": _knowledge_node("o"),
    }
    for token, value in substitutions.items():
        query = query.replace(token, value)
    return query


_KNOWLEDGE_HEALTH_QUERY = _build_knowledge_health_query()
# Sourced from build_publication_clause so the draft vocabulary has ONE definition.
_KNOWLEDGE_HEALTH_PARAMS: dict[str, str] = build_publication_clause("d")[1]

_EMPTY_KNOWLEDGE_HEALTH_RAW: KnowledgeHealthRaw = {
    "total_kus": 0,
    "total_path_steps": 0,
    "total_learning_paths": 0,
    "total_exercises": 0,
    "avg_ku_degree": 0.0,
    "max_ku_degree": 0,
    "orphan_ku_count": 0,
    "orphan_kus": [],
    "composition_edge_count": 0,
    "composed_ku_count": 0,
    "prerequisite_edge_count": 0,
    "dag_ku_count": 0,
    "dag_max_depth": 0,
    "organizes_edge_count": 0,
    "organized_ku_count": 0,
    "lateral_edge_count": 0,
    "enablement_edge_count": 0,
    "path_steps_with_exercise": 0,
    "draft_curriculum_count": 0,
}


class KnowledgeHealthBackend:
    """Read-only corpus-level structural measurement over the knowledge subgraph.

    Executor-based (like ``CrossDomainBackend``) rather than a
    ``UniversalNeo4jBackend[T]`` subclass: this gauge spans all four curriculum
    labels (Ku / PathStep / LearningPath / Exercise) at once, so the
    single-entity-type model does not fit. One round-trip yields the raw
    structural facts — node counts, Ku degree distribution (incident edges minus
    learner-state telemetry), the orphan-Ku list, and composition /
    prerequisite-DAG / ORGANIZES / lateral / practice coverage.
    ``KnowledgeHealthService`` derives coverage ratios, the composite
    GDS-readiness score, and the authoring flags from these facts (ADR-080 H1).
    """

    def __init__(self, executor: "Neo4jQueryExecutor") -> None:
        self.executor = executor
        self.logger = get_logger("skuel.backends.knowledge_health")

    async def measure_knowledge_subgraph(self) -> Result[KnowledgeHealthRaw]:
        """Measure the knowledge subgraph's raw structural facts in one query.

        Backend: the corpus query scopes every specialized metric to knowledge
        nodes; degree/orphans count incident edges minus learner-state telemetry.
        An empty graph yields the all-zeros shape, not an error.
        """
        result = await self.executor.execute_query(
            _KNOWLEDGE_HEALTH_QUERY, _KNOWLEDGE_HEALTH_PARAMS
        )
        if result.is_error:
            return Result.fail(result)
        rows = result.value or []
        if not rows:
            # Defensive: the aggregating query always returns exactly one row, so
            # this is essentially unreachable. Read-only constant, never mutated.
            return Result.ok(_EMPTY_KNOWLEDGE_HEALTH_RAW)
        row = rows[0]
        orphan_kus: list[KnowledgeOrphanKu] = [
            {"uid": str(entry["uid"]), "title": str(entry["title"])}
            for entry in (row.get("orphan_kus") or [])
        ]
        return Result.ok(
            KnowledgeHealthRaw(
                total_kus=int(row["total_kus"]),
                total_path_steps=int(row["total_path_steps"]),
                total_learning_paths=int(row["total_learning_paths"]),
                total_exercises=int(row["total_exercises"]),
                avg_ku_degree=float(row["avg_ku_degree"]),
                max_ku_degree=int(row["max_ku_degree"]),
                orphan_ku_count=int(row["orphan_ku_count"]),
                orphan_kus=orphan_kus,
                composition_edge_count=int(row["composition_edge_count"]),
                composed_ku_count=int(row["composed_ku_count"]),
                prerequisite_edge_count=int(row["prerequisite_edge_count"]),
                dag_ku_count=int(row["dag_ku_count"]),
                dag_max_depth=int(row["dag_max_depth"]),
                organizes_edge_count=int(row["organizes_edge_count"]),
                organized_ku_count=int(row["organized_ku_count"]),
                lateral_edge_count=int(row["lateral_edge_count"]),
                enablement_edge_count=int(row["enablement_edge_count"]),
                path_steps_with_exercise=int(row["path_steps_with_exercise"]),
                draft_curriculum_count=int(row["draft_curriculum_count"]),
            )
        )
