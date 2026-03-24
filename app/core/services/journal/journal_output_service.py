"""
JournalOutputService — LLM processing and JeOutput lifecycle
=============================================================

Processes JeInput content through LLM enrichment modes, creates JeOutput
entities in Neo4j with TRANSFORMS relationships, and manages output files
on disk.

Implements two protocols:
    OutputGeneratorOperations — pure LLM transform (used by BatchProcessingService)
    JournalOutputOperations  — full pipeline with persistence (used by routes)

Reuses shared infrastructure: UnifiedLLMCaller, InstructionResolver, PROMPT_REGISTRY.

Pipeline: JeInput(text) → InstructionResolver → LLM → file on disk → JeOutput in Neo4j

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.events import publish_event
from core.events.journal_events import JeOutputGenerated
from core.models.enums.entity_enums import EntityStatus, EntityType, ProcessorType
from core.models.journal.je_output import JeOutput
from core.models.journal.je_output_dto import JeOutputDTO
from core.ports.output_generator_protocols import OutputInstruction
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator

if TYPE_CHECKING:
    from adapters.persistence.neo4j.domain_backends import JournalOutputBackend
    from core.ports.infrastructure_protocols import EventBusOperations
    from core.services.llm_caller import UnifiedLLMCaller
    from core.services.output.instruction_resolver import InstructionResolver

logger = get_logger("skuel.services.journal.output")


class JournalOutputService:
    """
    LLM processing and JeOutput lifecycle management.

    Implements OutputGeneratorOperations (pure LLM transform) and
    JournalOutputOperations (full pipeline with Neo4j persistence).
    """

    def __init__(
        self,
        llm_caller: UnifiedLLMCaller,
        instruction_resolver: InstructionResolver,
        backend: JournalOutputBackend,
        storage_base: str,
        event_bus: EventBusOperations | None = None,
    ) -> None:
        self.llm_caller = llm_caller
        self.instruction_resolver = instruction_resolver
        self.backend = backend
        self.storage_base = storage_base
        self.event_bus = event_bus

    # =========================================================================
    # OutputGeneratorOperations — pure LLM transform (no persistence)
    # =========================================================================

    async def generate_output(
        self,
        content: str,
        instruction: OutputInstruction,
    ) -> Result[str]:
        """Generate formatted text from content + instruction.

        Substitutes {content} placeholder in instruction.prompt_text,
        calls LLM, returns the formatted text. No persistence.

        Used by BatchProcessingService for batch txt→md processing.
        """
        prompt = instruction.prompt_text.replace("{content}", content)

        return await self.llm_caller.generate(
            prompt=prompt,
            model=instruction.model,
            temperature=instruction.temperature,
            max_tokens=instruction.max_tokens,
        )

    # =========================================================================
    # JournalOutputOperations — full pipeline with persistence
    # =========================================================================

    async def process_je_input(
        self,
        je_input_uid: str,
        user_uid: str,
        content: str,
        enrichment_mode: str = "activity_tracking",
        custom_instructions: str | None = None,
    ) -> Result[JeOutput]:
        """Process a je_input through LLM and create a JeOutput entity.

        Pipeline:
        1. Resolve instruction via InstructionResolver
        2. Call LLM for content transformation
        3. Save output to disk
        4. Create JeOutput entity in Neo4j with TRANSFORMS relationship
        5. Publish JeOutputGenerated event

        Returns Result[JeOutput] — the created entity.
        """
        # 1. Resolve instruction
        instruction_result = self.instruction_resolver.resolve(
            enrichment_mode=enrichment_mode,
            custom_instructions=custom_instructions,
        )
        if instruction_result.is_error:
            return Result.fail(instruction_result.expect_error())

        instruction = instruction_result.value

        # 2. LLM transform
        llm_result = await self.generate_output(content, instruction)
        if llm_result.is_error:
            logger.error(f"LLM generation failed for {je_input_uid}: {llm_result.error}")
            return Result.fail(llm_result.expect_error())

        output_text = llm_result.value

        # 3. Save to disk
        uid = UIDGenerator.generate_random_uid("jo")
        now = datetime.now(tz=UTC)
        file_path = self._build_output_path(uid, now)

        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(output_text, encoding="utf-8")
        except OSError as e:
            logger.error(f"Failed to write je_output file {file_path}: {e}")
            return Result.fail(Errors.system(message=f"File write failed: {e}", service="journal"))

        # 4. Create JeOutput in Neo4j
        effective_mode = enrichment_mode or "activity_tracking"
        properties: dict[str, Any] = {
            "uid": uid,
            "entity_type": EntityType.JE_OUTPUT.value,
            "title": f"Journal Output — {effective_mode}",
            "status": EntityStatus.COMPLETED.value,
            "user_uid": user_uid,
            "output_content": output_text,
            "output_generated_at": now.isoformat(),
            "source_je_input_uid": je_input_uid,
            "enrichment_mode": effective_mode,
            "output_file_path": str(file_path),
            "processor_type": ProcessorType.LLM.value,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        create_result = await self.backend.create_with_transforms(
            properties=properties,
            user_uid=user_uid,
            je_input_uid=je_input_uid,
        )
        if create_result.is_error:
            logger.error(f"Failed to create JeOutput in Neo4j: {create_result.error}")
            return Result.fail(create_result.expect_error())

        # Build domain model from Neo4j result
        je_output = JeOutput.from_dto(JeOutputDTO.from_dict(create_result.value))

        # 5. Publish event
        if self.event_bus:
            await publish_event(
                self.event_bus,
                JeOutputGenerated(
                    je_output_uid=uid,
                    je_input_uid=je_input_uid,
                    user_uid=user_uid,
                    enrichment_mode=effective_mode,
                    output_file_path=str(file_path),
                ),
                logger,
            )

        logger.info(f"JeOutput created: {uid} (mode: {effective_mode}, input: {je_input_uid})")
        return Result.ok(je_output)

    # =========================================================================
    # JournalOutputOperations — retrieval methods
    # =========================================================================

    async def get_je_output(self, uid: str) -> Result[JeOutput | None]:
        """Get a journal entry output by UID."""
        result = await self.backend.get(uid)
        if result.is_error:
            return Result.fail(result.expect_error())
        if result.value is None:
            return Result.ok(None)
        return Result.ok(JeOutput.from_dto(JeOutputDTO.from_dict(result.value)))

    async def get_je_output_for_input(self, je_input_uid: str) -> Result[JeOutput | None]:
        """Get the je_output associated with a je_input via TRANSFORMS relationship."""
        result = await self.backend.get_je_output_for_input(je_input_uid)
        if result.is_error:
            return Result.fail(result.expect_error())
        if result.value is None:
            return Result.ok(None)
        return Result.ok(JeOutput.from_dto(JeOutputDTO.from_dict(result.value)))

    async def list_je_outputs(
        self,
        user_uid: str,
        limit: int = 50,
        offset: int = 0,
    ) -> Result[list[JeOutput]]:
        """List journal entry outputs for a user."""
        result = await self.backend.get_user_entities(user_uid=user_uid, limit=limit, offset=offset)
        if result.is_error:
            return Result.fail(result.expect_error())
        return Result.ok(
            [JeOutput.from_dto(JeOutputDTO.from_dict(record)) for record in (result.value or [])]
        )

    async def get_output_file_content(self, uid: str) -> Result[str | None]:
        """Get the content of a je_output file from disk."""
        result = await self.get_je_output(uid)
        if result.is_error:
            return Result.fail(result.expect_error())
        je_output = result.value
        if not je_output or not je_output.output_file_path:
            return Result.ok(None)

        path = Path(je_output.output_file_path)
        if not path.exists():
            return Result.ok(None)

        try:
            return Result.ok(path.read_text(encoding="utf-8"))
        except OSError as e:
            return Result.fail(Errors.system(message=f"File read failed: {e}", service="journal"))

    async def download_output_file(self, uid: str) -> Result[str | None]:
        """Get the file path of a je_output for download."""
        result = await self.get_je_output(uid)
        if result.is_error:
            return Result.fail(result.expect_error())
        je_output = result.value
        if not je_output or not je_output.output_file_path:
            return Result.ok(None)

        path = Path(je_output.output_file_path)
        if not path.exists():
            return Result.ok(None)
        return Result.ok(str(path))

    # =========================================================================
    # Admin — file cleanup
    # =========================================================================

    def cleanup_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> Result[dict[str, int]]:
        """Delete je_output files within a date range.

        Scans storage_base/{YYYY-MM}/ directories for files in range.
        Returns {files_deleted: int, bytes_freed: int}.
        """
        files_deleted = 0
        bytes_freed = 0
        base = Path(self.storage_base)

        if not base.exists():
            return Result.ok({"files_deleted": 0, "bytes_freed": 0})

        for month_dir in sorted(base.iterdir()):
            if not month_dir.is_dir():
                continue
            for file_path in month_dir.iterdir():
                if not file_path.is_file() or file_path.suffix != ".md":
                    continue
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime, tz=UTC)
                if start_date <= mtime <= end_date:
                    size = file_path.stat().st_size
                    file_path.unlink()
                    files_deleted += 1
                    bytes_freed += size

        return Result.ok({"files_deleted": files_deleted, "bytes_freed": bytes_freed})

    # =========================================================================
    # Private helpers
    # =========================================================================

    def _build_output_path(self, uid: str, timestamp: datetime) -> Path:
        """Build the output file path: {storage_base}/{YYYY-MM}/je_output_{uid}.md"""
        month_dir = timestamp.strftime("%Y-%m")
        return Path(self.storage_base) / month_dir / f"je_output_{uid}.md"
