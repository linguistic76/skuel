"""Journal service — STANDARD single-response and FOUNDER three-stage DNWF workflows.

STANDARD tier: run_standard() — single motivating response connecting the entry
to the user's active goals, tasks, and habits; closes with graph suggestions.

FOUNDER tier: run_stage1/2/3() — Scribe → Thought Partner → What Is Related;
each stage gated by user review.

Both tiers persist entries via save_entry() → UserEntry(pipeline=JOURNAL).

See: /docs/decisions/ (ADR forthcoming)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.models.type_hints import UserUID
from core.services.journal.instruction_loader import (
    stage1_system_prompt,
    stage2_system_prompt,
    stage3_system_prompt,
    standard_system_prompt,
)
from core.services.llm_caller import LLMCallerProtocol
from core.utils.exception_types import LLM_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.goals_service import GoalsService
    from core.services.habits_service import HabitsService
    from core.services.tasks_service import TasksService
    from core.services.user_entry.user_entry_service import UserEntryService

logger = get_logger("skuel.services.journal")

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 4000
_STAGE3_MAX_TOKENS = 3000


class JournalService:
    """Orchestrates journal workflows for both tiers.

    STANDARD: run_standard() — one-shot motivating response with context + graph hints.
    FOUNDER:  run_stage1/2/3() — Scribe → Thought Partner → What Is Related.

    Backend: UserEntryService (persistence); GoalsService/TasksService/HabitsService
    (user-context summaries); LLMCaller (all AI responses).
    """

    def __init__(
        self,
        llm_caller: LLMCallerProtocol,
        user_entry_service: UserEntryService,
        goals_service: GoalsService | None = None,
        tasks_service: TasksService | None = None,
        habits_service: HabitsService | None = None,
    ) -> None:
        self._llm = llm_caller
        self._user_entry = user_entry_service
        self._goals = goals_service
        self._tasks = tasks_service
        self._habits = habits_service

    # ------------------------------------------------------------------
    # User-context summary (used by Stage 2 and Stage 3 prompts)
    # ------------------------------------------------------------------

    async def _build_context_summary(self, user_uid: UserUID) -> str:
        """Return a short text digest of the user's active goals/tasks/habits."""
        lines: list[str] = []

        if self._goals:
            result = await self._goals.get_user_goals(user_uid)
            if not result.is_error and result.value:
                titles = [g.title for g in result.value[:6]]
                lines.append("Active goals: " + ", ".join(titles))

        if self._tasks:
            tasks_result = await self._tasks.get_user_tasks(user_uid)
            if not tasks_result.is_error and tasks_result.value:
                titles = [t.title for t in tasks_result.value[:6]]
                lines.append("Current tasks: " + ", ".join(titles))

        if self._habits:
            habits_result = await self._habits.get_user_habits(user_uid)
            if not habits_result.is_error and habits_result.value:
                titles = [h.title for h in habits_result.value[:6]]
                lines.append("Active habits: " + ", ".join(titles))

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Stage 1 — Scribe
    # ------------------------------------------------------------------

    async def run_stage1(self, raw_entry: str, user_uid: UserUID) -> Result[str]:
        """Stage 1: produce a faithful structural Scribe record of the raw entry."""
        system_prompt = stage1_system_prompt()
        user_message = f"# Daily Note\n\n{raw_entry}\n\nPlease process this as Stage 1 — Scribe."
        try:
            return await self._llm.generate(
                prompt=user_message,
                model=_MODEL,
                system_prompt=system_prompt,
                max_tokens=_MAX_TOKENS,
            )
        except LLM_EXCEPTIONS as exc:
            logger.error("Journal Stage 1 LLM error: %s", exc)
            return Result.fail(Errors.integration("llm", f"Stage 1 failed: {exc}"))

    # ------------------------------------------------------------------
    # Stage 2 — Thought Partner
    # ------------------------------------------------------------------

    async def run_stage2(
        self,
        raw_entry: str,
        scribe_output: str,
        review_notes: str,
        user_uid: UserUID,
    ) -> Result[str]:
        """Stage 2: evaluative + reflective Thought Partner response across four roles."""
        context_summary = await self._build_context_summary(user_uid)
        system_prompt = stage2_system_prompt(context_summary)
        user_message = (
            f"# Raw Daily Note\n\n{raw_entry}\n\n"
            f"# Stage 1 — Scribe Record\n\n{scribe_output}\n\n"
            f"# Review Notes\n\n{review_notes or '(none)'}\n\n"
            "Please process this as Stage 2 — Thought Partner."
        )
        try:
            return await self._llm.generate(
                prompt=user_message,
                model=_MODEL,
                system_prompt=system_prompt,
                max_tokens=_MAX_TOKENS,
            )
        except LLM_EXCEPTIONS as exc:
            logger.error("Journal Stage 2 LLM error: %s", exc)
            return Result.fail(Errors.integration("llm", f"Stage 2 failed: {exc}"))

    # ------------------------------------------------------------------
    # Stage 3 — What Is Related
    # ------------------------------------------------------------------

    async def run_stage3(
        self,
        raw_entry: str,
        thought_partner_output: str,
        review_notes: str,
        user_uid: UserUID,
    ) -> Result[str]:
        """Stage 3: propose graph connections to knowledge, goals, tasks, and habits."""
        context_summary = await self._build_context_summary(user_uid)
        system_prompt = stage3_system_prompt(context_summary)
        user_message = (
            f"# Raw Daily Note\n\n{raw_entry}\n\n"
            f"# Stage 2 — What Is Emerging\n\n{thought_partner_output}\n\n"
            f"# Review Notes\n\n{review_notes or '(none)'}\n\n"
            "Please process this as Stage 3 — What Is Related."
        )
        try:
            return await self._llm.generate(
                prompt=user_message,
                model=_MODEL,
                system_prompt=system_prompt,
                max_tokens=_STAGE3_MAX_TOKENS,
            )
        except LLM_EXCEPTIONS as exc:
            logger.error("Journal Stage 3 LLM error: %s", exc)
            return Result.fail(Errors.integration("llm", f"Stage 3 failed: {exc}"))

    # ------------------------------------------------------------------
    # Standard workflow
    # ------------------------------------------------------------------

    async def run_standard(self, raw_entry: str, user_uid: UserUID) -> Result[str]:
        """STANDARD tier: single response connecting the journal to active context.

        Fetches active goals/tasks/habits, builds a motivating response that
        names specific connections, and appends graph-connection suggestions when
        enough context is present.

        Backend: GoalsService, TasksService, HabitsService (context summary);
                 LLMCaller (response generation).
        """
        context_summary = await self._build_context_summary(user_uid)
        system_prompt = standard_system_prompt(context_summary)
        user_message = f"# Daily Note\n\n{raw_entry}\n\nPlease respond as my journal companion."
        try:
            return await self._llm.generate(
                prompt=user_message,
                model=_MODEL,
                system_prompt=system_prompt,
                max_tokens=_MAX_TOKENS,
            )
        except LLM_EXCEPTIONS as exc:
            logger.error("Journal standard response LLM error: %s", exc)
            return Result.fail(Errors.integration("llm", f"Journal response failed: {exc}"))

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    async def save_entry(self, title: str, raw_entry: str, user_uid: UserUID) -> Result[str]:
        """Persist the journal entry as a UserEntry(pipeline=JOURNAL).

        Returns the UID of the created entry.
        """
        from core.models.enums.pipeline import Pipeline
        from core.models.user_entry.user_entry_request import UserEntryCreateRequest

        request = UserEntryCreateRequest(
            title=title or "Journal Entry",
            content=raw_entry,
            pipeline=Pipeline.JOURNAL,
        )
        result = await self._user_entry.create_entry(request, user_uid)
        if result.is_error:
            return Result.fail(result)
        entry, _ = result.value
        logger.info("Journal entry saved: %s (user=%s)", entry.uid, user_uid)
        return Result.ok(entry.uid)
