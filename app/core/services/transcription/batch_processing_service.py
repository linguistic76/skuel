"""
Batch Processing Service (Tier 2)
===================================

Process .txt transcripts through LLM → .md files.

Uses OutputGeneratorOperations + InstructionResolver from Phase 2 to
resolve instructions and generate formatted content.

Can chain with BatchTranscriptionService for end-to-end audio → .md pipeline.

Usage:
    service = BatchProcessingService(output_generator, instruction_resolver)
    result = await service.process_batch(Path("data/je_outputs"), enrichment_mode="activity_tracking")
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from core.models.enums.submissions_enums import EnrichmentMode
from core.ports.output_generator_protocols import OutputGeneratorOperations
from core.utils.exception_types import FILE_IO_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from pathlib import Path

    from core.services.output.instruction_resolver import InstructionResolver
    from core.services.transcription.batch_transcription_service import (
        BatchTranscriptionService,
    )

logger = get_logger("skuel.services.transcription.batch_processing")


def _path_name(p: Path) -> str:
    """Sort key for paths by name (SKUEL012: named function, not lambda)."""
    return p.name


@dataclass(frozen=True)
class BatchProcessingResult:
    """Result of batch LLM processing run."""

    total_files: int
    succeeded: int
    failed: int
    skipped: int
    results: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)


class BatchProcessingService:
    """
    Batch .txt → .md processing via LLM.

    Tier 2 of the journals pipeline: takes transcripts (or any .txt files)
    and processes them through LLM using resolved instructions.

    Can optionally chain with BatchTranscriptionService for end-to-end
    audio → .md pipeline via transcribe_and_process().
    """

    def __init__(
        self,
        output_generator: OutputGeneratorOperations,
        instruction_resolver: InstructionResolver,
        max_concurrent: int = 3,  # LLM calls are more expensive than transcription
    ) -> None:
        """
        Initialize batch processing service.

        Args:
            output_generator: LLM content generator (implements OutputGeneratorOperations)
            instruction_resolver: Resolves enrichment mode / custom instructions
            max_concurrent: Max parallel LLM requests (lower than transcription)
        """
        self.output_generator = output_generator
        self.instruction_resolver = instruction_resolver
        self.max_concurrent = max_concurrent
        self.logger = logger

    async def process_batch(
        self,
        input_dir: Path,
        output_dir: Path | None = None,
        enrichment_mode: EnrichmentMode | None = None,
        custom_instructions: str | None = None,
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_tokens: int = 4000,
        skip_existing: bool = True,
    ) -> Result[BatchProcessingResult]:
        """
        Process .txt files through LLM to produce .md files.

        Args:
            input_dir: Directory containing .txt files
            output_dir: Directory for .md output (defaults to input_dir)
            enrichment_mode: Processing strategy (EnrichmentMode enum)
            custom_instructions: User-provided instruction text
            model: LLM model to use
            temperature: Sampling temperature
            max_tokens: Max tokens per generation
            skip_existing: Skip files that already have .md output

        Returns:
            Result[BatchProcessingResult]
        """
        if not input_dir.is_dir():
            return Result.fail(
                Errors.validation(f"Input directory does not exist: {input_dir}", field="input_dir")
            )

        output_dir = output_dir or input_dir

        # Ensure output directory exists
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except FILE_IO_EXCEPTIONS as e:
            return Result.fail(
                Errors.system(f"Cannot create output directory: {e}", operation="process_batch")
            )

        # Resolve instruction once for the whole batch
        instruction_result = self.instruction_resolver.resolve(
            enrichment_mode=enrichment_mode,
            custom_instructions=custom_instructions,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if instruction_result.is_error:
            return Result.fail(instruction_result)

        instruction = instruction_result.value

        # Find .txt files
        txt_files = sorted(input_dir.glob("*.txt"), key=_path_name)
        if not txt_files:
            return Result.ok(BatchProcessingResult(total_files=0, succeeded=0, failed=0, skipped=0))

        self.logger.info(
            f"Starting batch processing: {len(txt_files)} files from {input_dir} "
            f"(mode={enrichment_mode or 'default'}, model={model})"
        )

        # Concurrent processing with semaphore
        semaphore = asyncio.Semaphore(self.max_concurrent)
        tasks = [
            self._process_single(f, output_dir, instruction, semaphore, skip_existing)
            for f in txt_files
        ]
        results = await asyncio.gather(*tasks)

        # Aggregate
        succeeded = sum(1 for r in results if r["status"] == "success")
        failed = sum(1 for r in results if r["status"] == "failed")
        skipped = sum(1 for r in results if r["status"] == "skipped")
        errors = [
            {"name": r["name"], "error": r.get("error", "")}
            for r in results
            if r["status"] == "failed"
        ]

        self.logger.info(
            f"Batch processing complete: {succeeded} succeeded, {failed} failed, {skipped} skipped"
        )

        return Result.ok(
            BatchProcessingResult(
                total_files=len(txt_files),
                succeeded=succeeded,
                failed=failed,
                skipped=skipped,
                results=list(results),
                errors=errors,
            )
        )

    async def _process_single(
        self,
        txt_path: Path,
        output_dir: Path,
        instruction: Any,
        semaphore: asyncio.Semaphore,
        skip_existing: bool,
    ) -> dict[str, Any]:
        """Process a single .txt file through LLM → .md."""
        md_path = output_dir / f"{txt_path.stem}.md"
        file_name = txt_path.name

        if skip_existing and md_path.exists():
            self.logger.debug(f"Skipping {file_name} (already processed)")
            return {"name": file_name, "status": "skipped"}

        async with semaphore:
            self.logger.info(f"Processing: {file_name}")

            try:
                # Read content
                content = txt_path.read_text(encoding="utf-8")
                if not content.strip():
                    return {"name": file_name, "status": "failed", "error": "Empty file"}

                # Generate via LLM
                result = await self.output_generator.generate_output(content, instruction)

                if result.is_error:
                    error_msg = str(result.error)
                    self.logger.error(f"LLM processing failed for {file_name}: {error_msg}")
                    return {"name": file_name, "status": "failed", "error": error_msg}

                # Write .md output
                md_path.write_text(result.value, encoding="utf-8")

                self.logger.info(f"Processed {file_name}: {len(result.value)} chars")
                return {
                    "name": file_name,
                    "status": "success",
                    "output_path": str(md_path),
                    "output_chars": len(result.value),
                }

            except Exception as e:  # safety-net: single file failure must not stop batch
                self.logger.error(f"Error processing {file_name}: {e}")
                return {"name": file_name, "status": "failed", "error": str(e)}

    async def transcribe_and_process(
        self,
        audio_dir: Path,
        output_dir: Path,
        batch_transcription: BatchTranscriptionService,
        enrichment_mode: EnrichmentMode | None = None,
        custom_instructions: str | None = None,
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_tokens: int = 4000,
        skip_existing: bool = True,
    ) -> Result[dict[str, Any]]:
        """
        Combined Tier 1 + Tier 2: audio → txt → md.

        Args:
            audio_dir: Directory containing audio files
            output_dir: Directory for all output (.txt and .md)
            batch_transcription: BatchTranscriptionService for Tier 1
            enrichment_mode: Processing strategy for Tier 2
            custom_instructions: User-provided instructions for Tier 2
            model: LLM model for Tier 2
            temperature: Sampling temperature for Tier 2
            max_tokens: Max tokens for Tier 2
            skip_existing: Skip already-processed files

        Returns:
            Result[dict] with keys: transcription, processing
        """
        # Tier 1: audio → txt
        self.logger.info(f"Starting combined pipeline: {audio_dir} → {output_dir}")

        transcription_result = await batch_transcription.transcribe_batch(
            input_dir=audio_dir,
            output_dir=output_dir,
            skip_existing=skip_existing,
        )

        if transcription_result.is_error:
            return Result.fail(transcription_result)

        tier1 = transcription_result.value

        # Tier 2: txt → md (reads .txt from output_dir)
        processing_result = await self.process_batch(
            input_dir=output_dir,
            output_dir=output_dir,
            enrichment_mode=enrichment_mode,
            custom_instructions=custom_instructions,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            skip_existing=skip_existing,
        )

        if processing_result.is_error:
            return Result.fail(processing_result)

        tier2 = processing_result.value

        return Result.ok(
            {
                "transcription": {
                    "total": tier1.total_files,
                    "succeeded": tier1.succeeded,
                    "failed": tier1.failed,
                    "skipped": tier1.skipped,
                },
                "processing": {
                    "total": tier2.total_files,
                    "succeeded": tier2.succeeded,
                    "failed": tier2.failed,
                    "skipped": tier2.skipped,
                },
            }
        )


__all__ = ["BatchProcessingResult", "BatchProcessingService"]
