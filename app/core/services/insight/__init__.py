"""
Insight Service Package
=======================

Persistence and retrieval for event-driven insights (InsightStore), and the
principle-alignment insight writer.

Usage:
    from core.services.insight import InsightStore

    store = InsightStore(backend)
    await store.create_insight(insight)
    insights = await store.get_active_insights(user_uid)
"""

from core.services.insight.alignment_insight import persist_principle_alignment_insight
from core.services.insight.insight_store import InsightStore

__all__ = ["InsightStore", "persist_principle_alignment_insight"]
