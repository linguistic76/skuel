"""
Unified Ingestion Service - Orchestration Layer
================================================

Ingestion is one-way: the vault authors, the graph obeys. A re-sync of an
edited file upserts the entity, re-chunks its body and MERGEs the edges its
frontmatter declares; a target dropped from a registered frontmatter field
loses its edge on that sync — only the edges the file itself authored (the
``authored_edges`` fingerprint on its tracker row) are retracted, and an edge
MERGEd by both a file and an app door is one edge that the file's retraction
removes, because the vault is the author (ADR-070 Decision 10). The MOC
body-link pass refreshes its own edges the same way. A deleted file removes
what it declared. Nothing in this service writes into the content vault.
Curriculum structure (Ku, PathStep, LearningPath, CURRICULUM-scope Exercise)
has no create/update/delete route in the app — ADR-070 Decision 10 holds the
ruling and the inventory of what SKUEL does author in-app.

This module orchestrates content ingestion by composing:
- config.py - Entity configurations and constants
- types.py - Data classes (IngestionStats, ValidationResult, etc.)
- parser.py - MD/YAML file parsing
- detector.py - Format and entity type detection
- preparer.py - Entity data preparation
- validator.py - Validation pipeline
- batch.py - Concurrent batch operations

Architecture:
- The orchestrator delegates parsing/validation/persistence to the modules
  above and owns the cross-cutting seams: vault-descriptor ownership + walls
  (ADR-070), the post-persist embedding step (ADR-074), and the shared
  body-chunk step for ``chunks_body_content`` types (PathStep, Ku)
- Each module has ONE job (separation of concerns)
- Clear data flow: Parse → Detect → Validate → Prepare → Ingest

Key Design Decisions (ADR-014):
- Format Support: Both MD + YAML as first-class citizens
- Architecture: Single unified service (one path forward)
- UID Format: authored dot form (`ku.{ns}.{slug}`), stored verbatim — a colon-spelled
  uid fails prefix validation (ADR-013; CURRICULUM_GROUPING_PATTERNS § Authoring Spelling)
- Performance: BulkUpsertBackend for batch operations (10-100x faster)

See: /docs/decisions/ADR-014-unified-ingestion.md
"""

from __future__ import annotations

__version__ = "2.0"

from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from pathlib import Path

    from core.ports.ingestion_protocols import (
        BulkUpsertOperations,
        IngestionBackendOperations,
        IngestionWriteOperations,
    )
    from core.services.user_entry.user_entry_processing_service import (
        UserEntryProcessingService,
    )
    from core.services.user_entry.user_entry_service import UserEntryService
    from core.services.user_service import UserService
    from core.services.vault.vault_descriptor import VaultRegistry

from core.models.enums.entity_enums import EntityType, NonKuDomain
from core.models.enums.pipeline import Pipeline
from core.models.ps_content.content_chunks import ChunkingParams
from core.models.relationship_names import RelationshipName
from core.models.type_hints import EntityUID, UserUID
from core.services.vault.vault_descriptor import VaultKind
from core.utils.decorators import with_error_handling
from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

from .authored_edges import authored_edge_fingerprint, retracted_edges
from .batch import find_entity_file, ingest_bundle, ingest_directory, ingest_vault
from .config import (
    DEFAULT_MAX_FILE_SIZE_BYTES,
    DEFAULT_USER_UID,
    ENTITY_CONFIGS,
    SyncAllowlist,
    is_ingestible_path,
    je_pro_skip_reason,
    resolve_chunking_params,
)
from .detector import detect_entity_type, detect_format, is_edge_type
from .ingestion_tracker import IngestionTracker
from .moc_links import extract_moc_link_suffixes, frontmatter_organizes_targets
from .parser import parse_markdown, parse_yaml
from .preparer import (
    prepare_edge_data,
    prepare_entity_data,
)
from .types import (
    BundleStats,
    ChunkSource,
    DirectoryValidationResult,
    DryRunPreview,
    IncrementalStats,
    IngestionStats,
    ValidationResult,
)
from .user_entry_ingestion import ingest_user_entry
from .validator import (
    validate_directory,
    validate_edge_data,
    validate_entity_data,
    validate_file,
    validate_required_fields,
    validate_uid_format,
)

logger = get_logger("skuel.services.unified_ingestion")


