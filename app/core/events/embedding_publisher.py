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

if TYPE_CHECKING:
    from collections.abc import Collection

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
    UserEntryEmbeddingRequested,
)
from core.models.enums.entity_enums import EntityType
from core.utils.embedding_text_builder import EMBEDDING_FIELD_MAPS, build_embedding_text

if TYPE_CHECKING:
    from core.ports.infrastructure_protocols import EventBusOperations

# EntityType → event class for every type the background worker subscribes to.
# Mirrors the worker's subscription list (embedding_worker.start) — extend both
# together when a new entity type becomes embeddable.
# RESOURCE's producer is vault ingestion (Arc D 2026-07-03): descriptor files
# ingest via ENTITY_CONFIGS[RESOURCE] (embeddable=True), so both ingest doors
# publish ResourceEmbeddingRequested through this chokepoint. ResourceService
# stays read-only — there is no API create path for resources.
# USER_ENTRY's ONE producer is UserEntryService (create_entry + update paths),
# which gates on pipeline=knowledge before publishing — the ingestion door
# routes user_entry files through create_entry, and ENTITY_CONFIGS deliberately
# leaves UserEntry non-embeddable so ingestion never double-publishes.
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
    EntityType.USER_ENTRY: UserEntryEmbeddingRequested,
}

# EntityType → Neo4j node label for every embeddable type — THE one label map.
# Consumed by the background worker (embedding storage label) and the backfill
# script (candidate queries + storage). Mirrors EMBEDDING_EVENT_TYPES 1:1
# (guarded by tests/unit/services/ingestion/test_post_persist_embedding.py) —
# extend all three together when a new entity type becomes embeddable.
EMBEDDING_NODE_LABELS: dict[EntityType, str] = {
    EntityType.TASK: "Task",
    EntityType.GOAL: "Goal",
    EntityType.HABIT: "Habit",
    EntityType.EVENT: "Event",
    EntityType.CHOICE: "Choice",
    EntityType.PRINCIPLE: "Principle",
    EntityType.KU: "Ku",
    EntityType.RESOURCE: "Resource",
    EntityType.EXERCISE: "Exercise",
    EntityType.PATH_STEP: "PathStep",
    EntityType.LEARNING_PATH: "LearningPath",
    EntityType.REVISED_EXERCISE: "RevisedExercise",
    EntityType.USER_ENTRY: "UserEntry",
}


async def publish_embedding_requested(
    event_bus: EventBusOperations | None,
    entity_type: EntityType,
    source: dict[str, Any] | object,
    logger: Any = None,
    *,
    changed_fields: Collection[str] | None = None,
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
        changed_fields: For update paths — the fields the update wrote. When
            provided, the publish is skipped unless at least one changed field
            feeds this type's embedding text (``EMBEDDING_FIELD_MAPS``), so a
            status flip or progress bump never enqueues a redundant re-embed.
            Create paths omit it (everything is new).

    Returns:
        True if an event was published; False when the type has no event
        class, no changed field is embedding-relevant, the source yields no
        embeddable text, or the bus is missing.
    """
    event_cls = EMBEDDING_EVENT_TYPES.get(entity_type)
    if event_cls is None:
        return False

    if changed_fields is not None:
        embedding_fields = EMBEDDING_FIELD_MAPS.get(entity_type, ())
        if not set(changed_fields) & set(embedding_fields):
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
