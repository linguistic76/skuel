"""
KuService - Atomic Knowledge Unit Facade
==========================================

Facade for atomic Ku operations. Delegates to 4 sub-services via factory:
- .core: CRUD operations (KuCoreService)
- .search: Search and NOUS-topic queries (KuSearchService)
- .relationships: Graph relationship operations (UnifiedRelationshipService)
- .intelligence: Graph analytics (KuIntelligenceService)

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from core.models.type_hints import UserUID
from core.utils.logging import get_logger
from core.utils.neo4j_props import coerce_int
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from core.models.enums import MasteryLevel
    from core.models.graph_context import GraphContext
    from core.models.ku.ku import Ku
    from core.models.shared.dual_track import DualTrackResult
    from core.ports.curriculum_protocols import KuOperations
    from core.ports.query_types import KuUserSubstanceResult, NousSubtopicPair
    from core.services.ku.ku_intelligence_service import KuIntelligenceService
    from core.services.user import UserContext

logger = get_logger(__name__)


class KuService:
    """Facade for atomic Knowledge Unit operations.

    Ku is a lightweight ontology/reference node — a single definable thing:
    concept, state, principle, substance, practice, or value.

    Uses create_curriculum_sub_services() factory for consistent initialization,
    matching PS and Activity Domain patterns.
    """

    def __init__(
        self,
        backend: "KuOperations | None" = None,
        graph_intel: Any = None,
        event_bus: Any = None,
    ) -> None:
        if not backend:
            raise ValueError(
                "KuService backend is REQUIRED. "
                "SKUEL follows fail-fast architecture — all required dependencies "
                "must be provided at initialization."
            )
        if not graph_intel:
            raise ValueError(
                "KuService graph_intel is REQUIRED. "
                "SKUEL follows fail-fast architecture — graph intelligence enables "
                "cross-domain queries for curriculum domains."
            )

        from core.services.curriculum_domain_config import (
            CurriculumCommonSubServices,
            create_curriculum_sub_services,
        )

        common: CurriculumCommonSubServices[KuIntelligenceService] = create_curriculum_sub_services(
            domain="ku",
            backend=backend,
            graph_intel=graph_intel,
            event_bus=event_bus,
        )

        self.core = common.core
        # Sub-service ATTRIBUTE, not a delegation method — SearchRouter's
        # _get_search_service resolves `.search` to the sub-service only when
        # it is non-callable (same shape as PsService). A facade method here
        # would shadow it with a divergent signature.
        self.search = common.search
        self.relationships = common.relationships
        self.intelligence: KuIntelligenceService = common.intelligence
        self.backend: KuOperations = backend  # For get_path_steps() reverse traversal

        logger.debug("KuService facade initialized with 4 sub-services via factory")

    # =========================================================================
    # CRUD (delegated to core)
    # =========================================================================

    async def create_ku(
        self,
        title: str,
        aliases: list[str] | None = None,
        description: str | None = None,
        summary: str | None = None,
        domain: str | None = None,
        tags: list[str] | None = None,
    ) -> Result[Ku | None]:
        """Create a new atomic Knowledge Unit."""
        return await self.core.create_ku(
            title=title,
            aliases=aliases,
            description=description,
            summary=summary,
            domain=domain,
            tags=tags,
        )

    async def get_ku(self, uid: str) -> Result[Ku | None]:
        """Get a Knowledge Unit by UID."""
        return await self.core.get_ku(uid)

    async def get_with_content(self, uid: str) -> Result[tuple[Ku, str | None]]:
        """Get a Ku with its lesson body loaded from the :Content subtree.

        Backend: ``UniversalNeo4jBackend.get_content`` via the
        ``ContextOperationsMixin`` inline-first fallback — same recipe as
        PathStep (lesson bodies live on :Content nodes, ADR-074).
        """
        return await self.core.get_with_content(uid)

    async def get_kus_batch(self, uids: list[str]) -> Result[list[Any]]:
        """Get multiple Kus in one batched query.

        Backend: ``UniversalNeo4jBackend.get_many``. Sibling of
        ``PsService.get_steps_batch`` — the batch read a caller with a list of
        UIDs needs, so it never has to reach the backend through ``.core``.
        """
        return await self.core.backend.get_many(uids)

    # =========================================================================
    # SEARCH (sub-service at .search; extra delegations below)
    # =========================================================================

    async def search_by_alias(self, alias: str) -> Result[list[dict[str, Any]]]:
        """Search Kus by alias (alternative name)."""
        return await self.search.search_by_alias(alias)

    async def list_nous_topics(self) -> Result[list[str]]:
        """List the NOUS topic vocabulary — distinct `nous` values across all Kus.

        Derived from the graph, not hardcoded: the 11 anchor Kus self-assign
        their own topic, so the list is complete by construction (a topic
        exists iff its anchor Ku exists).
        """
        return await self.search.list_all_categories()

    async def nous_subtopic_pairs(self) -> Result[list[NousSubtopicPair]]:
        """This Ku label's (nous, nous_subtopic) co-occurrence pairs.

        The Ku contribution to the dependent /search sub-topic dropdown;
        `SearchRouter.nous_subtopic_map` merges it with the PathStep contribution
        (cross-domain aggregation stays in the search service, not a backend).
        Graph-derived (content boundary). Rows carry `nous` + `subtopic`.

        Backend: KuBackend.nous_subtopic_pairs via KuSearchService.
        """
        return await self.search.nous_subtopic_pairs()

    # =========================================================================
    # INTELLIGENCE (delegated to intelligence)
    # =========================================================================

    async def get_with_context(self, uid: str, depth: int = 2) -> Result[tuple[Ku, GraphContext]]:
        """Get Ku with full graph context."""
        return await self.intelligence.get_with_context(uid, depth)

    async def get_usage_summary(self, ku_uid: str) -> Result[dict[str, int]]:
        """Count path steps and organized children for a Ku."""
        return await self.intelligence.get_usage_summary(ku_uid)

    async def calculate_user_substance(
        self, ku_uid: str, user_context: UserContext
    ) -> Result[KuUserSubstanceResult]:
        """Calculate how much a user has applied this Ku's knowledge in their life.

        See: KuIntelligenceService.calculate_user_substance
        """
        return await self.intelligence.calculate_user_substance(ku_uid, user_context)

    async def assess_mastery_dual_track(
        self,
        user_uid: UserUID,
        ku_uid: str,
        user_level: MasteryLevel,
        user_evidence: str,
        user_context: UserContext,
        user_reflection: str | None = None,
        store_callback: (
            Callable[[str, DualTrackResult[MasteryLevel]], Awaitable[None]] | None
        ) = None,
    ) -> Result[DualTrackResult[MasteryLevel]]:
        """Dual-track mastery assessment for a Ku (ADR-030 — Knowledge dimension).

        See: KuIntelligenceService.assess_mastery_dual_track
        """
        return await self.intelligence.assess_mastery_dual_track(
            user_uid,
            ku_uid,
            user_level,
            user_evidence,
            user_context,
            user_reflection=user_reflection,
            store_callback=store_callback,
        )

    # =========================================================================
    # GRAPH (reverse traversal via backend)
    # =========================================================================

    async def get_path_steps(self, ku_uid: str) -> Result[list[dict[str, Any]]]:
        """Get all PathSteps that use this atomic Ku via USES_KU."""
        if self.backend is None:
            return Result.fail(
                Errors.system("KuService backend not configured for graph operations")
            )
        return await self.backend.get_path_steps_using(ku_uid)

    async def get_cited_resources(self, ku_uid: str) -> Result[list[dict[str, Any]]]:
        """Get the curated Resources this Ku cites via CITES_RESOURCE.

        Surfaces the citation "Resources" section on the Ku detail page,
        mirroring the PathStep side. Flattens the backend's ``{"resource": {...},
        "locator": ...}`` rows to plain property dicts for the shared resource
        chip, merging the edge's ``locator`` free-string anchor when present.
        """
        if self.backend is None:
            return Result.fail(
                Errors.system("KuService backend not configured for graph operations")
            )
        result = await self.backend.get_cited_resources(ku_uid)
        if result.is_error:
            return Result.fail(result)
        # Each row's "resource" is a nested Neo4j map (r {.*}) — a dict, which the
        # scalar Neo4jProperties value union can't express. cast at this boundary.
        out: list[dict[str, Any]] = []
        for row in result.value or []:
            res = row.get("resource")
            if not res:
                continue
            merged = dict(cast("dict[str, Any]", res))
            loc = row.get("locator")
            if loc:
                merged["locator"] = loc
            out.append(merged)
        return Result.ok(out)

    # =========================================================================
    # LEARNING STATE (Ku-native — two-tier: Studying + Understood)
    # =========================================================================

    async def count_studying_kus(self, user_uid: UserUID) -> Result[int]:
        """Count Kus the user is currently studying (IN_PROGRESS or MARKED_AS_READ)."""
        result = await self.backend.count_studying_kus(user_uid)
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        return Result.ok(coerce_int(records[0]["cnt"]) if records else 0)

    async def mark_as_studying(self, user_uid: UserUID, ku_uid: str) -> Result[bool]:
        """Mark a Ku as actively being studied (IN_PROGRESS relationship)."""
        result = await self.backend.mark_in_progress(user_uid, ku_uid)
        if result.is_error:
            return Result.fail(result)
        return Result.ok(True)

    async def mark_as_understood(self, user_uid: UserUID, ku_uid: str) -> Result[bool]:
        """Mark a Ku as understood (MASTERED relationship, self-reported)."""
        result = await self.backend.mark_mastered(
            user_uid, ku_uid, mastery_score=0.7, method="self_report"
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(True)

    async def get_ku_learning_state(
        self, user_uid: UserUID, ku_uid: str
    ) -> Result[dict[str, bool]]:
        """Get learning state: {is_studying, is_understood}."""
        result = await self.backend.get_ku_learning_state(user_uid, ku_uid)
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.ok({"is_studying": False, "is_understood": False})
        rec = records[0]
        # MARKED_AS_READ treated as equivalent to studying for backward compat
        is_studying = bool(rec.get("is_studying")) or bool(rec.get("is_marked_as_read"))
        is_understood = bool(rec.get("is_understood"))
        return Result.ok({"is_studying": is_studying, "is_understood": is_understood})

    async def get_user_learning_states(self, user_uid: UserUID) -> Result[list[dict[str, Any]]]:
        """Get all Kus with learning state for a user (for sidebar display)."""
        result = await self.backend.get_user_learning_states(user_uid)
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])
