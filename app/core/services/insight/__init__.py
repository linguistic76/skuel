"""
Insight Service Package
=======================

Both sides of the insight domain: persistence/retrieval for event-driven
insights (InsightStore) and task-to-knowledge generation
(InsightGenerationService — shell + pattern-analysis / insight-synthesis /
quality-curation mixins, July 2026 decomposition).

Usage:
    from core.services.insight import InsightGenerationService, InsightStore

    store = InsightStore(driver)
    await store.create_insight(insight)
    insights = await store.get_active_insights(user_uid)
"""

from core.services.insight.alignment_insight import persist_principle_alignment_insight
from core.services.insight.insight_generation_service import InsightGenerationService
from core.services.insight.insight_store import InsightStore

__all__ = ["InsightGenerationService", "InsightStore", "persist_principle_alignment_insight"]
