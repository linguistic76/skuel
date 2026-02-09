"""
Journal Output Generator
=========================

Generates formatted je_output files based on mode weights.

Three formatters for three modes:
- Activity: Structured with DSL tags preserved
- Articulation: Verbatim with formatting improvements
- Exploration: Question-organized
"""

import os
from datetime import datetime
from pathlib import Path

from core.models.enums.report_enums import JournalMode
from core.services.ai_service import OpenAIService
from core.services.journals.journal_types import JournalWeights
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.services.journals.generator")


class JournalOutputGenerator:
    """
    Generates formatted journal output files based on processing mode.

    Uses LLM to format content according to mode-specific templates.
    Saves output to SKUEL_JOURNAL_STORAGE organized by date.
    """

    def __init__(self, openai_service: OpenAIService, storage_base: str | None = None) -> None:
        """
        Initialize generator with OpenAI service and storage location.

        Args:
            openai_service: OpenAI service for LLM formatting
            storage_base: Base directory for je_output files (env: SKUEL_JOURNAL_STORAGE)
        """
        self.openai_service = openai_service
        self.logger = logger

        # Get storage location from env or use provided
        self.storage_base = storage_base or os.getenv(
            "SKUEL_JOURNAL_STORAGE", "/tmp/skuel_journals"
        )

        # Load formatter prompts
        prompts_dir = Path(__file__).parent / "prompts"
        self.activity_prompt = (prompts_dir / "activity_formatter.md").read_text()
        self.articulation_prompt = (prompts_dir / "articulation_formatter.md").read_text()
        self.exploration_prompt = (prompts_dir / "exploration_formatter.md").read_text()

    async def generate(
        self,
        content: str,
        weights: JournalWeights,
        report_uid: str,
        threshold: float = 0.2,
    ) -> Result[str]:
        """
        Generate formatted je_output file based on mode weights.

        Primary mode (highest weight) determines formatter.
        Output saved to: {storage_base}/{YYYY-MM}/report_{uid}_output.md

        Args:
            content: Raw journal content to format
            weights: Mode weight distribution
            report_uid: Report UID for filename
            threshold: Minimum weight to trigger mode (default: 0.2)

        Returns:
            Result containing path to generated je_output file
        """
        primary_mode = weights.get_primary_mode()
        self.logger.info(
            f"Generating je_output for {report_uid} (mode: {primary_mode.value}, weights: {weights.to_dict()})"
        )

        # Select formatter based on primary mode
        if primary_mode == JournalMode.ACTIVITY_TRACKING:
            formatted_result = await self._format_activity(content)
        elif primary_mode == JournalMode.IDEA_ARTICULATION:
            formatted_result = await self._format_articulation(content)
        else:  # CRITICAL_THINKING
            formatted_result = await self._format_exploration(content)

        if formatted_result.is_error:
            return Result.fail(formatted_result.expect_error())

        formatted_content = formatted_result.value

        # Save to disk
        output_path_result = self._save_output(report_uid, formatted_content)
        if output_path_result.is_error:
            return Result.fail(output_path_result.expect_error())

        output_path = output_path_result.value
        self.logger.info(f"je_output saved: {output_path}")
        return Result.ok(output_path)

    async def _format_activity(self, content: str) -> Result[str]:
        """Format content for activity tracking mode (structured DSL)."""
        prompt = self.activity_prompt.format(content=content)
        return await self._call_formatter(prompt, "activity")

    async def _format_articulation(self, content: str) -> Result[str]:
        """Format content for idea articulation mode (verbatim preservation)."""
        prompt = self.articulation_prompt.format(content=content)
        return await self._call_formatter(prompt, "articulation")

    async def _format_exploration(self, content: str) -> Result[str]:
        """Format content for critical thinking mode (question-organized)."""
        prompt = self.exploration_prompt.format(content=content)
        return await self._call_formatter(prompt, "exploration")

    async def _call_formatter(self, prompt: str, mode_name: str) -> Result[str]:
        """Call OpenAI to format content using mode-specific prompt."""
        try:
            response = await self.openai_service.complete(
                prompt=prompt,
                temperature=0.5,  # Moderate creativity for formatting
                max_tokens=2000,  # Longer output for formatted content
            )

            if response.is_error:
                return Result.fail(response.expect_error())

            formatted = response.value.strip()
            self.logger.debug(f"Formatted content ({mode_name}): {len(formatted)} chars")
            return Result.ok(formatted)

        except Exception as e:
            return Result.fail(
                Errors.system(
                    message=f"Formatting failed ({mode_name}): {e}",
                    operation="format_journal",
                    exception=e,
                )
            )

    def _save_output(self, report_uid: str, content: str) -> Result[str]:
        """
        Save formatted content to disk.

        Path: {storage_base}/{YYYY-MM}/report_{uid}_output.md

        Args:
            report_uid: Report UID for filename
            content: Formatted content to save

        Returns:
            Result containing full path to saved file
        """
        try:
            # Create date-based subdirectory (YYYY-MM)
            now = datetime.now()
            date_subdir = now.strftime("%Y-%m")
            output_dir = Path(self.storage_base) / date_subdir
            output_dir.mkdir(parents=True, exist_ok=True)

            # Generate filename
            filename = f"report_{report_uid}_output.md"
            output_path = output_dir / filename

            # Write file
            output_path.write_text(content, encoding="utf-8")

            self.logger.info(f"Saved je_output: {output_path}")
            return Result.ok(str(output_path))

        except Exception as e:
            return Result.fail(
                Errors.system(
                    message=f"Failed to save je_output: {e}",
                    operation="save_journal_output",
                    exception=e,
                )
            )

    def cleanup_date_range(
        self, start_date: datetime, end_date: datetime
    ) -> Result[dict[str, int]]:
        """
        Delete je_output files from date range.

        Used after human has decomposed je_outputs and ingested pieces into Neo4j.

        Args:
            start_date: Start of date range (inclusive)
            end_date: End of date range (inclusive)

        Returns:
            Result containing cleanup stats (files_deleted, bytes_freed)
        """
        try:
            storage_path = Path(self.storage_base)
            if not storage_path.exists():
                return Result.ok({"files_deleted": 0, "bytes_freed": 0})

            files_deleted = 0
            bytes_freed = 0

            # Iterate through date subdirectories
            current_date = start_date
            while current_date <= end_date:
                date_subdir = current_date.strftime("%Y-%m")
                subdir_path = storage_path / date_subdir

                if subdir_path.exists():
                    # Delete all .md files in this directory
                    for file_path in subdir_path.glob("report_*_output.md"):
                        bytes_freed += file_path.stat().st_size
                        file_path.unlink()
                        files_deleted += 1

                    # Remove empty directory
                    if not list(subdir_path.iterdir()):
                        subdir_path.rmdir()

                # Move to next month
                if current_date.month == 12:
                    current_date = current_date.replace(year=current_date.year + 1, month=1)
                else:
                    current_date = current_date.replace(month=current_date.month + 1)

            self.logger.info(
                f"Cleanup complete: {files_deleted} files deleted, {bytes_freed} bytes freed"
            )
            return Result.ok({"files_deleted": files_deleted, "bytes_freed": bytes_freed})

        except Exception as e:
            return Result.fail(
                Errors.system(
                    message=f"Cleanup failed: {e}",
                    operation="cleanup_journal_outputs",
                    exception=e,
                )
            )
