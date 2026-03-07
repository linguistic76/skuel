"""
Ku Intelligence Service
========================

Intelligence service for atomic Knowledge Units — graph analytics, no AI.

Provides:
- Graph context retrieval (get_with_context)
- Performance analytics (get_performance_analytics)
- Domain insights (get_domain_insights)
- Usage summary (articles, learning steps, organized children)
- Organization depth (ORGANIZES tree traversal)

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.enums import Domain
from core.models.ku.ku import Ku
from core.models.ku.ku_dto import KuDTO
from core.services.base_analytics_service import BaseAnalyticsService
from core.services.intelligence import GraphContextOrchestrator
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.graph_context import GraphContext
    from core.ports import BackendOperations

logger = get_logger(__name__)


class KuIntelligenceService(
    BaseAnalyticsService["BackendOperations[Ku]", "Ku"]
):
    """
    Intelligence service for atomic Knowledge Units.

    Extends BaseAnalyticsService (ADR-030) — NO AI dependencies.
    Pure graph queries and Python calculations.

    Provides:
    - Usage analysis: how many articles/steps reference this Ku
    - Organization analysis: ORGANIZES tree depth and child count
    - Existence checks: is_trained, is_organized
    """

    _service_name = "ku.intelligence"

    def __init__(
        self,
        backend: BackendOperations[Ku],
        graph_intelligence_service: Any | None = None,
        relationship_service: Any | None = None,
        event_bus: Any | None = None,
    ) -> None:
        super().__init__(
            backend=backend,
            graph_intelligence_service=graph_intelligence_service,
            relationship_service=relationship_service,
            event_bus=event_bus,
        )

        if graph_intelligence_service:
            self.orchestrator = GraphContextOrchestrator[Ku, KuDTO](
                service=self,
                backend_get_method="get",
                dto_class=KuDTO,
                model_class=Ku,
                domain=Domain.KNOWLEDGE,
            )

    # ========================================================================
    # INTELLIGENCEOPERATIONS PROTOCOL METHODS
    # ========================================================================

    async def get_with_context(
        self, uid: str, depth: int = 2
    ) -> Result[tuple[Ku, GraphContext]]:
        """Get Ku with full graph context (articles, learning steps, children)."""
        if self.orchestrator is None:
            return Result.fail(
                Errors.system(
                    message="Graph intelligence service required for context queries",
                    operation="get_with_context",
                )
            )
        return await self.orchestrator.get_with_context(uid=uid, depth=depth)

    async def get_performance_analytics(
        self, user_uid: str, period_days: int = 30
    ) -> Result[dict[str, Any]]:
        """Get overall Ku statistics (shared content, not user-specific)."""
        ku_result = await self.backend.find_by()
        if ku_result.is_error:
            return Result.fail(ku_result.expect_error())

        all_kus = ku_result.value or []
        total = len(all_kus)

        # Count by namespace
        namespaces: dict[str, int] = {}
        for ku in all_kus:
            ns = getattr(ku, "namespace", None) or "unassigned"
            namespaces[ns] = namespaces.get(ns, 0) + 1

        return Result.ok(
            {
                "user_uid": user_uid,
                "period_days": period_days,
                "total_kus": total,
                "by_namespace": namespaces,
                "analytics": {
                    "total": total,
                    "note": "Kus are shared curriculum content",
                },
            }
        )

    async def get_domain_insights(
        self, uid: str, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        """Get domain-specific insights for a Ku."""
        ku_result = await self.backend.get(uid)
        if ku_result.is_error:
            return Result.fail(ku_result.expect_error())

        ku = ku_result.value
        if not ku:
            return Result.fail(Errors.not_found(resource="Ku", identifier=uid))

        usage_result = await self.get_usage_summary(uid)
        usage = usage_result.value if usage_result.is_ok else {}

        depth_result = await self.get_organization_depth(uid)
        org_depth = depth_result.value if depth_result.is_ok else 0

        return Result.ok(
            {
                "ku_uid": uid,
                "ku_title": ku.title,
                "namespace": ku.namespace,
                "ku_category": ku.ku_category,
                "alias_count": len(ku.aliases),
                "usage": usage,
                "organization_depth": org_depth,
                "min_confidence": min_confidence,
            }
        )

    # ========================================================================
    # DOMAIN-SPECIFIC METHODS
    # ========================================================================

    @with_error_handling("get_usage_summary", error_type="database", uid_param="ku_uid")
    async def get_usage_summary(self, ku_uid: str) -> Result[dict[str, int]]:
        """Count articles (USES_KU), learning steps (TRAINS_KU), and organized children (ORGANIZES).

        Single Cypher query for efficiency.
        """
        query = """
            MATCH (ku:Entity:Ku {uid: $ku_uid})
            OPTIONAL MATCH (article:Entity)-[:USES_KU]->(ku)
            OPTIONAL MATCH (ls:Entity)-[:TRAINS_KU]->(ku)
            OPTIONAL MATCH (ku)-[:ORGANIZES]->(child:Entity)
            RETURN count(DISTINCT article) as articles,
                   count(DISTINCT ls) as learning_steps,
                   count(DISTINCT child) as organized_children
        """
        result = await self.backend.execute_query(query, {"ku_uid": ku_uid})
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []
        if not records:
            return Result.ok({"articles": 0, "learning_steps": 0, "organized_children": 0})

        row = records[0]
        return Result.ok(
            {
                "articles": row.get("articles", 0),
                "learning_steps": row.get("learning_steps", 0),
                "organized_children": row.get("organized_children", 0),
            }
        )

    @with_error_handling("is_trained", error_type="database", uid_param="ku_uid")
    async def is_trained(self, ku_uid: str) -> Result[bool]:
        """Check if any Learning Step trains this Ku via TRAINS_KU."""
        query = """
            MATCH (ls:Entity)-[:TRAINS_KU]->(ku:Entity:Ku {uid: $ku_uid})
            RETURN count(ls) > 0 as trained
        """
        result = await self.backend.execute_query(query, {"ku_uid": ku_uid})
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []
        return Result.ok(records[0].get("trained", False) if records else False)

    @with_error_handling("is_organized", error_type="database", uid_param="ku_uid")
    async def is_organized(self, ku_uid: str) -> Result[bool]:
        """Check if this Ku has ORGANIZES children (acts as MOC)."""
        query = """
            MATCH (ku:Entity:Ku {uid: $ku_uid})-[:ORGANIZES]->(child:Entity)
            RETURN count(child) > 0 as organized
        """
        result = await self.backend.execute_query(query, {"ku_uid": ku_uid})
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []
        return Result.ok(records[0].get("organized", False) if records else False)

    @with_error_handling("get_organization_depth", error_type="database", uid_param="ku_uid")
    async def get_organization_depth(self, ku_uid: str) -> Result[int]:
        """Get depth of the ORGANIZES tree below this Ku."""
        query = """
            MATCH path = (ku:Entity:Ku {uid: $ku_uid})-[:ORGANIZES*]->(descendant:Entity)
            RETURN max(length(path)) as max_depth
        """
        result = await self.backend.execute_query(query, {"ku_uid": ku_uid})
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []
        if not records or records[0].get("max_depth") is None:
            return Result.ok(0)

        return Result.ok(records[0]["max_depth"])
