"""
Embedding Request Publisher — THE Entity-Embedding Refresh Chokepoint
======================================================================

One function for every producer of ``*EmbeddingRequested`` events: in-app
create paths, in-app update paths, and the ingestion post-persist step all
publish through :func:`publish_embedding_requested`. The
:class:`~core.services.background.embedding_worker.EmbeddingBackgroundWorker`
subscribes to every event class in :data:`EMBEDDING_EVENT_TYPES`, so a
publish here is the complete write-side contract — text recipe
(``build_embedding_text``), event selection, and timestamping happen in
exactly one place.

Ingestion never embeds inline (ADR-074): persistence first, then a publish
through this chokepoint; the worker embeds asynchronously in batches.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.events.embedding_events import (
    ChoiceEmbeddingRequested,
    EmbeddingRequested,
    EventEmbeddingRequested,
    ExerciseEmbeddingRequested,
    GoalEmbeddingRequested,
    HabitEmbeddingRequested,
    KuEmbeddingRequested,
    LearningPathEmbeddingRequested,
    PathStepEmbeddingRequested,
    PrincipleEmbeddingRequested,
    ResourceEmbeddingRequested,
    RevisedExerciseEmbeddingRequested,
    TaskEmbeddingRequested,
)
from core.models.enums.entity_enums import EntityType
from core.utils.embedding_text_builder import build_embedding_text

if TYPE_CHECKING:
    from core.ports.infrastructure_protocols import EventBusOperations

# EntityType → event class for every type the background worker subscribes to.
# Mirrors the worker's subscription list (embedding_worker.start) — extend both
# together when a new entity type becomes embeddable.
# NOTE: RESOURCE currently has no producer that reaches this chokepoint —
# Resource is not file-ingestible (no ENTITY_CONFIGS entry) and ResourceService
# is read-only. The mapping is staged so the first Resource creation path
# (ingestion config or a ResourceService.create) embeds with zero extra wiring.
EMBEDDING_EVENT_TYPES: dict[EntityType, type[EmbeddingRequested]] = {
    EntityType.TASK: TaskEmbeddingRequested,
    EntityType.GOAL: GoalEmbeddingRequested,
    EntityType.HABIT: HabitEmbeddingRequested,
    EntityType.EVENT: EventEmbeddingRequested,
    EntityType.CHOICE: ChoiceEmbeddingRequested,
    EntityType.PRINCIPLE: PrincipleEmbeddingRequested,
    EntityType.KU: KuEmbeddingRequested,
    EntityType.RESOURCE: ResourceEmbeddingRequested,
    EntityType.EXERCISE: ExerciseEmbeddingRequested,
    EntityType.PATH_STEP: PathStepEmbeddingRequested,
    EntityType.LEARNING_PATH: LearningPathEmbeddingRequested,
    EntityType.REVISED_EXERCISE: RevisedExerciseEmbeddingRequested,
}


async def publish_embedding_requested(
    event_bus: EventBusOperations | None,
    entity_type: EntityType,
    source: dict[str, Any] | object,
    logger: Any = None,
) -> bool:
    """
    Build embedding text for a persisted entity and publish its refresh event.

    Call AFTER the entity is persisted — the worker re-reads nothing; the
    event carries the full embedding text, so publishing before persistence
    would only risk storing an embedding on a node that never landed.

    Args:
        event_bus: Event bus (``None`` follows the ``publish_event`` contract:
            logged warning, event dropped). Callers that legitimately run
            without a bus — CORE-tier ingestion — must gate before calling.
        entity_type: The entity's type; selects the event class.
        source: Domain model or Neo4j property dict — anything
            ``build_embedding_text`` accepts. Must carry ``uid``.
        logger: Optional logger for the publish warning path.

    Returns:
        True if an event was published; False when the type has no event
        class, the source yields no embeddable text, or the bus is missing.
    """
    event_cls = EMBEDDING_EVENT_TYPES.get(entity_type)
    if event_cls is None:
        return False

    embedding_text = build_embedding_text(entity_type, source)
    if not embedding_text:
        return False

    uid = source["uid"] if isinstance(source, dict) else source.uid  # type: ignore[attr-defined]  # DomainModelProtocol guarantees uid

    from core.events import publish_event

    return await publish_event(
        event_bus,
        event_cls(
            entity_uid=uid,
            entity_type=entity_type.value,
            embedding_text=embedding_text,
            requested_at=datetime.now(),
        ),
        logger,
    )
