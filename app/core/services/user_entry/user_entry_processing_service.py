"""
UserEntryProcessingService — ADR-054
====================================

Pipeline dispatcher for ``UserEntry``. Reads ``entry.pipeline`` and routes
to the matching processor:

    Pipeline.NONE                     → no-op (already complete)
    Pipeline.TEACHER_REVIEW           → no-op (waits on teacher queue)
    Pipeline.TRANSCRIBE               → Deepgram audio → transcript
    Pipeline.LLM_SUMMARY              → LLM summarization of text/processed content
    Pipeline.TRANSCRIBE_AND_STRUCTURE → transcribe + LLM structuring (two entries)
    Pipeline.EXTRACT_ACTIVITIES       → DSL parse → real entities with
                                        EXTRACTED_FROM provenance (ADR-069)

TRANSCRIBE_AND_STRUCTURE produces a second ``UserEntry`` carrying the
LLM-structured output, linked back to the source with a ``TRANSFORMS``
edge (wired via ``UserEntryCreateRequest.transforms_of_uid`` on the
facade).

EXTRACT_ACTIVITIES is Analog-complete: the DSL parser runs over hand-tagged
``@context(...)`` lines with no API keys; on FULL tier an optional LLM
bridge pre-pass tags untagged prose first and degrades to parser-only when
the bridge call fails (ADR-069 Decision 1 — extraction joins the unified
ingestion path; the ADR-054-retired submission-metadata flow stays retired).
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.events import publish_event
from core.events.knowledge_substance_events import KnowledgeReflectedInEntry
from core.events.user_entry_events import (
    UserEntryProcessingCompleted,
    UserEntryProcessingFailed,
    UserEntryProcessingStarted,
)
from core.models.enums.entity_enums import EntityStatus
from core.models.enums.metadata_enums import Visibility
from core.models.enums.pipeline import Pipeline
from core.models.enums.user_entry_enums import EnrichmentMode
from core.models.relationship_names import RelationshipName
from core.models.user_entry.user_entry import UserEntry
from core.models.user_entry.user_entry_request import UserEntryCreateRequest
from core.services.dsl.activity_extractor import (
    USER_OWNED_DEDUP_LABELS,
    ExtractedByVaultId,
    normalized_line_hash,
    semantic_dedup_key,
)
from core.services.dsl.grounding import active_goal_titles as fetch_active_goal_titles
from core.services.dsl.grounding import goals_as_context
from core.utils.exception_types import FILE_IO_EXCEPTIONS, LLM_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports.infrastructure_protocols import EventBusOperations
    from core.ports.transcription_protocols import TranscriptionPort
    from core.services.dsl.activity_extractor import ActivityExtractorService
    from core.services.dsl.llm_dsl_bridge import LLMDSLBridgeService
    from core.services.goals_service import GoalsService
    from core.services.llm_caller import UnifiedLLMCaller
    from core.services.output.instruction_resolver import InstructionResolver
    from core.services.user_entry.user_entry_service import UserEntryService
    from core.services.user_service import UserService

# Matches any markdown checkbox line (ADR-070 double-extraction guard).
_CHECKBOX_RE = re.compile(r"^[-*]\s*\[[xX ]?\]")


class UserEntryProcessingService:
    """Pipeline dispatcher for ``UserEntry``.

    Composes ``UserEntryService`` with the transcription and LLM
    adapters so every pipeline branch can run without routing through
    the legacy ``SubmissionsProcessingService`` / ``JournalOutputService``.
    """

    def __init__(
        self,
        entry_service: UserEntryService,
        transcription_adapter: TranscriptionPort | None = None,
        llm_caller: UnifiedLLMCaller | None = None,
        instruction_resolver: InstructionResolver | None = None,
        event_bus: EventBusOperations | None = None,
        activity_extractor: ActivityExtractorService | None = None,
        dsl_bridge: LLMDSLBridgeService | None = None,
        user_service: UserService | None = None,
        goals_service: GoalsService | None = None,
    ) -> None:
        self.entry_service = entry_service
        self.transcription_adapter = transcription_adapter
        self.llm_caller = llm_caller
        self.instruction_resolver = instruction_resolver
        self.event_bus = event_bus
        self.activity_extractor = activity_extractor
        self.dsl_bridge = dsl_bridge
        self.user_service = user_service
        # Grounds the bridge pre-pass in the user's active goals — the same
        # grounding the inert journal "Suggested activities" panel uses, so the
        # entity-creating path and the preview path recognise prose against the
        # identical context (core.services.dsl.grounding). None → ungrounded.
        self.goals_service = goals_service
        self.logger = get_logger("skuel.services.user_entry.processing")

    # =========================================================================
    # DISPATCH
    # =========================================================================

    async def process(
        self,
        entry: UserEntry,
        instructions: str | None = None,
        force: bool = False,
    ) -> Result[UserEntry]:
        """Run ``entry.pipeline`` on ``entry``.

        Args:
            entry: The UserEntry to process.
            instructions: Per-run override for pipeline instructions
                (e.g., custom LLM prompt). Falls back to ``entry.instructions``.
            force: Re-run override for EXTRACT_ACTIVITIES — bypasses the
                completed-run guard (line-hash dedup still prevents
                duplicates).

        Returns:
            Result[UserEntry] — the (possibly updated) entry.
        """
        pipeline = entry.pipeline

        if pipeline in (
            Pipeline.NONE,
            Pipeline.TEACHER_REVIEW,
            Pipeline.REFERENCE,
            Pipeline.KNOWLEDGE,
        ):
            # REFERENCE: archive/training material — stored as-is, no processing.
            # KNOWLEDGE: developed vault notes — stored as-is; they inform
            # UserContext via retrieval, not via a processing pass.
            return Result.ok(entry)

        if pipeline == Pipeline.EXTRACT_ACTIVITIES:
            # Guard precedes _emit_started: a completed-run no-op is not a run.
            if self._extraction_already_completed(entry) and not force:
                self.logger.info(
                    f"EXTRACT_ACTIVITIES already completed for {entry.uid}; "
                    "no-op (pass force=True to re-run)"
                )
                return Result.ok(entry)
            await self._emit_started(entry)
            return await self._run_extract_activities(entry)

        await self._emit_started(entry)

        if pipeline == Pipeline.TRANSCRIBE:
            return await self._run_transcribe(entry)

        if pipeline == Pipeline.LLM_SUMMARY:
            return await self._run_llm_summary(entry, instructions)

        if pipeline == Pipeline.TRANSCRIBE_AND_STRUCTURE:
            return await self._run_transcribe_and_structure(entry, instructions)

        return Result.fail(
            Errors.validation(
                f"Unknown pipeline: {pipeline}",
                field="pipeline",
            )
        )

    # =========================================================================
    # TRANSCRIBE
    # =========================================================================

    async def _run_transcribe(self, entry: UserEntry) -> Result[UserEntry]:
        if self.transcription_adapter is None:
            return await self._fail(
                entry,
                Errors.integration(
                    service="deepgram",
                    message="DeepgramAdapter not configured for UserEntryProcessingService",
                ),
                phase="setup",
            )
        if not entry.file_path:
            return await self._fail(
                entry,
                Errors.validation(
                    "TRANSCRIBE pipeline requires entry.file_path",
                    field="file_path",
                ),
                phase="setup",
            )

        transcript = await self._transcribe(entry.file_path)
        if transcript.is_error:
            return await self._fail(entry, transcript.expect_error(), phase="transcribe")

        update_result = await self.entry_service.update_processed_content(
            uid=entry.uid,
            processed_content=transcript.value,
        )
        if update_result.is_error:
            return await self._fail(entry, update_result.expect_error(), phase="persist_transcript")

        updated = update_result.value
        await self._emit_completed(updated)
        return Result.ok(updated)

    # =========================================================================
    # LLM_SUMMARY
    # =========================================================================

    async def _run_llm_summary(
        self,
        entry: UserEntry,
        instructions: str | None,
    ) -> Result[UserEntry]:
        if self.llm_caller is None:
            return await self._fail(
                entry,
                Errors.business(
                    rule="llm_tier_required",
                    message=(
                        "Pipeline.LLM_SUMMARY requires INTELLIGENCE_TIER=full; "
                        "UnifiedLLMCaller is not configured."
                    ),
                ),
                phase="setup",
            )
        if self.instruction_resolver is None:
            return await self._fail(
                entry,
                Errors.system(
                    message="InstructionResolver not configured for UserEntryProcessingService",
                ),
                phase="setup",
            )

        source_text = entry.processed_content or entry.content
        if not source_text:
            return await self._fail(
                entry,
                Errors.validation(
                    "LLM_SUMMARY pipeline requires entry.content or entry.processed_content",
                    field="content",
                ),
                phase="setup",
            )

        llm_result = await self._generate(
            source_text,
            custom_instructions=self._apply_mode_addendum(
                instructions or entry.instructions, entry.journal_mode
            ),
            enrichment_mode=self._resolve_enrichment_mode(entry),
        )
        if llm_result.is_error:
            return await self._fail(entry, llm_result.expect_error(), phase="generate_summary")

        update_result = await self.entry_service.update_processed_content(
            uid=entry.uid,
            processed_content=llm_result.value,
        )
        if update_result.is_error:
            return await self._fail(entry, update_result.expect_error(), phase="persist_summary")

        updated = update_result.value
        await self._emit_completed(updated)
        return Result.ok(updated)

    # =========================================================================
    # TRANSCRIBE_AND_STRUCTURE
    # =========================================================================

    async def _run_transcribe_and_structure(
        self,
        entry: UserEntry,
        instructions: str | None,
    ) -> Result[UserEntry]:
        if self.transcription_adapter is None:
            return await self._fail(
                entry,
                Errors.integration(
                    service="deepgram",
                    message="DeepgramAdapter not configured for UserEntryProcessingService",
                ),
                phase="setup",
            )
        if self.llm_caller is None:
            return await self._fail(
                entry,
                Errors.business(
                    rule="llm_tier_required",
                    message=(
                        "Pipeline.TRANSCRIBE_AND_STRUCTURE requires INTELLIGENCE_TIER=full; "
                        "UnifiedLLMCaller is not configured."
                    ),
                ),
                phase="setup",
            )
        if self.instruction_resolver is None:
            return await self._fail(
                entry,
                Errors.system(
                    message="InstructionResolver not configured for UserEntryProcessingService",
                ),
                phase="setup",
            )
        if not entry.file_path:
            return await self._fail(
                entry,
                Errors.validation(
                    "TRANSCRIBE_AND_STRUCTURE pipeline requires entry.file_path",
                    field="file_path",
                ),
                phase="setup",
            )

        # Phase 1 — transcribe and store on the source entry
        transcript = await self._transcribe(entry.file_path)
        if transcript.is_error:
            return await self._fail(entry, transcript.expect_error(), phase="transcribe")

        update_source = await self.entry_service.update_processed_content(
            uid=entry.uid,
            processed_content=transcript.value,
        )
        if update_source.is_error:
            return await self._fail(entry, update_source.expect_error(), phase="update_source")
        updated_source = update_source.value

        # Phase 2 — LLM-structure the transcript
        structured = await self._generate(
            transcript.value,
            custom_instructions=self._apply_mode_addendum(
                instructions or entry.instructions, entry.journal_mode
            ),
            enrichment_mode=self._resolve_enrichment_mode(entry),
        )
        if structured.is_error:
            return await self._fail(updated_source, structured.expect_error(), phase="structure")

        # Phase 3 — persist the structured output as a second UserEntry.
        #
        # The child is PRIVATE and inherits no audience from the source
        # (ADR-054 §5: journal is private by policy; see
        # Pipeline.allows_sharing). The source itself is already on
        # pipeline=TRANSCRIBE_AND_STRUCTURE, so AudienceResolver.validate blocked
        # any explicit audience at submit time — the child is anchored to
        # the same norm rather than drifting to the default visibility.
        child_request = UserEntryCreateRequest(
            title=f"{entry.title} — structured",
            content=structured.value,
            pipeline=Pipeline.NONE,
            modality=entry.modality,
            transforms_of_uid=entry.uid,
            visibility=Visibility.PRIVATE,
            tags=list(entry.tags) if entry.tags else [],
        )
        child_result = await self.entry_service.create_entry(
            request=child_request,
            user_uid=entry.user_uid,
        )
        if child_result.is_error:
            return await self._fail(
                updated_source, child_result.expect_error(), phase="persist_child"
            )

        child, _share_outcome = child_result.value
        await self._emit_completed(updated_source, produced_entry_uid=child.uid)
        return Result.ok(updated_source)

    # =========================================================================
    # EXTRACT_ACTIVITIES (ADR-069)
    # =========================================================================

    @staticmethod
    def _extraction_already_completed(entry: UserEntry) -> bool:
        """Guard 1 of the three-guard idempotency: completed-run metadata."""
        summary = (entry.metadata or {}).get("activity_extraction")
        if isinstance(summary, str):
            # backend.update JSON-serializes nested dicts into string props.
            try:
                summary = json.loads(summary)
            except ValueError:
                return False
        return isinstance(summary, dict) and summary.get("status") == "completed"

    async def _run_extract_activities(self, entry: UserEntry) -> Result[UserEntry]:
        """DSL extraction: text → parsed Activity Lines → real entities.

        Analog-complete with graceful Digital enhancement:
        1. Optional bridge pre-pass (FULL tier) tags untagged prose; a bridge
           *failure* degrades to parser-only over the original text
           (ProgressReportGenerator precedent), a bridge *absence* is silent.
        2. Guards 2+3 of the three-guard idempotency: lines whose hash already
           has an EXTRACTED_FROM edge to this entry are skipped by the
           extractor (exact); bridge-generated lines whose (node label,
           normalized title) matches an entity already extracted from this
           entry MERGE instead of duplicating (semantic, R3 — the bridge
           rewords lines every run, so their hashes never repeat).
        3. Provenance: ``(created)-[:EXTRACTED_FROM {extracted_at,
           source_line_hash}]->(entry)`` batch write.
        4. Knowledge contract: ``(entry)-[:APPLIES_KNOWLEDGE]->(ku)`` for every
           created Ku and resolved ``@ku()`` reference — the substance/ZPD
           edge. Each successful write publishes ``KnowledgeReflectedInEntry``
           (substance fan-out) and feeds UserContext.entry_knowledge_applied
           + the ZPD entry_application signal on read.
        5. Run summary persisted under ``entry.metadata["activity_extraction"]``.
        """
        if self.activity_extractor is None:
            return await self._fail(
                entry,
                Errors.system(
                    message="ActivityExtractorService not configured for "
                    "UserEntryProcessingService",
                ),
                phase="setup",
            )

        source_text = entry.processed_content or entry.content
        if not source_text:
            return await self._fail(
                entry,
                Errors.validation(
                    "EXTRACT_ACTIVITIES pipeline requires entry.content or entry.processed_content",
                    field="content",
                ),
                phase="setup",
            )

        # --- Bridge pre-pass (optional Digital enhancement) ------------------
        # Periodic notes (daily/weekly/monthly) NEVER take the bridge: the
        # periodic-note parse contract (E3, docs/roadmap/done/
        # calendar-periodic-notes-arc.md) rules that entities come ONLY from
        # checkbox lines + explicit @context() markers — never inferred from
        # prose — so both tiers behave identically for periodic entries. The
        # bridge stays a sanctioned Digital enhancement for every other
        # EXTRACT_ACTIVITIES entry. One shared predicate
        # (UserEntry.is_periodic_note) — the same one the journals routes use.
        working_text = source_text
        bridge_error: str | None = None
        bridge_line_hashes: frozenset[str] = frozenset()
        if self.dsl_bridge is not None and not entry.is_periodic_note():
            # Strip checkbox lines before the LLM bridge: the obsidian-tasks
            # adapter owns them (ADR-070). Sending them to the bridge causes
            # double extraction — the LLM sees a task-shaped line and emits an
            # @context(task) annotation, then the parser ALSO parses the original
            # checkbox line, creating a duplicate Task on the same hash.
            bridge_text = "\n".join(
                ln for ln in source_text.splitlines() if not _CHECKBOX_RE.match(ln)
            )
            # Skip the bridge when the strip left nothing (a checkbox-only note):
            # the obsidian-tasks adapter owns those lines and there is no prose to
            # tag, so the goals query + LLM call would be pure waste. (Grounding
            # safety itself lives in the bridge: the active-goal context goes to a
            # separate, non-extractable {user_context} slot, so it can never
            # produce phantom entities regardless of this guard.) The Analog
            # parser still runs over the original checkbox text below.
            if bridge_text.strip():
                # Ground the pre-pass in the user's active goals through the
                # shared builder — recognition-only and soft, both stated once in
                # core.services.dsl.grounding.
                grounding_titles = await fetch_active_goal_titles(
                    self.goals_service, entry.user_uid
                )
                bridge_result = await self.dsl_bridge.transform_with_context(
                    bridge_text,
                    user_uid=entry.user_uid,
                    active_goals=goals_as_context(grounding_titles),
                )
                if bridge_result.is_error:
                    # Degrade, don't fail: the Analog parser still runs over the
                    # original text; tagged lines extract regardless.
                    bridge_error = str(bridge_result.expect_error())
                    self.logger.warning(
                        f"DSL bridge degraded to parser-only for {entry.uid}: {bridge_error}"
                    )
                elif bridge_result.value.activity_lines:
                    working_text = (
                        source_text
                        + "\n\n## Extracted Activities\n"
                        + "\n".join(bridge_result.value.activity_lines)
                    )
                    # Guard 3 eligibility (R3): only lines the bridge GENERATED
                    # this run are semantically deduped — user-typed lines keep
                    # exact Guard-2 semantics.
                    bridge_line_hashes = frozenset(
                        normalized_line_hash(line) for line in bridge_result.value.activity_lines
                    )

        # --- Existing-extraction read (guard 2 / 2b / 3 inputs) ---------------
        # Read on every run, not only under force: if a prior run wrote edges
        # but died before the metadata write, the next run must still dedup.
        # One query feeds three guards: exact line hashes (Guard 2), the 🆔s
        # already on this entry's edges (Guard 2b, identity — a line SKUEL has
        # written ``[x]`` + ``✅`` into no longer hashes to its edge, but its 🆔
        # still names it, ADR-070), and the semantic (node label, normalized
        # title) → uid map (Guard 3, R3).
        extracted_result = await self.entry_service.get_extracted_entities(entry.uid)
        if extracted_result.is_error:
            return await self._fail(entry, extracted_result.expect_error(), phase="read_provenance")
        extracted_rows = extracted_result.value or []
        existing_line_hashes = frozenset(
            line_hash for row in extracted_rows if (line_hash := row.get("source_line_hash"))
        )
        # Every edge per 🆔, not one: the duplicate-creation bug Guard 2b closes
        # left some 🆔s with two (the original task and its copy), and all of
        # them are the line's own — retired and refreshed together.
        edges_by_vault_id: dict[str, list[ExtractedByVaultId]] = {}
        for row in extracted_rows:
            if (vault_id := row.get("vault_id")) and row.get("entity_uid"):
                edges_by_vault_id.setdefault(vault_id, []).append(
                    ExtractedByVaultId(
                        entity_uid=row["entity_uid"],
                        source_line_hash=row.get("source_line_hash") or "",
                    )
                )
        existing_vault_ids = {
            vault_id: tuple(edges) for vault_id, edges in edges_by_vault_id.items()
        }
        existing_extracted: dict[tuple[str, str], str] = {}
        for row in extracted_rows:
            # Node label is the never-sniff-compliant type source; :Entity is
            # the shared base label, :Content the chunk-shadow label (G13).
            label = next(
                (lb for lb in row.get("labels", []) if lb not in ("Entity", "Content")), None
            )
            if label and row.get("title") and row.get("entity_uid"):
                existing_extracted[semantic_dedup_key(label, row["title"])] = row["entity_uid"]

        # --- User-wide active twins (Guard 4 input, cross-entry/F4) -----------
        # Rows are oldest-first; setdefault keeps the same winner the F4 fixer
        # keeps. A line matching an ACTIVE owned twin merges instead of
        # re-creating a node the cleanup deleted (resurrection guard).
        twins_result = await self.entry_service.get_user_active_extraction_twins(
            entry.user_uid, list(USER_OWNED_DEDUP_LABELS)
        )
        if twins_result.is_error:
            return await self._fail(entry, twins_result.expect_error(), phase="read_provenance")
        user_owned_semantic: dict[tuple[str, str], str] = {}
        for twin in twins_result.value or []:
            label = next((lb for lb in twin["labels"] if lb not in ("Entity", "Content")), None)
            if label and twin["title"] and twin["entity_uid"]:
                user_owned_semantic.setdefault(
                    semantic_dedup_key(label, twin["title"]), twin["entity_uid"]
                )

        # --- Existing APPLIES_KNOWLEDGE targets (substance idempotency) --------
        # The edge write below is MERGE-idempotent, but the substance event is
        # NOT — publishing KnowledgeReflectedInEntry for an edge that already
        # exists would double-count times_reflected_in_entries on a force re-run
        # or a crash-recovery retry. Read the already-linked Kus up front and
        # only emit the event for genuinely new links.
        applied_result = await self.entry_service.get_relationships(
            entry.uid, rel_type=RelationshipName.APPLIES_KNOWLEDGE, direction="outgoing"
        )
        if applied_result.is_error:
            return await self._fail(entry, applied_result.expect_error(), phase="read_provenance")
        already_applied_ku_uids = frozenset(
            target_uid
            for rel in applied_result.value or []
            if (target_uid := rel.get("target_uid"))
        )

        # --- Curriculum-creation gate (fail-closed) ---------------------------
        allow_curriculum_creation = False
        if self.user_service is not None:
            user_result = await self.user_service.get_user(entry.user_uid)
            if user_result.is_ok and user_result.value is not None:
                allow_curriculum_creation = user_result.value.can_create_curriculum()

        # --- Extraction --------------------------------------------------------
        extract_result = await self.activity_extractor.extract_and_create(
            entry,
            entry.user_uid,
            content_override=working_text,
            allow_curriculum_creation=allow_curriculum_creation,
            existing_line_hashes=existing_line_hashes,
            bridge_line_hashes=bridge_line_hashes,
            existing_extracted=existing_extracted,
            user_owned_semantic=user_owned_semantic,
            existing_vault_ids=existing_vault_ids,
        )
        if extract_result.is_error:
            return await self._fail(entry, extract_result.expect_error(), phase="extract")
        extraction = extract_result.value

        # --- Provenance edges ---------------------------------------------------
        # New edges for what was created, plus the hash refresh for lines Guard
        # 2b recognised by 🆔 after their text moved — the same MERGE, on the
        # line's own edge, same vault_id, extracted_at untouched (ON CREATE).
        provenance_links = [*extraction.created_links, *extraction.refreshed_links]
        if provenance_links:
            links_result = await self.entry_service.create_extracted_from_links(
                entry.uid, provenance_links
            )
            if links_result.is_error:
                return await self._fail(entry, links_result.expect_error(), phase="persist_links")

        # --- APPLIES_KNOWLEDGE edges (substance/ZPD contract) -------------------
        # A dangling @ku() reference (typo'd UID) must not fail the run — it
        # lands in the summary's link_errors instead.
        link_errors: list[str] = []
        ku_uids = dict.fromkeys(extraction.created_ku_uids + extraction.referenced_ku_uids)
        for ku_uid in ku_uids:
            edge_result = await self.entry_service.add_relationship(
                entry.uid, RelationshipName.APPLIES_KNOWLEDGE, ku_uid
            )
            if edge_result.is_error:
                message = f"APPLIES_KNOWLEDGE {entry.uid} -> {ku_uid}: " + str(
                    edge_result.expect_error()
                )
                link_errors.append(message)
                self.logger.warning(message)
                continue
            # Substance fan-out: PsService increments times_reflected_in_entries
            # on the Ku (+ connected PathSteps) — knowledge_substance_philosophy.
            # Only for NEW links: the edge MERGE is idempotent but the counter
            # increment is not, so skip Kus already linked to this entry.
            if ku_uid in already_applied_ku_uids:
                continue
            if self.event_bus is not None:
                await publish_event(
                    self.event_bus,
                    KnowledgeReflectedInEntry(
                        knowledge_uid=ku_uid,
                        entry_uid=entry.uid,
                        user_uid=entry.user_uid,
                    ),
                    self.logger,
                )

        # --- Run summary ---------------------------------------------------------
        if extraction.has_errors:
            self.logger.warning(
                f"Extraction for {entry.uid} completed with errors: "
                f"{len(extraction.parse_errors)} parse, "
                f"{len(extraction.creation_errors)} creation"
            )

        summary: dict[str, Any] = {
            **extraction.to_dict(),
            "status": "completed",
            "bridge_error": bridge_error,
            "link_errors": link_errors,
        }
        updates: dict[str, Any] = {
            "metadata": {**(entry.metadata or {}), "activity_extraction": summary},
            "status": EntityStatus.COMPLETED.value,
            "processing_completed_at": datetime.now(),
        }
        if bridge_error is not None:
            updates["processing_error"] = f"DSL bridge degraded to parser-only: {bridge_error}"
        update_result = await self.entry_service.update_processing_state(entry.uid, updates)
        if update_result.is_error:
            return await self._fail(entry, update_result.expect_error(), phase="persist_metadata")

        refreshed = await self.entry_service.get_entry(entry.uid, entry.user_uid)
        if refreshed.is_error or refreshed.value is None:
            # The run itself succeeded; surface the refetched-entry gap rather
            # than failing a completed extraction.
            self.logger.warning(f"Could not refetch {entry.uid} after extraction")
            await self._emit_completed(entry)
            return Result.ok(entry)

        updated = refreshed.value
        await self._emit_completed(updated)
        return Result.ok(updated)

    # =========================================================================
    # ADAPTER WRAPPERS
    # =========================================================================

    async def _transcribe(self, file_path: str) -> Result[str]:
        """Call Deepgram adapter, narrowing exceptions to the expected set."""
        assert self.transcription_adapter is not None
        try:
            result = await self.transcription_adapter.transcribe(audio_path=file_path)
        except FILE_IO_EXCEPTIONS as e:
            return Result.fail(
                Errors.system(message=f"Audio file read failed: {e}", service="user_entry")
            )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value.transcript_text)

    async def _generate(
        self,
        content: str,
        custom_instructions: str | None,
        enrichment_mode: EnrichmentMode,
    ) -> Result[str]:
        """Resolve an instruction template and call the LLM."""
        assert self.llm_caller is not None
        assert self.instruction_resolver is not None

        instruction_result = self.instruction_resolver.resolve(
            enrichment_mode=enrichment_mode,
            custom_instructions=custom_instructions,
        )
        if instruction_result.is_error:
            return Result.fail(instruction_result)
        instruction = instruction_result.value

        prompt = instruction.prompt_text.replace("{content}", content)

        try:
            return await self.llm_caller.generate(
                prompt=prompt,
                model=instruction.model,
                temperature=instruction.temperature,
                max_tokens=instruction.max_tokens,
            )
        except LLM_EXCEPTIONS as e:
            return Result.fail(
                Errors.integration(
                    service="llm",
                    message=f"LLM call failed: {e}",
                )
            )

    # =========================================================================
    # HELPERS
    # =========================================================================

    @staticmethod
    def _apply_mode_addendum(
        base_instructions: str | None, journal_mode_str: str | None
    ) -> str | None:
        """Append a JournalMode style addendum to LLM instructions when mode is set."""
        if not journal_mode_str:
            return base_instructions
        from core.models.enums.user_enums import JournalMode
        from core.services.journal.instruction_loader import journal_mode_addendum

        mode = JournalMode.from_string(journal_mode_str)
        addendum = journal_mode_addendum(mode)
        if not addendum:
            return base_instructions
        combined = (base_instructions or "") + f"\n\n## Response Mode\n\n{addendum}"
        return combined.strip() or None

    @staticmethod
    def _resolve_enrichment_mode(entry: UserEntry) -> EnrichmentMode:
        """Pull EnrichmentMode from entry metadata or fall back to default."""
        raw = (entry.metadata or {}).get("enrichment_mode") if entry.metadata else None
        if isinstance(raw, EnrichmentMode):
            return raw
        if isinstance(raw, str):
            try:
                return EnrichmentMode(raw)
            except ValueError:
                pass
        return EnrichmentMode.ACTIVITY_TRACKING

    async def _fail(
        self, entry: UserEntry, error: Any, phase: str | None = None
    ) -> Result[UserEntry]:
        """Mark the entry as FAILED, emit failure event, return Result.fail.

        ``phase`` is the stage of the pipeline where the failure occurred
        (``setup``, ``transcribe``, ``update_source``, ``structure``,
        ``persist_child``, ``generate_summary``, ``persist_summary``,
        ``persist_transcript``, ``read_provenance``, ``extract``,
        ``persist_links``, ``persist_metadata``). Threaded onto the emitted
        ``UserEntryProcessingFailed`` event so postmortems can tell a
        Deepgram blip apart from an LLM blip inside a
        ``TRANSCRIBE_AND_STRUCTURE`` run without re-reading logs.
        """
        message = getattr(error, "message", None) or str(error)
        phase_tag = f" [phase={phase}]" if phase else ""
        self.logger.error(
            f"UserEntry pipeline {entry.pipeline.value}{phase_tag} failed "
            f"for {entry.uid}: {message}"
        )
        try:
            await self.entry_service.update_processing_state(
                entry.uid,
                {
                    "processing_error": message,
                    "status": EntityStatus.FAILED.value,
                    "updated_at": datetime.now(),
                },
            )
        except Exception as update_exc:  # safety-net: failure-marking must not mask original error
            self.logger.warning(f"Failed to mark UserEntry {entry.uid} as FAILED: {update_exc}")

        if self.event_bus is not None:
            await publish_event(
                self.event_bus,
                UserEntryProcessingFailed(
                    entity_uid=entry.uid,
                    user_uid=entry.user_uid,
                    pipeline=entry.pipeline.value,
                    error=message,
                    failed_phase=phase,
                ),
                self.logger,
            )
        return Result.fail(error)

    async def _emit_started(self, entry: UserEntry) -> None:
        if self.event_bus is None:
            return
        await publish_event(
            self.event_bus,
            UserEntryProcessingStarted(
                entity_uid=entry.uid,
                user_uid=entry.user_uid,
                pipeline=entry.pipeline.value,
            ),
            self.logger,
        )

    async def _emit_completed(
        self,
        entry: UserEntry,
        produced_entry_uid: str | None = None,
    ) -> None:
        if self.event_bus is None:
            return
        await publish_event(
            self.event_bus,
            UserEntryProcessingCompleted(
                entity_uid=entry.uid,
                user_uid=entry.user_uid,
                pipeline=entry.pipeline.value,
                produced_entry_uid=produced_entry_uid,
            ),
            self.logger,
        )
