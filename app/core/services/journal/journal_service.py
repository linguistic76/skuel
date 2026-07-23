"""Journal service — typed discussion, follow-ups, and the FOUNDER DNWF file path.

Typed door: run_discussion() opens an open, user-led conversation on the first
message (companion voice, no analysis template), run_follow_up() continues it.
Both are quote-on-demand surfaces (ADR-076) that ground on UserContext always
and on the canon shelf / vault behind the FOUNDER dials.

File / audio door: run_stage1/2/3() — Scribe → Thought Partner → What Is Related;
each stage gated by user review; run_compiled() chains them for batch uploads.
Stage functions are mode-invariant.

Entry persistence is handled by the ingestion path in the calling route,
not by this service. See: /docs/decisions/ (ADR forthcoming)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.models.enums.user_enums import JournalMode
from core.models.type_hints import UserUID
from core.services.chat import available_chat_models, resolve_chat_model
from core.services.dsl.grounding import active_goal_titles as fetch_active_goal_titles
from core.services.dsl.grounding import goals_as_context
from core.services.journal.instruction_loader import (
    discussion_system_prompt,
    follow_up_system_prompt,
    stage1_system_prompt,
    stage2_system_prompt,
    stage3_system_prompt,
)
from core.services.llm_caller import LLMCallerProtocol
from core.utils.exception_types import LLM_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports.query_types import ShelvedBook
    from core.services.canon import CanonContext, CanonRetrievalService, CanonSource
    from core.services.dsl.llm_dsl_bridge import LLMDSLBridgeService
    from core.services.goals_service import GoalsService
    from core.services.habits_service import HabitsService
    from core.services.journal.suggestion import SuggestedActivity
    from core.services.tasks_service import TasksService
    from core.services.user_entry.user_entry_service import UserEntryService

logger = get_logger("skuel.services.journal")


@dataclass(frozen=True)
class JournalFollowUp:
    """A follow-up turn's result — the reply text plus structured sources.

    ``text`` is the conversational reply (with the model's inline quotes/citations
    when a corpus was summoned). ``sources`` are the shelf books and/or vault
    notes it drew on (``CanonSource.source_kind`` discriminates), kept structured
    so the plain-text journal bubble can render a real, clickable link to each —
    the book's Resource page or the note's ``/gradebook/{uid}`` detail (ADR-076;
    Codex #572 P2) rather than literal markdown. Empty ``sources`` on an
    ungrounded follow-up.
    """

    text: str
    sources: tuple[CanonSource, ...]


_MAX_TOKENS = 4000
_STAGE3_MAX_TOKENS = 3000


class JournalService:
    """Orchestrates journal workflows across both doors.

    Typed door: run_discussion() opens a user-led conversation, run_follow_up()
    continues it. File/audio door: run_stage1/2/3() + run_compiled() (DNWF).

    Backend: UserEntryService (persistence); GoalsService/TasksService/HabitsService
    (user-context summaries); CanonRetrievalService (shelf + vault grounding);
    LLMCaller (all AI responses).
    """

    def __init__(
        self,
        llm_caller: LLMCallerProtocol,
        user_entry_service: UserEntryService,
        goals_service: GoalsService | None = None,
        tasks_service: TasksService | None = None,
        habits_service: HabitsService | None = None,
        dsl_bridge: LLMDSLBridgeService | None = None,
        canon_retrieval_service: CanonRetrievalService | None = None,
    ) -> None:
        self._llm = llm_caller
        self._user_entry = user_entry_service
        self._goals = goals_service
        self._tasks = tasks_service
        self._habits = habits_service
        # Optional Digital pre-pass that turns prose into @context() lines for
        # the "Suggested activities" panel. None on CORE tier (no panel).
        self._dsl_bridge = dsl_bridge
        # Optional canon shelf — voice-infuses a summoned Stage 2/3 with curated
        # book passages. None when unwired (CORE tier / no embeddings). The same
        # service carries the vault side (retrieve_vault, canon P3) behind the
        # second dial.
        self._canon = canon_retrieval_service

    def _resolve_model(self, requested: str | None = None) -> str:
        """Gate a per-conversation model choice to one the caller can serve.

        The Journals half of the LLM switcher seam: the discussion's chosen model
        (from the composer picker) wins when supported, else it degrades
        OpenAI-safe to the app default (see ``core.services.chat``). ``None`` — the
        DNWF file/audio stages, which carry no picker — rides the safe default.
        """
        return resolve_chat_model(requested, self._llm)

    def available_chat_models(self) -> list[tuple[str, str]]:
        """Headline chat models the caller can serve — the discussion picker's options.

        Options come from the wired caller, so a dev env with no Anthropic adapter
        offers only OpenAI models. Empty renders no picker (fails soft).
        """
        return available_chat_models(self._llm)

    @property
    def suggestions_available(self) -> bool:
        """Whether the activity-suggestion bridge is wired (FULL tier + OpenAI key).

        ``JournalService`` can exist (``llm_caller`` present) while the DSL bridge
        is ``None`` — e.g. FULL tier with an Anthropic key but no OpenAI key. The
        suggestions route checks this so a bridge-unavailable empty result is
        never cached (a poisoned empty panel would survive a later key change).
        """
        return self._dsl_bridge is not None

    # ------------------------------------------------------------------
    # User-context summary (used by Stage 2 and Stage 3 prompts)
    # ------------------------------------------------------------------

    async def _build_context_summary(
        self, user_uid: UserUID, include_vault_notes: bool = True
    ) -> str:
        """Return a short text digest of the user's active goals/tasks/habits/vault notes.

        ``include_vault_notes=False`` drops the shallow recency-ordered note
        snippets — the vault dial's grounded retrieval block replaces them
        (canon P3 de-dup: never both the shallow and the semantic read of the
        same corpus in one prompt). Callers pass ``False`` only when the
        grounded block actually landed (``vault.has_passages``) — a dial-on
        retrieval miss keeps the snippets, so grounding never drops below the
        dial-off state. Dial off → byte-identical digest.
        """
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

        if include_vault_notes:
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
        self,
        content: str,
        user_uid: UserUID,
        active_goal_titles: list[str] | None = None,
    ) -> Result[list[SuggestedActivity]]:
        """Recognise candidate activities in journal text as paste-ready DSL lines.

        Runs the LLM bridge over ``content`` (grounded in the user's active
        goals), then re-renders the result into canonical checkbox DSL. The
        lines are *inert suggestions* — the caller surfaces them for the user to
        copy into a Periodic Note or extraction folder; nothing is created here.

        ``active_goal_titles`` lets the caller inject the *same* goal snapshot it
        used to build the cache key, so a cached panel is always keyed by the
        grounding that actually produced it (no fetch-twice skew). When ``None``,
        the titles are fetched here.

        Returns an empty list (not an error) when the bridge is unavailable
        (CORE tier) or the content is blank — the panel renders a neutral state.

        Backend: GoalsService (grounding); LLMDSLBridgeService (recognition).
        """
        from core.services.journal.suggestion import build_suggestions

        if self._dsl_bridge is None or not content or not content.strip():
            return Result.ok([])

        if active_goal_titles is None:
            # Grounding is a soft signal: a goals-query failure degrades to no
            # grounding rather than failing the whole suggestion pass.
            titles_result = await self.active_goal_titles(user_uid)
            active_goal_titles = titles_result.value if titles_result.is_ok else []

        transform = await self._dsl_bridge.transform_with_context(
            content, user_uid, active_goals=goals_as_context(active_goal_titles)
        )
        if transform.is_error:
            return Result.fail(transform)

        return Result.ok(build_suggestions(transform.value.activity_lines))

    async def active_goal_titles(self, user_uid: UserUID) -> Result[list[str]]:
        """Titles of the user's active goals — the grounding fed to the bridge.

        The suggestions route fetches this once, derives the cache key from it,
        and passes the same snapshot back into ``suggest_activities`` so the
        cached fingerprint can never drift from the context that produced the
        suggestions. The same grounding builder feeds the EXTRACT_ACTIVITIES
        extractor, so the inert preview and the entity-creating path share one
        grounding source (`core.services.dsl.grounding`).

        Grounding is soft: the shared builder already degrades a missing goals
        service / query failure to ``[]`` (ungrounded). This service method wraps
        that in ``Result.ok`` to honour the uniform service contract (AGENTS.md:
        services return ``Result[T]``); callers keep the ``.is_error``/``.value``
        shape and treat an empty list as "no grounding".

        Backend: GoalsService.get_active (via core.services.dsl.grounding).
        """
        return Result.ok(await fetch_active_goal_titles(self._goals, user_uid))

    # ------------------------------------------------------------------
    # Canon shelf (the "summon" dial)
    # ------------------------------------------------------------------

    async def _maybe_summon_canon(
        self,
        raw_entry: str,
        summon: bool,
        resource_uids: list[str] | None = None,
    ) -> CanonContext:
        """Resolve the canon context for a stage — THE single dial branch point.

        Fail-soft: dial off, no canon service (CORE tier / no embeddings), or a
        retrieval failure all collapse to an empty ``CanonContext`` so the stage
        proceeds as a normal journal. Graduating the dial to automatic later
        means changing only this method (consult prefs/heuristics here) — the
        call sites stay untouched.

        ``resource_uids`` scopes the draw to the books the discussion picked
        (C3 shelf checkboxes → ``retrieve(resource_uids=...)``); ``None`` draws
        the whole shelf (the DNWF stage/compile default). ``summon`` is still
        the master switch — an off dial returns empty regardless of scope.
        """
        from core.services.canon import CanonContext

        if not summon or self._canon is None:
            return CanonContext.empty()
        result = await self._canon.retrieve(raw_entry, resource_uids=resource_uids)
        return result.value if result.is_ok else CanonContext.empty()

    async def _maybe_summon_vault(
        self, query_text: str, user_uid: UserUID, summon: bool
    ) -> CanonContext:
        """Resolve the vault context for a stage — the second dial's branch point.

        The canon P3 sibling of ``_maybe_summon_canon``: owner-scoped retrieval
        over the user's non-private knowledge notes. Same fail-soft contract —
        dial off, no canon service, or a retrieval failure all collapse to an
        empty ``CanonContext`` so the stage proceeds ungrounded.
        """
        from core.services.canon import CanonContext

        if not summon or self._canon is None:
            return CanonContext.empty()
        result = await self._canon.retrieve_vault(query_text, user_uid)
        return result.value if result.is_ok else CanonContext.empty()

    async def list_canon_shelf(self) -> Result[list[ShelvedBook]]:
        """List the books on the canon shelf for the discussion source picker.

        Returns an empty list (not an error) when no canon service is wired
        (CORE tier / no embeddings) — the composer simply renders no picker.
        The route calls this only for FOUNDERs (the canon dial's entitlement).

        Backend: CanonRetrievalService.list_shelf.
        """
        if self._canon is None:
            return Result.ok([])
        return await self._canon.list_shelf()

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
        summon_canon: bool = False,
        summon_vault: bool = False,
    ) -> Result[str]:
        """Stage 2: Thought Partner response across four roles.

        When ``summon_canon`` is set (FULL tier), curated book passages resonant
        with the raw entry voice-infuse the reasoning; ``summon_vault`` does the
        same with the user's own non-private vault notes (canon P3) — and
        replaces the digest's shallow note snippets with the grounded block. A
        light "Drawing on" footer is appended when anything infused. Fail-soft:
        no grounding degrades to a normal Stage 2 — a vault retrieval that
        misses keeps the shallow digest, so the dial never grounds below its
        off state.
        """
        canon = await self._maybe_summon_canon(raw_entry, summon_canon)
        vault = await self._maybe_summon_vault(raw_entry, user_uid, summon_vault)
        context_summary = await self._build_context_summary(
            user_uid, include_vault_notes=not vault.has_passages
        )
        system_prompt = stage2_system_prompt(
            context_summary, canon.to_prompt_block(), vault.to_prompt_block()
        )
        user_message = (
            f"# Raw Daily Note\n\n{raw_entry}\n\n"
            f"# Stage 1 — Scribe Record\n\n{scribe_output}\n\n"
            f"# Review Notes\n\n{review_notes or '(none)'}\n\n"
            "Please process this as Stage 2 — Thought Partner."
        )
        try:
            result = await self._llm.generate(
                prompt=user_message,
                model=self._resolve_model(),
                system_prompt=system_prompt,
                max_tokens=_MAX_TOKENS,
            )
        except LLM_EXCEPTIONS as exc:
            logger.error("Journal Stage 2 LLM error: %s", exc)
            return Result.fail(Errors.integration("llm", f"Stage 2 failed: {exc}"))
        return self._append_grounding_footer(result, canon, vault)

    # ------------------------------------------------------------------
    # Stage 3 — What Is Related
    # ------------------------------------------------------------------

    async def run_stage3(
        self,
        raw_entry: str,
        thought_partner_output: str,
        review_notes: str,
        user_uid: UserUID,
        summon_canon: bool = False,
        summon_vault: bool = False,
    ) -> Result[str]:
        """Stage 3: propose graph connections to knowledge, goals, tasks, and habits.

        When ``summon_canon`` is set (FULL tier), curated book passages resonant
        with the raw entry voice-infuse the reasoning; ``summon_vault`` does the
        same with the user's own non-private vault notes (canon P3, replacing
        the digest's shallow snippets). A light "Drawing on" footer is appended
        when anything infused. Fail-soft: no grounding degrades to a normal
        Stage 3 — a vault retrieval that misses keeps the shallow digest.
        """
        canon = await self._maybe_summon_canon(raw_entry, summon_canon)
        vault = await self._maybe_summon_vault(raw_entry, user_uid, summon_vault)
        context_summary = await self._build_context_summary(
            user_uid, include_vault_notes=not vault.has_passages
        )
        system_prompt = stage3_system_prompt(
            context_summary, canon.to_prompt_block(), vault.to_prompt_block()
        )
        user_message = (
            f"# Raw Daily Note\n\n{raw_entry}\n\n"
            f"# Stage 2 — What Is Emerging\n\n{thought_partner_output}\n\n"
            f"# Review Notes\n\n{review_notes or '(none)'}\n\n"
            "Please process this as Stage 3 — What Is Related."
        )
        try:
            result = await self._llm.generate(
                prompt=user_message,
                model=self._resolve_model(),
                system_prompt=system_prompt,
                max_tokens=_STAGE3_MAX_TOKENS,
            )
        except LLM_EXCEPTIONS as exc:
            logger.error("Journal Stage 3 LLM error: %s", exc)
            return Result.fail(Errors.integration("llm", f"Stage 3 failed: {exc}"))
        return self._append_grounding_footer(result, canon, vault)

    @staticmethod
    def _append_grounding_footer(
        result: Result[str], canon: CanonContext, vault: CanonContext
    ) -> Result[str]:
        """Append ONE "Drawing on" footer to a successful stage output.

        No-op when the stage errored or nothing was drawn from either corpus —
        the footer only ever appears when the response was genuinely infused.
        Both dials on → a single merged line, never two rules.
        """
        from core.services.canon import merged_attribution_footer

        if result.is_error or not (canon.has_passages or vault.has_passages):
            return result
        return Result.ok(result.value + merged_attribution_footer(canon, vault))

    # ------------------------------------------------------------------
    # Discussion (first message of an open, user-led conversation)
    # ------------------------------------------------------------------

    async def run_discussion(
        self,
        raw_entry: str,
        user_uid: UserUID,
        mode: JournalMode | None = None,
        summon_canon: bool = False,
        summon_vault: bool = False,
        canon_book_uids: list[str] | None = None,
        model: str | None = None,
    ) -> Result[JournalFollowUp]:
        """Open a journal discussion on the user's first typed message.

        The discussion-first entry point (replaces the removed ``run_standard``):
        a companion voice that lets the user lead, with no imposed analysis
        template. UserContext is always-on grounding; ``summon_canon`` /
        ``summon_vault`` are the FOUNDER dials the route gates server-side.

        Like ``run_follow_up`` (its continuation sibling), it is a
        quote-on-demand surface (ADR-076): a summoned corpus is injected via
        ``to_discussion_block()`` so the model may name and quote it.
        ``canon_book_uids`` scopes the shelf draw to the books the composer's
        checkboxes selected (C3); ``None`` / empty with the dial on draws the
        whole shelf. Returns a ``JournalFollowUp`` — reply text plus structured
        ``sources`` the route renders as clickable citations (canon books +
        vault notes). Fail-soft: no grounding → empty ``sources``, and a vault
        miss keeps the shallow note digest.

        Backend: GoalsService, TasksService, HabitsService (context summary);
                 CanonRetrievalService (shelf + vault); LLMCaller (response).
        """
        canon = await self._maybe_summon_canon(raw_entry, summon_canon, canon_book_uids)
        vault = await self._maybe_summon_vault(raw_entry, user_uid, summon_vault)
        context_summary = await self._build_context_summary(
            user_uid, include_vault_notes=not vault.has_passages
        )
        system_prompt = discussion_system_prompt(
            context_summary, mode, canon.to_discussion_block(), vault.to_discussion_block()
        )
        user_message = raw_entry
        try:
            result = await self._llm.generate(
                prompt=user_message,
                model=self._resolve_model(model),
                system_prompt=system_prompt,
                max_tokens=_MAX_TOKENS,
            )
        except LLM_EXCEPTIONS as exc:
            logger.error("Journal discussion LLM error: %s", exc)
            return Result.fail(Errors.integration("llm", f"Journal response failed: {exc}"))
        if result.is_error:
            return Result.fail(result)
        return Result.ok(
            JournalFollowUp(text=result.value, sources=canon.sources() + vault.sources())
        )

    # ------------------------------------------------------------------
    # Compiled output
    # ------------------------------------------------------------------

    async def run_compiled(
        self,
        raw_entry: str,
        user_uid: UserUID,
        summon_canon: bool = False,
        summon_vault: bool = False,
    ) -> Result[str]:
        """Run all three DNWF stages in sequence and return a single compiled document.

        Used for file-based (batch) processing where interactive review between
        stages is not possible. Produces Stage 1 → Stage 2 → Stage 3 output with no
        review notes between stages.

        ``summon_canon`` (FULL tier) draws curated book passages into Stages 2 and
        3; ``summon_vault`` draws the user's own non-private vault notes (canon
        P3) — the file path's parallels to the interactive dials, since there is
        no review gate to check. Fail-soft: no grounding degrades to a normal
        compile.
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
            summon_canon=summon_canon,
            summon_vault=summon_vault,
        )
        if stage2.is_error:
            return stage2
        thought_partner_output = stage2.value

        stage3 = await self.run_stage3(
            raw_entry=raw_entry,
            thought_partner_output=thought_partner_output,
            review_notes="",
            user_uid=user_uid,
            summon_canon=summon_canon,
            summon_vault=summon_vault,
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
        summon_canon: bool = False,
        summon_vault: bool = False,
        canon_book_uids: list[str] | None = None,
        model: str | None = None,
    ) -> Result[JournalFollowUp]:
        """Respond to the user's follow-up without re-running the full analysis template.

        Uses follow_up_system_prompt() which adds a continuation directive on top of
        the mode's base instructions, preventing the LLM from re-producing headings
        like '# What is Emerging' for a conversational reply.

        The follow-up is the **quote-on-demand** surface (ADR-076): when
        ``summon_canon`` is set (FULL tier), canon passages resonant with the
        user's *question* (``user_reply``, not the raw entry) are injected via
        ``to_discussion_block()`` so the model may name + quote the shelf.
        ``summon_vault`` (canon P3) does the same with the user's own
        non-private vault notes, keyed on the same question. ``canon_book_uids``
        carries the discussion's book scope (the composer's C3 selection)
        forward so follow-ups stay scoped to the same shelf the session opened
        on; ``None`` draws the whole shelf. Returns a
        ``JournalFollowUp`` — the reply text plus structured ``sources``
        (books + notes, concatenated) the route renders as clickable links
        (not a markdown footer, which a plain-text bubble would show
        literally). Fail-soft: no grounding → empty ``sources`` — and a vault
        retrieval that misses keeps the shallow note digest.

        Backend: GoalsService, TasksService, HabitsService (context summary);
                 CanonRetrievalService (shelf + vault); LLMCaller (response
                 generation).
        """
        canon = await self._maybe_summon_canon(user_reply, summon_canon, canon_book_uids)
        vault = await self._maybe_summon_vault(user_reply, user_uid, summon_vault)
        context_summary = await self._build_context_summary(
            user_uid, include_vault_notes=not vault.has_passages
        )
        system_prompt = follow_up_system_prompt(
            context_summary, mode, canon.to_discussion_block(), vault.to_discussion_block()
        )
        user_message = (
            f"# Original Note\n\n{original_entry}\n\n"
            f"# Previous Response\n\n{ai_response}\n\n"
            f"# Follow-up\n\n{user_reply}"
        )
        try:
            result = await self._llm.generate(
                prompt=user_message,
                model=self._resolve_model(model),
                system_prompt=system_prompt,
                max_tokens=_MAX_TOKENS,
            )
        except LLM_EXCEPTIONS as exc:
            logger.error("Journal follow-up LLM error: %s", exc)
            return Result.fail(Errors.integration("llm", f"Follow-up failed: {exc}"))
        if result.is_error:
            return Result.fail(result)
        return Result.ok(
            JournalFollowUp(text=result.value, sources=canon.sources() + vault.sources())
        )
