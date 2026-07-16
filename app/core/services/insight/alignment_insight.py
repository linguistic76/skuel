"""
Principle-Alignment Insight Persistence
=======================================

Shared build-and-persist ceremony for PRINCIPLE_ALIGNMENT insights, used by
the Task and Goal event handlers when a completed/achieved activity turns out
to be aligned with the user's principles.

Backend: InsightStore.create_insight.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.models.insight.persisted_insight import InsightImpact, InsightType, PersistedInsight

if TYPE_CHECKING:
    import structlog

    from core.models.type_hints import EntityUID, UserUID
    from core.services.insight.insight_store import InsightStore


async def persist_principle_alignment_insight(  # skuel-lint: disable=SKUEL005 -- fire-and-forget event side effect; failures logged, never surfaced
    insight_store: InsightStore | None,
    logger: structlog.BoundLogger,
    *,
    user_uid: UserUID,
    entity_uid: EntityUID,
    domain: str,
    title: str,
    description: str,
    principle_uids: list[str],
) -> None:
    """Persist a PRINCIPLE_ALIGNMENT insight; no-op when no store is wired.

    Failures are logged (warning), never raised — insight persistence is a
    best-effort side effect of event handling.
    """
    if insight_store is None:
        return

    insight = PersistedInsight(
        uid=PersistedInsight.generate_uid(InsightType.PRINCIPLE_ALIGNMENT, entity_uid),
        user_uid=user_uid,
        insight_type=InsightType.PRINCIPLE_ALIGNMENT,
        domain=domain,
        title=title,
        description=description,
        confidence=0.8,
        impact=InsightImpact.LOW,
        entity_uid=entity_uid,
        related_entities={"principles": principle_uids[:5]},
        supporting_data={"principle_count": len(principle_uids)},
    )
    create_result = await insight_store.create_insight(insight)
    if create_result.is_error:
        logger.warning(f"Failed to persist alignment insight: {create_result.error}")
