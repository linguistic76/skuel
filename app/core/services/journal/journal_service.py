"""Journal service — STANDARD single-response and FOUNDER three-stage DNWF workflows.

STANDARD tier: run_standard() — single response in the requested JournalMode
(SCRIBE / THOUGHT_PARTNER / WHAT_IS_RELATED); defaults to THOUGHT_PARTNER.

FOUNDER tier: run_stage1/2/3() — Scribe → Thought Partner → What Is Related;
each stage gated by user review. Stage functions are mode-invariant.

Entry persistence is handled by the ingestion path in the calling route,
not by this service. See: /docs/decisions/ (ADR forthcoming)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.models.enums.user_enums import JournalMode
from core.models.type_hints import UserUID
from core.services.journal.instruction_loader import (
    follow_up_system_prompt,
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
    from core.services.dsl.llm_dsl_bridge import LLMDSLBridgeService
    from core.services.goals_service import GoalsService
    from core.services.habits_service import HabitsService
    from core.services.journal.suggestion import SuggestedActivity
    from core.services.tasks_service import TasksService
    from core.services.user_entry.user_entry_service import UserEntryService

logger = get_logger("skuel.services.journal")

_MODEL_CLAUDE = "claude-sonnet-4-6"
_MODEL_GPT = "gpt-4o-mini"
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
        dsl_bridge: LLMDSLBridgeService | None = None,
    ) -> None:
        self._llm = llm_caller
        self._user_entry = user_entry_service
        self._goals = goals_service
        self._tasks = tasks_service
        self._habits = habits_service
        # Optional Digital pre-pass that turns prose into @context() lines for
        # the "Suggested activities" panel. None on CORE tier (no panel).
        self._dsl_bridge = dsl_bridge

    def _resolve_model(self) -> str:
        """Return the best available LLM model based on configured adapters."""
        return _MODEL_CLAUDE if self._llm.is_model_supported(_MODEL_CLAUDE) else _MODEL_GPT

    # ------------------------------------------------------------------
    # User-context summary (used by Stage 2 and Stage 3 prompts)
    # ------------------------------------------------------------------

    async def _build_context_summary(self, user_uid: UserUID) -> str:
        """Return a short text digest of the user's active goals/tasks/habits/vault notes."""
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

        notes_result = await self._user_entry.get_vault_notes_for_context(user_uid)
        if not notes_result.is_error and notes_result.value:
            note_lines = []
            for note in notes_result.value:
                title = note.get("title", "")
                snippet = (note.get("snippet") or "").strip()
                entry = f"  [{title}]" + (f" {snippet}" if snippet else "")
                note_lines.append(entry)
            lines.append("Personal project notes:\n" + "\n".join(note_lines))

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Suggested activities (prose → paste-ready @context() lines)
    # ------------------------------------------------------------------

    async def suggest_activities(
        self, content: str, user_uid: UserUID
    ) -> Result[list[SuggestedActivity]]:
        """Recognise candidate activities in journal text as paste-ready DSL lines.

        Runs the LLM bridge over ``content`` (grounded in the user's active
        goals), then re-renders the result into canonical checkbox DSL. The
        lines are *inert suggestions* — the caller surfaces them for the user to
        copy into a Periodic Note or extraction folder; nothing is created here.

        Returns an empty list (not an error) when the bridge is unavailable
        (CORE tier) or the content is blank — the panel renders a neutral state.

        Backend: GoalsService (grounding); LLMDSLBridgeService (recognition).
        """
        from core.services.journal.suggestion import build_suggestions

        if self._dsl_bridge is None or not content or not content.strip():
            return Result.ok([])

        active_goals: list[dict[str, str]] = []
        if self._goals:
            # get_active filters terminal states (completed/cancelled/archived);
            # the bridge labels this context "active goals", so stale goals must
            # not leak in (get_user_goals would return all).
            goals_result = await self._goals.get_active(user_uid, limit=10)
            if not goals_result.is_error and goals_result.value:
                active_goals = [{"title": g.title} for g in goals_result.value]

        transform = await self._dsl_bridge.transform_with_context(
            content, user_uid, active_goals=active_goals or None
        )
        if transform.is_error:
            return Result.fail(transform)

        return Result.ok(build_suggestions(transform.value.activity_lines))

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
                model=self._resolve_model(),
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
        """Stage 2: Thought Partner response across four roles."""
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
                model=self._resolve_model(),
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
                model=self._resolve_model(),
                system_prompt=system_prompt,
                max_tokens=_STAGE3_MAX_TOKENS,
            )
        except LLM_EXCEPTIONS as exc:
            logger.error("Journal Stage 3 LLM error: %s", exc)
            return Result.fail(Errors.integration("llm", f"Stage 3 failed: {exc}"))

    # ------------------------------------------------------------------
    # Standard workflow
    # ------------------------------------------------------------------

    async def run_standard(
        self,
        raw_entry: str,
        user_uid: UserUID,
        mode: JournalMode | None = None,
    ) -> Result[str]:
        """STANDARD tier: single response in the requested JournalMode.

        JournalMode selects the function (SCRIBE / THOUGHT_PARTNER / WHAT_IS_RELATED).
        Defaults to THOUGHT_PARTNER when not supplied.

        Backend: GoalsService, TasksService, HabitsService (context summary);
                 LLMCaller (response generation).
        """
        context_summary = await self._build_context_summary(user_uid)
        system_prompt = standard_system_prompt(context_summary, mode)
        user_message = f"# Daily Note\n\n{raw_entry}\n\nPlease respond as my journal companion."
        try:
            return await self._llm.generate(
                prompt=user_message,
                model=self._resolve_model(),
                system_prompt=system_prompt,
                max_tokens=_MAX_TOKENS,
            )
        except LLM_EXCEPTIONS as exc:
            logger.error("Journal standard response LLM error: %s", exc)
            return Result.fail(Errors.integration("llm", f"Journal response failed: {exc}"))

    # ------------------------------------------------------------------
    # Compiled output
    # ------------------------------------------------------------------

    async def run_compiled(self, raw_entry: str, user_uid: UserUID) -> Result[str]:
        """Run all three DNWF stages in sequence and return a single compiled document.

        Used for file-based (batch) processing where interactive review between
        stages is not possible. Produces Stage 1 → Stage 2 → Stage 3 output with no
        review notes between stages.
        """
        stage1 = await self.run_stage1(raw_entry, user_uid)
        if stage1.is_error:
            return stage1
        scribe_output = stage1.value

        stage2 = await self.run_stage2(
            raw_entry=raw_entry,
            scribe_output=scribe_output,
            review_notes="",
            user_uid=user_uid,
        )
        if stage2.is_error:
            return stage2
        thought_partner_output = stage2.value

        stage3 = await self.run_stage3(
            raw_entry=raw_entry,
            thought_partner_output=thought_partner_output,
            review_notes="",
            user_uid=user_uid,
        )
        if stage3.is_error:
            return stage3

        compiled = (
            f"# Stage 1 — Scribe\n\n{scribe_output}"
            f"\n\n---\n\n"
            f"# Stage 2 — What Is Emerging\n\n{thought_partner_output}"
            f"\n\n---\n\n"
            f"# Stage 3 — What Is Related\n\n{stage3.value}"
        )
        return Result.ok(compiled)

    # ------------------------------------------------------------------
    # Follow-up (conversation continuation)
    # ------------------------------------------------------------------

    async def run_follow_up(
        self,
        original_entry: str,
        ai_response: str,
        user_reply: str,
        user_uid: UserUID,
        mode: JournalMode | None = None,
    ) -> Result[str]:
        """Respond to the user's follow-up without re-running the full analysis template.

        Uses follow_up_system_prompt() which adds a continuation directive on top of
        the mode's base instructions, preventing the LLM from re-producing headings
        like '# What is Emerging' for a conversational reply.

        Backend: GoalsService, TasksService, HabitsService (context summary);
                 LLMCaller (response generation).
        """
        context_summary = await self._build_context_summary(user_uid)
        system_prompt = follow_up_system_prompt(context_summary, mode)
        user_message = (
            f"# Original Note\n\n{original_entry}\n\n"
            f"# Previous Response\n\n{ai_response}\n\n"
            f"# Follow-up\n\n{user_reply}"
        )
        try:
            return await self._llm.generate(
                prompt=user_message,
                model=self._resolve_model(),
                system_prompt=system_prompt,
                max_tokens=_MAX_TOKENS,
            )
        except LLM_EXCEPTIONS as exc:
            logger.error("Journal follow-up LLM error: %s", exc)
            return Result.fail(Errors.integration("llm", f"Follow-up failed: {exc}"))
