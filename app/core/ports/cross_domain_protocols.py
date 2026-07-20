"""
Cross-Domain Protocols
======================

Protocols for the CrossDomainBackend — the read-only adapter layer for
cross-domain analytics, queries, and graph intelligence.

Implementation: adapters/persistence/neo4j/cross_domain_backend.py
Consumers: CrossDomainAnalyticsService, CrossDomainQueryService,
           GraphIntelligenceService
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from datetime import date, datetime

    from core.models.query_types import QueryIntent


@runtime_checkable
class CrossDomainBackendOperations(Protocol):
    """Backend operations for cross-domain analytics, queries, and graph intelligence.

    Single protocol covering all three cross-domain services. One backend
    instance is shared by CrossDomainAnalyticsService, CrossDomainQueryService,
    and GraphIntelligenceService.
    """

    # ================================================================
    # ANALYTICS — Event-driven analytics node CRUD
    # ================================================================

    async def upsert_learning_velocity(
        self, user_uid: str, mastery_score: float, occurred_at: str
    ) -> Result[list[dict[str, Any]]]: ...

    async def increment_paths_completed(self, user_uid: str) -> Result[list[dict[str, Any]]]: ...

    async def upsert_productivity_analytics(
        self, user_uid: str, occurred_at: str
    ) -> Result[list[dict[str, Any]]]: ...

    async def upsert_habit_analytics(
        self, user_uid: str, occurred_at: str
    ) -> Result[list[dict[str, Any]]]: ...

    async def upsert_event_analytics(
        self, user_uid: str, occurred_at: str
    ) -> Result[list[dict[str, Any]]]: ...

    async def get_learning_velocity_metrics(
        self, user_uid: str, start_date: str
    ) -> Result[list[dict[str, Any]]]: ...

    async def get_productivity_analytics(self, user_uid: str) -> Result[list[dict[str, Any]]]: ...

    async def get_habit_analytics(self, user_uid: str) -> Result[list[dict[str, Any]]]: ...

    # ================================================================
    # CROSS-DOMAIN QUERIES — Multi-domain graph reads
    # ================================================================

    async def get_principle_alignment_evidence(
        self, principle_uid: str, user_uid: str
    ) -> Result[list[dict[str, Any]]]: ...

    async def get_embodiment_rates_7d(
        self, principle_uids: list[str], user_uid: str, cutoff: datetime
    ) -> Result[list[dict[str, Any]]]: ...

    async def get_tasks_applying_knowledge(
        self, knowledge_uid: str, user_uid: str, limit: int
    ) -> Result[list[dict[str, Any]]]: ...

    async def get_goals_for_tasks_batch(
        self, task_uids: list[str]
    ) -> Result[list[dict[str, Any]]]: ...

    async def count_active_tasks_for_goal(self, goal_uid: str) -> Result[list[dict[str, Any]]]: ...

    async def get_habit_knowledge_reinforcement(
        self, user_uid: str
    ) -> Result[list[dict[str, Any]]]: ...

    async def get_choice_principle_adherence(
        self, user_uid: str, period_days: int
    ) -> Result[list[dict[str, Any]]]: ...

    async def get_choice_conflict_count(self, user_uid: str) -> Result[list[dict[str, Any]]]: ...

    async def get_event_impact_batch(
        self, user_uid: str, start_date: date, end_date: date
    ) -> Result[list[dict[str, Any]]]: ...

    # ================================================================
    # GRAPH INTELLIGENCE — Pure Cypher graph analytics
    # ================================================================

    async def find_knowledge_hubs(
        self, domain_filter: str, params: dict[str, Any]
    ) -> Result[list[dict[str, Any]]]: ...

    async def find_similar_knowledge(
        self, uid: str, min_similarity: float, limit: int
    ) -> Result[list[dict[str, Any]]]: ...

    async def analyze_prerequisite_depth(self, uid: str) -> Result[list[dict[str, Any]]]: ...

    async def find_learning_clusters(
        self, domain_filter: str, params: dict[str, Any]
    ) -> Result[list[dict[str, Any]]]: ...

    async def calculate_knowledge_importance(self, uid: str) -> Result[list[dict[str, Any]]]: ...

    async def query_with_intent(
        self,
        intent: QueryIntent,
        depth: int,
        uid: str,
        relationship_types: list[str] | None = None,
    ) -> Result[list[dict[str, Any]]]: ...

    async def get_entity_labels(self, uid: str) -> Result[list[dict[str, Any]]]: ...

    async def get_ku_titles_and_tags(self) -> Result[list[dict[str, Any]]]: ...

    async def get_prerequisite_graph(self, ku_uids: list[str]) -> Result[list[dict[str, Any]]]: ...

    async def get_user_learning_state(self, user_uid: str) -> Result[list[dict[str, Any]]]: ...

    async def get_knowledge_patterns(
        self, entity_uids: list[str]
    ) -> Result[list[dict[str, Any]]]: ...

    async def find_cross_domain_connections(
        self, entity_uid: str, target_domains: list[str]
    ) -> Result[list[dict[str, Any]]]: ...

    # ================================================================
    # ADMIN STATS — System-wide aggregation queries
    # ================================================================

    async def get_entity_system_metrics(self) -> Result[list[dict[str, Any]]]: ...

    async def get_all_users_progress(self) -> Result[list[dict[str, Any]]]: ...

    async def get_user_ku_detail(self, user_uid: str) -> Result[list[dict[str, Any]]]: ...

    async def get_user_submissions_detail(self, user_uid: str) -> Result[list[dict[str, Any]]]: ...

    async def get_user_detail_stats(self, user_uid: str) -> Result[list[dict[str, Any]]]: ...

    async def get_activity_entity_counts(self) -> Result[list[dict[str, Any]]]: ...

    async def get_user_role_counts(self) -> Result[list[dict[str, Any]]]: ...

    async def get_users_with_activity_counts(
        self, where_str: str, params: dict[str, Any]
    ) -> Result[list[dict[str, Any]]]: ...

    async def get_recent_activities(self, user_uid: str) -> Result[list[dict[str, Any]]]: ...
