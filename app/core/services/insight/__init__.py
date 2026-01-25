"""
Insight Service Package
=======================

Provides persistence and retrieval for event-driven insights.

The InsightStore service stores insights in Neo4j and provides
APIs for listing, dismissing, and acting on insights.

Usage:
    from core.services.insight import InsightStore

    store = InsightStore(driver)
    await store.create_insight(insight)
    insights = await store.get_active_insights(user_uid)
"""

from core.services.insight.insight_store import InsightStore

__all__ = ["InsightStore"]
