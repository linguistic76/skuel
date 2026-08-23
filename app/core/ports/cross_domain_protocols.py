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
    from core.ports.query_types import (
        JournalEntryRow,
        SelCategoryRow,
        UserKnowledgeChannelRow,
    )


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

    async def recompute_productivity_analytics(
        self, user_uid: str, occurred_at: str | None
    ) -> Result[list[dict[str, Any]]]:
        """Recompute ``tasks_completed`` from the user's currently-completed tasks.

        Derived, not tallied — idempotent under a repeat complete and able to
        fall when a task is reopened. ``occurred_at`` is ``None`` on the reopen
        path, which recomputes the count and leaves both completion stamps
        untouched (a reopen is not a completion).
        """
        ...

    async def upsert_habit_analytics(
        self, user_uid: str, occurred_at: str
    ) -> Result[list[dict[str, Any]]]: ...

    async def upsert_event_analytics(
        self, user_uid: str, occurred_at: str
    ) -> Result[list[dict[str, Any]]]: ...

    async def get_learning_velocity_metrics(
        self, user_uid: str, start_date: str
    ) -> Result[list[dict[str, Any]]]: ...

    async def get_productivity_analytics(
        self, user_uid: str, window_start: str
    ) -> Result[list[dict[str, Any]]]:
        """The stored ProductivityAnalytics node plus the trailing-window count.

        ``window_start`` is an inclusive ISO ``YYYY-MM-DD`` date bound; the row
        carries ``completed_in_window``, the numerator of
        ``completion_velocity``. Always exactly one row — ``analytics`` is
        ``None`` when the user has no node, and the derived count stands on its
        own.
        """
        ...

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

    async def get_journal_entries_in_range(
        self,
        user_uid: str,
        start_datetime: str,
        end_datetime: str,
    ) -> Result[list["JournalEntryRow"]]:
        """Journal SOURCE entries in a datetime range.

        After ADR-054 these are ``:UserEntry`` with
        ``pipeline='transcribe_and_structure'``; the LLM-structured child is
        deliberately excluded. Bounds are ISO-8601 strings, compared against
        the node's stored temporal value.
        """
        ...

    async def get_user_knowledge_channels(
        self, user_uid: str, activity_types: list[str]
    ) -> Result[list[UserKnowledgeChannelRow]]:
        """``{entity_type, activity_uid, ku_uids}`` per knowledge-naming activity.

        Unwindowed and status-blind — the cumulative source for per-user
        substance, as distinct from the MEGA-QUERY's planning-window rollup.
        """
        ...

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

    async def get_sel_categories(self, uids: list[str]) -> Result[list[SelCategoryRow]]: ...

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