class UnifiedIngestionService:
    """
    Unified service for ingesting content from both MD and YAML formats.

    Orchestrates capabilities from decomposed modules:
    - Auto-detects file format (MD vs YAML)
    - Routes to the appropriate entity type (every ENTITY_CONFIGS entry)
    - Normalizes UIDs to dot notation
    - Uses BulkUpsertBackend for batch performance
    - Creates graph-native relationships

    Usage:
        from adapters.persistence.neo4j.ingestion_service_factory import (
            make_unified_ingestion_service,
        )

        service = make_unified_ingestion_service(driver)

        # Single file
        result = await service.ingest_file(Path("ku_machine-learning.md"))

        # Directory
        result = await service.ingest_directory(Path("/docs"))

        # Vault
        result = await service.ingest_vault(Path("/vault"), subdirs=["docs", "notes"])

        # Bundle
        result = await service.ingest_bundle(Path("/bundles/mindfulness"))
    """

    def __init__(
        self,
        write_backend: IngestionWriteOperations,
        bulk_backend: BulkUpsertOperations,
        default_user_uid: UserUID | None = None,
        max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
        chunking_service: Any | None = None,
        content_adapter: Any | None = None,
        event_bus: Any | None = None,
        ingestion_backend: "IngestionBackendOperations | None" = None,
        user_entry_service: UserEntryService | None = None,
        user_service: UserService | None = None,
        user_entry_processor: UserEntryProcessingService | None = None,
        sync_allowlist: SyncAllowlist | None = None,
    ) -> None:
        """
        Initialize unified ingestion service.

        Args:
            write_backend: IngestionWriteOperations port for edge/existence/ownership writes.
            bulk_backend: BulkUpsertOperations port for node upsert + constraints + delete.
                Both are built at the composition root and injected so this service
                never imports the adapter (ADR-044 / SKUEL022); use
                ``make_unified_ingestion_service(driver, ...)`` to build them.
            default_user_uid: Default user UID for entities without explicit user_uid.
                              If not provided, uses SKUEL_DEFAULT_USER_UID env var or "user_system".
            max_file_size_bytes: Maximum file size in bytes (default: 10 MB).
                                 Files larger than this will be rejected to prevent OOM.
            chunking_service: Optional EntityChunkingService for automatic chunk generation.
                              If not provided, ingestion works without chunking (graceful degradation).
            content_adapter: Neo4jContentAdapter for persisting :Content and :ContentChunk nodes
                             after chunk generation. Required in production for RAG retrieval;
                             when omitted, chunks remain in-memory only.
            event_bus: EventBusOperations for the post-persist embedding step — publishes
                       ``*EmbeddingRequested`` (per persisted embeddable entity, both ingest
                       doors) and ``ChunkEmbeddingRequested`` to the background embedding
                       worker. Tier-gated at the composition root: wired only at FULL, ``None``
                       in CORE where the worker isn't running (a publish would be a
                       queue-with-no-listener). Ingestion never embeds inline (ADR-074).
            ingestion_backend: Backend for ingestion tracking (optional).
            user_entry_service: UserEntryService for routing UserEntry YAMLs through
                                the same create_entry() pipeline as /submit. Required
                                when ingesting ``type: user_entry`` files.
            user_service: UserService for role lookup during UserEntry ingestion
                          (gates ``audience: public`` on TEACHER role). When not
                          wired, ``audience: public`` uploads are rejected as
                          forbidden.
            user_entry_processor: UserEntryProcessingService that runs the
                          entry's ``pipeline`` after persistence. When wired, a
                          ``pipeline: extract_activities`` periodic note has its
                          ``- [ ]`` lines extracted into Tasks on ingest (ADR-069).
                          Extraction failures are isolated — the journal node
                          persists regardless. Late-bound at the composition root.
            sync_allowlist: Optional fail-closed folder allowlist (SyncAllowlist)
                          enforced on every ingestion path — directory scans
                          (``ingest_directory`` → collect_files, driving the
                          reconciler) AND single-file ingestion
                          (``ingest_file`` → /api/ingest/file). When
                          set, files under the governed vault root are ingested
                          only if they sit under an allowed dir; ``None`` = no
                          wall. Late-bound at the composition root once the vault
                          root is known.
        """
        if write_backend is None or bulk_backend is None:
            raise ValueError("IngestionWriteBackend and BulkUpsertBackend are required")

        # All ingestion Cypher lives below the boundary (ADR-044): edge/existence
        # writes in IngestionWriteBackend, node upsert + constraints + delete in
        # BulkUpsertBackend. Both are injected at the composition root; the service
        # orchestrates and calls these backends and never authors Cypher, opens
        # sessions, or imports the adapter (SKUEL022).
        self._write_backend = write_backend
        self._bulk_backend = bulk_backend
        self.ingestion_backend = ingestion_backend
        self.default_user_uid = (
            default_user_uid if default_user_uid is not None else DEFAULT_USER_UID
        )
        self.max_file_size_bytes = max_file_size_bytes
        self.chunking = chunking_service  # Can be None - graceful degradation
        self.content_adapter = content_adapter  # Can be None - graceful degradation
        self.event_bus = event_bus  # None in CORE tier — no embedding publishes
        self.user_entry_service = user_entry_service
        self.user_service = user_service
        # Late-bound at the composition root (UserEntryProcessingService is built
        # after this service); runs entry.pipeline after persistence.
        self.user_entry_processor = user_entry_processor
        # Fail-closed folder allowlist, late-bound at the composition root once the
        # governed vault root is resolved. Applied to every ingest_directory scan
        # so both ingestion doors inherit the same privacy wall.
        self.sync_allowlist = sync_allowlist
        # Late-bound at the composition root. Resolves which vault governs a target
        # path so the OWNER of USER_OWNED entities is a function of the vault, not
        # of the ingest surface (dashboard/reconciler/script all agree). ``None``
        # (minimal composes / tests) → owner falls back to the acting hint.
        self.vault_registry: VaultRegistry | None = None
        self.logger = logger

        # Log chunking availability
        if self.chunking:
            self.logger.info(
                "✅ Chunking service available - will generate chunks during "
                "PathStep/Ku body ingestion"
            )
        else:
            self.logger.warning(
                "⚠️ Chunking service not available - PathStep/Ku ingestion will work without chunks"
            )

        # Chunks reach Neo4j only when both the chunker and the content adapter are wired.
        # In tests, omitting either keeps the path entirely in-memory; in production
        # both are wired in compose.py so the full ingest → persist → embed chain runs.
        if self.chunking and not self.content_adapter:
            self.logger.warning(
                "⚠️ Chunking enabled but content_adapter missing — chunks will not be persisted to Neo4j"
            )
        if self.content_adapter and not self.event_bus:
            self.logger.info(
                "Content adapter wired without event_bus — chunks persist but no embedding "
                "events publish (expected in CORE tier, miswired in FULL)"
            )

    # ========================================================================
    # EDGE INGESTION
    # ========================================================================

    @with_error_handling("ingest_edge", error_type="system")
    async def ingest_edge(self, edge_data: dict[str, Any]) -> Result[dict[str, Any]]:
        """
        Ingest a standalone edge (relationship) into Neo4j.

        Uses the edge-write backend (not the bulk node upsert) since edges create
        relationships, not nodes. Idempotent: re-ingesting an edge refreshes its
        evidence properties instead of adding a second one, and ``created`` then
        reports ``False``.

        Args:
            edge_data: Prepared edge data from prepare_edge_data()

        Returns:
            Result with edge details (from_uid, to_uid, relationship, created —
            whether this call created the edge rather than updating one already
            in the graph)
        """
        from_uid = edge_data["from_uid"]
        to_uid = edge_data["to_uid"]
        props = edge_data["properties"]

        # Convert the validated-but-stringly-typed dict value into a typed
        # RelationshipName at the boundary — this is where the value re-enters the
        # typed world, so the enum (not "validated by caller" discipline) is what
        # guarantees the rel-type interpolation in IngestionWriteBackend is safe.
        rel_type = RelationshipName.from_string(edge_data["relationship"])
        if rel_type is None:
            return Result.fail(
                Errors.validation(
                    f"Unknown relationship type: {edge_data['relationship']!r}",
                    field="relationship",
                )
            )

        try:
            # The Cypher lives in IngestionWriteBackend below the boundary (ADR-044).
            records = await self._write_backend.ingest_edge(from_uid, to_uid, rel_type, props)

            if not records:
                # One or both entities not found
                missing: list[str] = []
                for uid, label in [(from_uid, "from"), (to_uid, "to")]:
                    if not await self._write_backend.entity_exists(uid):
                        missing.append(f"{label}={uid}")
                return Result.fail(
                    Errors.not_found(
                        resource="Entity",
                        identifier=", ".join(missing),
                    )
                )

            record = records[0]
            was_created = record["created"]
            self.logger.info(
                f"{'Created' if was_created else 'Updated'} edge: "
                f"({from_uid})-[:{rel_type}]->({to_uid})"
            )

            return Result.ok(
                {
                    "from_uid": from_uid,
                    "to_uid": to_uid,
                    "relationship": rel_type,
                    "created": was_created,
                    "success": True,
                }
            )

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to ingest edge ({from_uid})-[:{rel_type}]->({to_uid}): {e}")
            return Result.fail(
                Errors.database(
                    operation="ingest_edge",
                    message=f"Edge ingestion failed: {e}",
                )
            )

    # ========================================================================
    # OWNERSHIP
    # ========================================================================

    @property
    def _owner_is_authoritative(self) -> bool:
        """Whether the descriptor-resolved owner overrides a file-supplied ``user_uid``.

        True when a vault registry governs ownership (descriptor wins — a file
        cannot spoof ownership of a USER_OWNED entity); False in minimal composes
        where the file's own ``user_uid`` is still honored.
        """
        return self.vault_registry is not None

    def _resolve_owner(self, path: Path, user_uid: UserUID | None) -> UserUID:
        """Owner to attribute to what ``path`` yields — a function of the vault.

        ``user_uid`` is the *acting-user hint* (whoever triggered the ingest). The
        real owner comes from the vault descriptor governing ``path`` (via
        :meth:`VaultRegistry.resolve_by_path`), so the same file gets the same
        owner regardless of ingest surface: content-vault paths → the content
        acts-as owner; personal-vault paths → that vault's bound owner (the
        primary VAULT_ROOT owner, or the ``{uid}`` of a ``user_vaults/{uid}/``
        member vault). The hint never decides ownership when a registry governs.
        Only ``requires_user_uid`` entity types actually persist this owner;
        SHARED curriculum drops it (see ``preparer.prepare_entity_data``).

        Falls back to ``user_uid or self.default_user_uid`` when no registry is
        wired (minimal composes / unit tests) — never a random user.
        """
        acting = user_uid or self.default_user_uid
        if self.vault_registry is None:
            return acting
        descriptor = self.vault_registry.resolve_by_path(path, acting)
        return descriptor.value.owner_uid if descriptor.is_ok else acting

    def _resolve_allowlist(
        self, path: Path, allowlist: SyncAllowlist | None
    ) -> SyncAllowlist | None:
        """Fail-closed wall for a file or directory ``path`` — a function of the vault.

        An explicit ``allowlist`` always wins: the descriptor-driven reconciler
        passes the target vault's own wall, and it must not be second-guessed.
        Otherwise, when a registry is wired, derive the wall from the descriptor
        governing ``path`` (via :meth:`VaultRegistry.resolve_by_path`) so every
        surface inherits the same per-vault wall the reconciler uses — the by-path
        counterpart to :meth:`_resolve_owner`. This is what applies the content
        vault's ``je_*`` staging floor to a content file ingested through the
        single-file door, matching the directory / reconciler paths.

        Safe because the caller resolves against a path that is unambiguously in
        one vault: a single file, or a directory guarded to be single-vault (see
        :meth:`VaultRegistry.nested_vault_roots`). Falls back to
        ``self.sync_allowlist`` when no registry is wired or no descriptor governs
        the path. Owner-independent, so the acting hint is ``self.default_user_uid``.
        """
        if allowlist is not None:
            return allowlist
        if self.vault_registry is None:
            return self.sync_allowlist
        descriptor = self.vault_registry.resolve_by_path(path, self.default_user_uid)
        return descriptor.value.allowlist if descriptor.is_ok else self.sync_allowlist

    # ========================================================================
    # POST-PERSIST EMBEDDING STEP (ADR-074)
    # ========================================================================

    async def _publish_embedding_requests(
        self, entity_type: EntityType | NonKuDomain, entities: list[dict[str, Any]]
    ) -> None:
        """
        Publish ``*EmbeddingRequested`` for persisted entities — both ingest doors.

        The one place ingestion touches embeddings: after persistence, for
        entity types whose ``ENTITY_CONFIGS.embeddable`` flag is set, publish
        the type's event through the shared chokepoint
        (``core.events.embedding_publisher``); the background worker embeds
        asynchronously. Ingestion never embeds inline (ADR-074).

        No-op when ``event_bus`` is None (CORE tier — gated at the composition
        root, so no queue-with-no-listener publishes and no dropped-event
        warnings), for NonKuDomain types, and for non-embeddable configs.
        """
        if self.event_bus is None or not isinstance(entity_type, EntityType):
            return
        config = ENTITY_CONFIGS.get(entity_type)
        if config is None or not config.embeddable:
            return

        from core.events.embedding_publisher import publish_embedding_requested

        for entity_data in entities:
            await publish_embedding_requested(self.event_bus, entity_type, entity_data, self.logger)

    async def _chunk_entity_content(
        self,
        uid: str,
        content_body: str,
        file_format: str,
        source_path: str,
        params: ChunkingParams,
        *,
        preserve_entity_body: bool = False,
    ) -> bool:
        """
        The shared body-chunk step — both ingest doors, all
        ``chunks_body_content`` entity types (PathStep, Ku), plus non-private
        knowledge UserEntries (canon P3 — additive substrate, body NOT popped).

        ``preserve_entity_body=True`` (UserEntry) keeps the inline
        ``Entity.content`` property intact — it stays load-bearing for
        /gradebook and the journal digest; the chunk subtree is purely
        additive. Default ``False`` follows the popped-body contract
        (Ku/PathStep): persisting the subtree also clears any legacy inline
        body so no stale copy can be served.

        Chunk the popped content body, persist it as :Content + :ContentChunk
        nodes, and publish ``ChunkEmbeddingRequested`` for the background
        worker. Body-content semantics live in CHUNK embeddings; the entity
        vector covers frontmatter fields only (ADR-074).

        Failures never fail ingestion — chunks can be regenerated later.
        Chunking and persistence run in CORE too (Analog behavior); only the
        embedding publish is tier-gated (``event_bus`` None → no publish).

        An empty body takes the explicit clear path instead (ADR-074): an
        entity re-ingested with its body emptied must not keep the previous
        body's :Content/:ContentChunk subtree serving stale chunk vectors.
        Clearing needs only the content adapter, so it runs chunker or not.

        Returns whether chunks were generated (persisted when the content
        adapter is wired; in-memory only otherwise).
        """
        if not content_body:
            if self.content_adapter:
                await self.content_adapter.delete_content_subtree(uid)
            return False
        if not self.chunking:
            return False

        chunk_result = self.chunking.process_content_for_ingestion(
            parent_uid=uid,
            content_body=content_body,
            format=file_format,
            source_path=source_path,
            params=params,
        )

        if chunk_result.is_error:
            # Log warning but don't fail ingestion - chunks can be regenerated later
            self.logger.warning(
                f"Failed to generate chunks for {uid}: {chunk_result.expect_error().message}"
            )
            return False

        content, _metadata = chunk_result.value
        self.logger.info(
            f"Generated {content.chunk_count} chunks for {uid} ({content.word_count} words)"
        )

        if not self.content_adapter:
            # Chunks generated in-memory but not persisted — flag for the caller.
            return True

        # Persist chunks to Neo4j so retrieval can target them
        stored = await self.content_adapter.store_content_with_chunks(
            uid, content, clear_inline_body=not preserve_entity_body
        )
        if not stored:
            self.logger.warning(f"Chunk persistence failed for {uid}")
            return False

        # Request async embedding generation for the persisted chunks
        if self.event_bus and content.chunks:
            from datetime import datetime

            from core.events import ChunkEmbeddingRequested, publish_event

            await publish_event(
                self.event_bus,
                ChunkEmbeddingRequested(
                    parent_uid=uid,
                    chunk_uids=tuple(c.chunk_id for c in content.chunks),
                    chunk_texts=tuple(c.context_window for c in content.chunks),
                    requested_at=datetime.now(),
                ),
                self.logger,
            )
        return True

    async def _ingest_post_persist(
        self,
        entity_type: EntityType | NonKuDomain,
        entities: list[dict[str, Any]],
        chunk_sources: dict[str, ChunkSource],
    ) -> None:
        """
        Batch-door post-persist step: embedding publishes + body chunking.

        Passed to ``batch.ingest_directory`` as ``post_persist_fn``, invoked
        per successful per-type upsert. Mirrors ``ingest_file``'s post-persist
        sequence: entity ``*EmbeddingRequested`` publishes first, then the
        shared chunk step for each ``chunks_body_content`` entity whose
        content the engine popped pre-upsert (``chunk_sources`` is empty for
        every other type).
        """
        await self._publish_embedding_requests(entity_type, entities)
        params = resolve_chunking_params(entity_type)
        for uid, source in chunk_sources.items():
            await self._chunk_entity_content(
                uid, source.content, source.file_format, source.source_path, params
            )

    # ========================================================================
    # MOC EDGE PASS — ``moc: true`` body links → ORGANIZES edges
    # ========================================================================

    async def _apply_moc_links(
        self,
        entity_uid: str,
        link_suffixes: list[str],
        file_path: Path,
        protected_target_uids: list[str] | None = None,
    ) -> list[str]:
        """The MOC edge pass (resolve half): body links → ordered ORGANIZES edges.

        ``moc: true`` on any ingestible file has exactly one effect — this pass.
        Each extracted link suffix is resolved against the tracker's path→uid
        mapping (``IngestionMetadata``), scoped to the vault that governs the
        MOC file; resolved targets become ``(moc)-[:ORGANIZES {order}]->(target)``
        edges with ``order`` = document position. The write is a full refresh:
        edges for links removed from the body are deleted (mirrors how
        rel-config ``order_property`` values refresh on re-ingest).

        MOC identity stays emergent — nothing reads the ``moc`` node property;
        this pass runs off the frontmatter at ingestion time only, so dangling
        links fill in when the MOC file is next re-ingested (edit or --force).

        Unresolved links are posture-dependent: PERSONAL vaults skip silently
        (a MOC names territory before content exists — dangling links are
        plans, not errors); the CONTENT vault gets warnings (returned for the
        sync stats). No registry → personal posture, unscoped resolution
        (tests / minimal composes).

        ``protected_target_uids`` (the file's own ``organizes:`` frontmatter
        targets, normalized): the refresh's stale-delete spares these — the
        rel-config authoring surface and the body-link surface coexist on one
        file without the MOC pass erasing the frontmatter-authored edges.

        Backend: IngestionWriteBackend.resolve_path_suffixes /
        refresh_moc_organizes.
        """
        root_prefix: str | None = None
        content_posture = False
        if self.vault_registry is not None:
            descriptor = self.vault_registry.resolve_by_path(file_path, self.default_user_uid)
            if descriptor.is_ok:
                root_prefix = str(descriptor.value.root.resolve())
                content_posture = descriptor.value.kind is VaultKind.CONTENT

        resolved_by_suffix: dict[str, str] = {}
        if link_suffixes:
            rows = await self._write_backend.resolve_path_suffixes(link_suffixes, root_prefix)
            # Same basename in two folders → multiple rows for one suffix.
            # Deterministic winner: shortest path, then lexicographic (closest
            # to Obsidian's shortest-path link resolution).
            candidates: dict[str, list[tuple[int, str, str]]] = {}
            for row in rows:
                path = str(row["file_path"])
                candidates.setdefault(str(row["suffix"]), []).append(
                    (len(path), path, str(row["entity_uid"]))
                )
            for suffix, matches in candidates.items():
                resolved_by_suffix[suffix] = min(matches)[2]

        target_uids: list[str] = []
        for suffix in link_suffixes:
            uid = resolved_by_suffix.get(suffix)
            # Self-links are dropped (a MOC linking itself draws nothing);
            # two links resolving to one entity keep the first position.
            if uid is not None and uid != entity_uid and uid not in target_uids:
                target_uids.append(uid)

        edges = await self._write_backend.refresh_moc_organizes(
            entity_uid, target_uids, protected_target_uids or []
        )

        unresolved = [s for s in link_suffixes if s not in resolved_by_suffix]
        self.logger.info(
            f"MOC edge pass for {entity_uid}: {edges} ORGANIZES edges "
            f"({len(target_uids)} resolved, {len(unresolved)} unresolved of "
            f"{len(link_suffixes)} links)"
        )
        if content_posture and unresolved:
            return [
                f"{entity_uid}: MOC link target '{suffix}' does not resolve to an "
                "ingested entity — ORGANIZES edge not created"
                for suffix in unresolved
            ]
        return []

    async def _resolve_prior_user_entry_uid(self, file_path: Path, user_uid: UserUID) -> str | None:
        """Path-keyed identity: the tracker's prior uid for a vault UserEntry file.

        A uid-less knowledge note mints a random ``ue_`` uid on first sync; the
        tracker's ``IngestionMetadata`` path→uid row lets every later sync reuse
        it so the note upserts in place instead of orphaning the old node
        (contract: docs/roadmap/done/uidless-vault-entry-identity-upsert.md). Both ingest
        doors converge on ``ingest_file``'s USER_ENTRY branch, so this single
        lookup covers the reconciler sync path and the direct door alike.

        The tracker row is keyed by **path**, so a file previously ingested as a
        different entity type (or an edge) and later re-typed to ``user_entry``
        without an authored uid would carry that FOREIGN identity (e.g. a
        ``ku.*`` node uid or an ``edge:`` identity). Reuse it only after
        confirming it still names a ``:UserEntry`` owned by this user — otherwise
        mint fresh. Without this guard a foreign uid would either collide with
        the ``:Entity.uid`` uniqueness constraint (failing every sync) or, for an
        ``edge:`` identity that names no node, create a ``:UserEntry`` with an
        edge id.

        Returns None when no tracker/service is wired (minimal composes / tests),
        the file is new, or the tracked uid is not this user's UserEntry — all
        fall back to minting a fresh uid. The gating that protects turn-in files
        and uploads lives in ``build_user_entry_request``; this method only
        supplies a validated candidate.
        """
        if self.ingestion_backend is None or self.user_entry_service is None:
            return None
        tracker = IngestionTracker(self.ingestion_backend)
        meta_result = await tracker.get_ingestion_metadata([file_path])
        if meta_result.is_error:
            return None
        # One path queried → at most one row; take it regardless of key form.
        row = next(iter(meta_result.value.values()), None)
        if row is None:
            return None
        prior_uid = str(row.entity_uid)
        # Label + ownership guard: get_entry reads through the UserEntry-scoped
        # backend (MATCH on :UserEntry), so a foreign uid / edge identity → None.
        existing = await self.user_entry_service.get_entry(prior_uid, user_uid)
        if existing.is_error or existing.value is None:
            return None
        return prior_uid

    # ========================================================================
    # SINGLE FILE INGESTION
    # ========================================================================

    @with_error_handling("ingest_file", error_type="system")
    async def ingest_file(
        self,
        file_path: Path,
        *,
        user_uid: UserUID | None = None,
        defer_moc_pass: bool = False,
    ) -> Result[dict[str, Any]]:
        """
        Ingest a single file (MD or YAML) into Neo4j.

        Auto-detects format and entity type, normalizes UID,
        and persists using BulkUpsertBackend. If the file declares
        type: Edge, it is ingested as a relationship instead of a node.

        Intentional seam vs. ``batch.parse_file_sync``: both run the same
        parse → validate → prepare pipeline (identical contract, one preparer);
        the remaining divergence is the error channel only — this path returns
        ``Result``, while the batch path reports per-file ``IngestionError``
        dicts the batch aggregates.

        Args:
            file_path: Path to file to ingest
            user_uid: Override user UID for multi-tenant entities.
                      If not provided, uses self.default_user_uid.
            defer_moc_pass: When True (the directory/batch door), a
                      ``moc: true`` file's ORGANIZES edge pass is NOT run
                      inline — the batch applies it end-of-sync, after
                      IngestionMetadata rows land, so same-sync link targets
                      resolve. Direct callers keep the default (inline).

        Returns:
            Result with ingestion details including uid, title, entity_type
        """
        if not file_path.exists():
            return Result.fail(Errors.not_found(f"File not found: {file_path}"))

        # ingest_file is the direct entry point for /api/ingest/file (and a
        # belt-and-suspenders for the per-file directory path), so the vault
        # exclusions must be enforced here too — otherwise a single file could
        # bypass the collect_files scan filters. One predicate covers symlinks,
        # the je_* staging floor, and the fail-closed allowlist. The wall is the
        # one governing THIS file's vault (descriptor-resolved), so a content
        # file gets the content staging floor rather than the personal wall —
        # consistent with the directory / reconciler paths.
        if not is_ingestible_path(file_path, self._resolve_allowlist(file_path, None)):
            # je_pro consent skips get the actionable hint (one frontmatter
            # line away from ingesting); path-wall rejects keep the generic
            # boundary message.
            je_pro_reason = je_pro_skip_reason(file_path) if "je_pro" in file_path.parts else None
            if je_pro_reason is not None:
                return Result.fail(
                    Errors.validation(
                        f"je_pro file not ingested: {je_pro_reason}",
                        field="path",
                    )
                )
            return Result.fail(
                Errors.validation(
                    "File is excluded by the vault sync boundary (symlink, je_* "
                    f"staging folder, or outside the allowlist): {file_path}",
                    field="path",
                )
            )

        # Detect format
        file_format = detect_format(file_path)

        # Parse file
        if file_format == "markdown":
            parse_result = parse_markdown(file_path, self.max_file_size_bytes)
            if parse_result.is_error:
                return Result.fail(parse_result)
            data, body = parse_result.value
        else:  # yaml
            yaml_result = parse_yaml(file_path, self.max_file_size_bytes)
            if yaml_result.is_error:
                return Result.fail(yaml_result)
            data = yaml_result.value
            body = None

        # Check for edge type BEFORE entity type detection
        if is_edge_type(data):
            validation = validate_edge_data(data)
            if validation.is_error:
                return Result.fail(validation)
            prepared = prepare_edge_data(data, file_path)
            return await self.ingest_edge(prepared)

        # Detect domain type (returns EntityType/NonKuDomain enum - type-safe!)
        entity_type = detect_entity_type(data, file_path)
        config = ENTITY_CONFIGS.get(entity_type)
        if not config:
            return Result.fail(
                Errors.validation(
                    f"Unsupported entity type: {entity_type.value}",
                    field="type",
                )
            )

        # UserEntry has its own creation pipeline (audience resolution,
        # Interaction audit, TRANSFORMS edges, compensation delete) that the
        # bulk engine cannot replicate. Route through UserEntryService so
        # /upload and /submit share every downstream step.
        if entity_type == EntityType.USER_ENTRY:
            if self.user_entry_service is None:
                return Result.fail(
                    Errors.system(
                        "UserEntry ingestion requires user_entry_service "
                        "to be wired into UnifiedIngestionService.",
                        operation="ingest_user_entry",
                    )
                )
            effective_user_uid = self._resolve_owner(file_path, user_uid)
            # Path-keyed identity for uid-less vault notes: reuse the tracker's
            # prior uid so re-syncs upsert in place instead of orphaning the old
            # node. Hard-gated inside build_user_entry_request (authored uid
            # wins; turn-ins and uploads never honor it).
            prior_uid = await self._resolve_prior_user_entry_uid(file_path, effective_user_uid)
            ue_result = await ingest_user_entry(
                data=data,
                file_path=file_path,
                user_uid=effective_user_uid,
                user_entry_service=self.user_entry_service,
                user_service=self.user_service,
                body=body,
                user_entry_processor=self.user_entry_processor,
                prior_uid=prior_uid,
            )
            # MOC edge pass — the user-entry door bypasses prepare_entity_data,
            # so link extraction happens here. The batch door defers to
            # end-of-sync (same-sync targets need their metadata rows first).
            if ue_result.is_ok and data.get("moc") is True and not defer_moc_pass:
                ue_moc_warnings = await self._apply_moc_links(
                    str(ue_result.value["uid"]), extract_moc_link_suffixes(body), file_path
                )
                if ue_moc_warnings:
                    ue_result.value["moc_warnings"] = ue_moc_warnings
            # Chunk substrate for companion retrieval (canon P3): non-private
            # knowledge notes get :ContentChunk children; everything else takes
            # the shared step's explicit clear path (empty body → subtree
            # delete), so a pipeline- or private-flip retracts stale chunks on
            # the next sync — unconditionally, per synced file. Deliberately
            # NOT a ``chunks_body_content`` config: the body stays on
            # ``UserEntry.content`` (load-bearing); chunks are additive.
            if ue_result.is_ok:
                chunkable = ue_result.value.get(
                    "pipeline"
                ) == Pipeline.KNOWLEDGE.value and not ue_result.value.get("private")
                # Explicit ``content:`` wins even when falsy — same resolution
                # build_user_entry_request applies to the persisted content.
                effective_content = data.get("content", body)
                ue_result.value["chunks_generated"] = await self._chunk_entity_content(
                    str(ue_result.value["uid"]),
                    str(effective_content or "") if chunkable else "",
                    file_format,
                    str(file_path),
                    resolve_chunking_params(EntityType.USER_ENTRY),
                    preserve_entity_body=True,
                )
            return ue_result

        # Validate UID format before preparation (early fail-fast)
        uid_result = validate_uid_format(entity_type, data, file_path)
        if uid_result.is_error:
            return Result.fail(uid_result)

        # Validate required fields before preparation (early fail-fast)
        validation_result = validate_required_fields(entity_type, data, file_path)
        if validation_result.is_error:
            return Result.fail(validation_result)

        # Prepare entity data (one sync path for both ingest doors — ADR-074).
        # Owner is descriptor-derived from the file's vault (surface-independent);
        # only requires_user_uid types persist it, SHARED curriculum drops it.
        effective_user_uid = self._resolve_owner(file_path, user_uid)
        try:
            entity_data = prepare_entity_data(
                entity_type,
                data,
                body,
                file_path,
                effective_user_uid,
                owner_is_authoritative=self._owner_is_authoritative,
            )
        except ValueError as e:
            # Content faults the preparer raises (blank ``uid:``, colon-spelled
            # relationship targets) are the file author's to fix — a validation
            # failure (HTTP 400), not a system error. Without this, the method's
            # ``@with_error_handling(error_type="system")`` wrapper would turn
            # an authoring mistake into a 500. Mirrors the batch door, where
            # "preparation" is a content-fault stage.
            return Result.fail(
                Errors.validation(str(e), user_message=f"File {file_path.name}: {e}")
            )

        # Validate entity data after preparation (ensures auto-generated fields present)
        validation_result = validate_entity_data(entity_type, entity_data, file_path)
        if validation_result.is_error:
            return Result.fail(validation_result)

        # MOC edge pass input (``moc: true`` files): the transient link-suffix
        # list must never persist as a node property — pop before the upsert,
        # apply after (the plain ``moc`` field itself stays, inert).
        moc_link_suffixes: list[str] | None = entity_data.pop("_moc_links", None)

        # For chunks_body_content types (PathStep, Ku): pop content before
        # Neo4j storage — content lives on the :Content node, not the :Entity
        # node. word_count is written unconditionally: the bulk upsert
        # (`n += props`) never removes omitted keys, so an emptied body must
        # overwrite the previous ingest's count with 0 (ADR-074 clear path).
        chunk_content_body = ""
        if config.chunks_body_content:
            # `or ""` — frontmatter `content:` with no value parses to None
            chunk_content_body = entity_data.pop("content", "") or ""
            entity_data["word_count"] = len(chunk_content_body.split())

        # Ingest with relationships (node upsert + edge creation below the boundary)
        rel_config = config.relationship_config or {}
        result = await self._bulk_backend.upsert_with_relationships(
            entity_label=config.entity_label,
            base_label=config.base_label,
            entities=[entity_data],
            relationship_config=rel_config,
        )

        if result.is_error:
            return Result.fail(result)

        stats = result.value
        self.logger.info(f"Ingested {entity_type.value}: {entity_data['uid']}")

        # Frontmatter retraction + the file's tracker stamp — one identity per
        # file, shared with the directory door: the edges this file authored at
        # its previous ingest but omits now are deleted, then its row
        # records the new fingerprint (so the directory door sees the file as
        # ingested and diffs against the same row). Runs BEFORE the MOC pass so
        # a target dropped from ``organizes:`` but still body-linked is
        # re-MERGEd inside this call. A failed retraction is loud: the entity
        # and its new edges landed, but the graph would otherwise keep an edge
        # the file has dropped, with nothing left to retry it. Without a
        # tracker (minimal composes) there is no prior to diff and no stamp.
        source_uid = str(entity_data["uid"])
        authored_edges = authored_edge_fingerprint(entity_data, rel_config)
        if self.ingestion_backend is not None:
            tracker = IngestionTracker(self.ingestion_backend)
            prior_result = await tracker.get_authored_edges([file_path])
            if prior_result.is_error:
                return Result.fail(prior_result)
            dropped = retracted_edges(prior_result.value.get(str(file_path), []), authored_edges)
            if dropped:
                try:
                    deleted = await self._write_backend.delete_authored_edges(source_uid, dropped)
                except NEO4J_EXCEPTIONS as e:
                    return Result.fail(
                        Errors.database(
                            "ingest_file",
                            f"Failed to retract {len(dropped)} frontmatter edge(s) "
                            f"{source_uid} no longer declares: {e}",
                        )
                    )
                self.logger.info(
                    f"Retracted {deleted} frontmatter edge(s) {source_uid} no longer declares "
                    f"({len(dropped)} dropped from its registered fields)"
                )
            # A stamp failure is logged by the tracker; the entity write stands
            # and the row keeps its prior fingerprint (a superset — re-diffed on
            # the next ingest, where an already-deleted edge matches nothing).
            await tracker.update_ingestion_metadata(
                file_path,
                EntityUID(source_uid),
                tracker.compute_file_hash(file_path),
                authored_edges,
            )

        # Groups need an OWNS edge from the teacher to the group (ADR-053).
        # The engine created only the :Group node; wire ownership here.
        if entity_type == NonKuDomain.GROUP:
            owner_uid = entity_data.get("owner_uid")
            if owner_uid:
                try:
                    await self._write_backend.create_group_ownership(owner_uid, entity_data["uid"])
                except NEO4J_EXCEPTIONS as e:
                    self.logger.warning(
                        f"Failed to create OWNS edge for group {entity_data['uid']}: {e}"
                    )

        # Post-persist embedding step (ADR-074): publish the entity's
        # *EmbeddingRequested event for the background worker. For chunked
        # types the content body was popped above and is deliberately NOT
        # re-attached: the entity vector covers frontmatter fields;
        # body-content semantics live in CHUNK embeddings (below) — one
        # consistent recipe across ingest, in-app update, and backfill triggers.
        await self._publish_embedding_requests(entity_type, [entity_data])

        # Chunk the popped content body — the same shared step the batch
        # door runs (chunk → :Content/:ContentChunk persist → chunk-embedding
        # publish), so both doors produce the same content shape.
        chunks_generated = False
        if config.chunks_body_content:
            chunks_generated = await self._chunk_entity_content(
                entity_data["uid"],
                chunk_content_body,
                file_format,
                str(file_path),
                resolve_chunking_params(entity_type),
            )

        # MOC edge pass (inline for the direct single-file door; the batch
        # door defers to end-of-sync so same-sync targets resolve). The file's
        # own ``organizes:`` frontmatter targets are protected from the
        # stale-edge refresh — both authoring surfaces coexist.
        moc_warnings: list[str] = []
        if moc_link_suffixes is not None and not defer_moc_pass:
            moc_warnings = await self._apply_moc_links(
                str(entity_data["uid"]),
                moc_link_suffixes,
                file_path,
                frontmatter_organizes_targets(entity_data),
            )

        result_payload: dict[str, Any] = {
            "uid": entity_data["uid"],
            "title": entity_data.get("title") or entity_data.get("name"),
            "entity_type": entity_type.value,  # Serialize as string for JSON
            "format": file_format,
            "success": True,
            "nodes_created": stats.nodes_created,
            "nodes_updated": stats.nodes_updated,
            "relationships_created": stats.relationships_created,
            "chunks_generated": chunks_generated,  # Track whether chunking succeeded
        }
        if moc_warnings:
            result_payload["moc_warnings"] = moc_warnings
        return Result.ok(result_payload)

    # ========================================================================
    # BATCH OPERATIONS - Delegate to batch module
    # ========================================================================

    async def ingest_directory(
        self,
        directory: Path,
        pattern: str = "*",
        batch_size: int = 500,
        max_concurrent: int = 20,
        ingestion_mode: Literal["full", "incremental", "smart"] = "full",
        force: bool = False,
        validate_targets: bool = False,
        dry_run: bool = False,
        *,
        user_uid: UserUID | None = None,
        allowlist: SyncAllowlist | None = None,
    ) -> Result[IngestionStats | IncrementalStats | DryRunPreview]:
        """
        Ingest all supported files in a directory.

        Args:
            directory: Directory to scan
            pattern: Glob pattern for files (default: "*" for all supported)
            batch_size: Batch size for bulk operations
            max_concurrent: Maximum concurrent file parsing operations
            ingestion_mode: Ingestion strategy:
                - "full": Process all files (default)
                - "incremental": Skip files with unchanged content hash
                - "smart": Skip files with unchanged mtime (fast), verify with hash if changed
            force: Re-process every surviving file regardless of the
                IngestionMetadata hash/mtime match. Force ≠ full: a force run
                keeps tracked-mode semantics — the fail-closed allowlist,
                metadata re-stamping, and deletion reconciliation all stay
                active — so it is the sanctioned re-chunk/migration path.
                A "full"-mode request with force is coerced to "smart".
            validate_targets: If True, validate relationship targets exist before ingestion
            dry_run: If True, validates and previews changes without writing to Neo4j

        Returns:
            Result with IngestionStats (full mode), IncrementalStats (incremental/smart mode), or DryRunPreview (dry-run mode)

        Delegates to batch.ingest_directory.

        USER_ENTRY files are routed through ``self.ingest_file`` (per-file
        pipeline) instead of the bulk upsert engine so the OWNS edge, audience
        resolution, and post-persist extraction (EXTRACT_ACTIVITIES) all run.

        The fail-closed folder allowlist is applied to every scan here — the
        single chokepoint every ingestion door traverses — so a vault wall cannot
        be bypassed by any caller. ``allowlist`` selects which wall: the
        descriptor-driven reconciler passes the target vault's own allowlist; the
        residual per-file/domain doors fall back to ``self.sync_allowlist`` (the
        personal vault's wall). Files under the governed vault root are ingested
        only if they sit under an allowed dir.

        When the wall governs ``directory``, a ``full``-mode request is upgraded to
        ``smart``: full mode skips deletion reconciliation, but fail-closed
        retraction of now-walled rows depends on it, so the wall would otherwise
        leak on a full-mode ingest.
        """
        # A directory scan attributes ONE owner and ONE wall (below) to the whole
        # batch, so it is sound only if every file it may collect resolves by-path
        # to the same vault as the directory. Reject a scan that nests a vault
        # resolving to a DIFFERENT kind — an ancestor scan (roots differ) or a
        # personal vault nested inside a content scan (its private files would be
        # stamped with the content owner). A combined vault (content nested inside
        # personal → same personal descriptor) is uniform and allowed, so the
        # normal nested-config personal sync is never broken.
        if self.vault_registry is not None:
            acting_hint = user_uid or self.default_user_uid
            conflicting = self.vault_registry.conflicting_nested_roots(directory, acting_hint)
            if conflicting:
                return Result.fail(
                    Errors.validation(
                        "Directory scan would sweep a nested vault with a different "
                        f"owner (nested vault root(s): {', '.join(str(r) for r in conflicting)}); "
                        "scan a single vault root instead.",
                        field="directory",
                    )
                )

        # Resolve the owner from the vault governing ``directory`` — the same
        # chokepoint ingest_file uses, but applied here because the bulk upsert
        # engine (which handles every USER_OWNED activity type) stamps this owner
        # directly and never passes through ingest_file. Without this, a content-
        # vault Task ingested via the dashboard would be owned by the acting admin
        # instead of the content acts-as account. The single-vault guard above
        # makes this per-directory owner equivalent to per-file resolution.
        # USER_ENTRY files re-resolve per-path in ingest_file (same answer);
        # curriculum drops the owner.
        effective_user_uid = self._resolve_owner(directory, user_uid)
        effective_allowlist = self._resolve_allowlist(directory, allowlist)

        effective_mode = ingestion_mode
        if force and ingestion_mode == "full":
            # Force means "re-process unchanged files", which only has meaning
            # under tracked ingestion — coerce to smart so the tracker, the
            # wall, and deletion reconciliation all stay active (force ≠ full).
            effective_mode = "smart"
        if (
            effective_mode == "full"
            and self.ingestion_backend is not None
            and effective_allowlist is not None
            and effective_allowlist.governs(directory)
        ):
            self.logger.info(
                "Vault wall governs %s — upgrading full → smart ingestion so deletion "
                "reconciliation retracts now-walled entries",
                directory,
            )
            effective_mode = "smart"

        async def _ingest_file_for_batch(path: Path) -> Result[Any]:
            # defer_moc_pass: the batch applies MOC edge passes end-of-sync
            # (after IngestionMetadata rows land) so same-sync targets resolve.
            return await self.ingest_file(path, user_uid=effective_user_uid, defer_moc_pass=True)

        return await ingest_directory(
            directory=directory,
            write_backend=self._write_backend,
            bulk_backend=self._bulk_backend,
            ingestion_backend=self.ingestion_backend,
            pattern=pattern,
            batch_size=batch_size,
            max_concurrent=max_concurrent,
            default_user_uid=effective_user_uid,
            max_file_size_bytes=self.max_file_size_bytes,
            ingestion_mode=effective_mode,
            force=force,
            validate_targets=validate_targets,
            dry_run=dry_run,
            ingest_file_fn=_ingest_file_for_batch,
            allowlist=effective_allowlist,
            owner_is_authoritative=self._owner_is_authoritative,
            post_persist_fn=self._ingest_post_persist,
            moc_pass_fn=self._apply_moc_links,
        )

    async def ingest_vault(
        self,
        vault_path: Path,
        subdirs: list[str] | None = None,
        *,
        user_uid: UserUID | None = None,
    ) -> Result[IngestionStats]:
        """
        Ingest an entire Obsidian vault or specific subdirectories.

        Delegates to batch.ingest_vault.
        """
        return await ingest_vault(
            vault_path=vault_path,
            ingest_directory_fn=self.ingest_directory,
            subdirs=subdirs,
            user_uid=user_uid or self.default_user_uid,
        )

    async def ingest_bundle(
        self, bundle_path: Path, *, user_uid: UserUID | None = None
    ) -> Result[BundleStats]:
        """
        Ingest a domain bundle using manifest file.

        Delegates to batch.ingest_bundle.

        ``user_uid`` is an acting-user hint threaded to each file's ``ingest_file``
        (symmetry with the other ingest doors — ADR-070). The real owner of any
        USER_OWNED entity is still resolved from the vault descriptor for its path;
        the hint only governs the fallback when no vault registry is wired.
        """

        def _find_entity_file_with_size(bp: Path, uid: str) -> Path | None:
            return find_entity_file(bp, uid, self.max_file_size_bytes)

        def _parse_yaml(file_path: Path) -> Result[dict[str, Any]]:
            return parse_yaml(file_path, self.max_file_size_bytes)

        async def _ingest_file(file_path: Path) -> Result[dict[str, Any]]:
            return await self.ingest_file(file_path, user_uid=user_uid)

        return await ingest_bundle(
            bundle_path=bundle_path,
            parse_yaml_fn=_parse_yaml,
            ingest_file_fn=_ingest_file,
            find_entity_file_fn=_find_entity_file_with_size,
        )

    # ========================================================================
    # VALIDATION - Delegate to validator module
    # ========================================================================

    async def validate_file(self, file_path: Path) -> Result[ValidationResult]:
        """
        Validate a file without persisting to Neo4j (dry-run mode).

        Delegates to validator.validate_file.
        """
        return await validate_file(
            file_path=file_path,
            default_user_uid=self.default_user_uid,
            max_file_size_bytes=self.max_file_size_bytes,
        )

    async def validate_directory(
        self,
        directory: Path,
        pattern: str = "*",
        max_concurrent: int = 20,
    ) -> Result[DirectoryValidationResult]:
        """
        Validate all files in a directory without persisting (dry-run mode).

        Delegates to validator.validate_directory.
        """
        return await validate_directory(
            directory=directory,
            pattern=pattern,
            max_concurrent=max_concurrent,
            default_user_uid=self.default_user_uid,
            max_file_size_bytes=self.max_file_size_bytes,
        )
