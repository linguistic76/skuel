"""Journals domain routes — typed discussion door + the DNWF file/audio door.

Routes:
    GET  /journals                      — 3-column landing page (no Tasks+ sidebar)
    POST /journals/start                — open a discussion on typed text; returns response inline (zero-persistence, ADR-073)
    POST /journals/upload               — file upload handler (DNWF door)
    POST /journals/folder-process       — batch folder processing
    GET  /journals/je-out/{filename}    — download a journal output from je_out/
    GET  /journals/{entry_uid}          — periodic-note page (daily/weekly/monthly)
    POST /journals/follow-up            — conversation continuation (all tiers)
    POST /journals/stage1               — Stage 1 Scribe (FOUNDER audio door, FULL tier)
    POST /journals/stage2               — Stage 2 Thought Partner (FOUNDER audio door, FULL tier)
    POST /journals/stage3               — Stage 3 What Is Related (FOUNDER audio door, FULL tier)
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from starlette.responses import HTMLResponse, RedirectResponse, Response

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.rate_limit import LLM_QUOTA_MESSAGE, llm_quota_allowed, rate_limited
from core.services.chat import DEFAULT_CHAT_MODEL
from core.services.conversation import (
    build_source_selection,
    history_to_follow_up_context,
    parse_source_selection,
    parse_transcript,
    render_discussion_markdown,
    render_follow_up_context,
    safe_export_filename,
    serialize_transcript,
    transcript_to_pairs,
)
from core.services.intelligence_tier_service import get_user_intelligence_tier
from core.utils.logging import get_logger
from ui.journals.components import render_upload_status as render_journal_upload_status

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.models.type_hints import UserUID
    from core.models.user.user import User
    from core.services.journal import BatchRunReport, JournalBatchService
    from services_bootstrap._container import Services


logger = get_logger("skuel.routes.journals")

# Shown to effective-CORE users on every gated fragment — mirrors the
# Errors.forbidden reason used across the AI surfaces (askesis, exercises…).
AI_SUBSCRIPTION_MESSAGE = (
    "AI features require a paid subscription. Upgrade to MEMBER to unlock AI journals."
)


# ---------------------------------------------------------------------------
# Helpers
#
# The je_in/upload → je_out batch pipeline (transcription, LLM compile,
# exemplar injection, the je_* staging-folder layout) lives in
# ``core.services.journal.JournalBatchService`` — routes here only parse the
# request, gate auth/tier, call the service, and render fragments.
# ---------------------------------------------------------------------------


def _render_batch_report(report: BatchRunReport, status_id: str) -> Any:
    """Render a ``BatchRunReport`` as the upload-status fragment."""
    return render_journal_upload_status(
        "completed" if report.ok else "error",
        report.message,
        is_error=not report.ok,
        status_id=status_id,
    )


async def _process_single_upload(
    *,
    file_content: bytes,
    filename: str,
    title: str,
    processing_mode: str,
    instructions: str | None,
    user_uid: UserUID,
    is_founder: bool,
    retarget_workspace: bool,
    journal_batch: JournalBatchService,
    summon_canon: bool = False,
    summon_vault: bool = False,
) -> Any:
    """Process one uploaded file to ``je_out/`` and return an inline fragment.

    Zero-persistence (ADR-073): no ``UserEntry`` is created. Text files compile
    via the LLM; audio transcribes via Deepgram. FOUNDER audio hands the
    transcript to the interactive DNWF review→Scribe flow; everyone else gets a
    ``je_out/`` file plus a download fragment.
    """
    from fasthtml.common import to_xml

    from core.models.conversation import ROLE_ASSISTANT, ROLE_USER
    from ui.journals import FileOutputFragment, TranscriptReviewFragment

    # canon=[] (whole shelf) — the upload form carries no per-book picker (C3);
    # the door's coarse booleans ride the composer so a Save records them.
    def _file_transcript(source_text: str, output: str) -> str:
        """The source→output opening pair (Option A) as a structured transcript."""
        return serialize_transcript([(ROLE_USER, source_text), (ROLE_ASSISTANT, output)])

    def _workspace(fragment: Any) -> Any:
        # Success fragments are rooted at ``#journal-workspace``. On the
        # ``/journals`` landing (``retarget_workspace``) the form posts with
        # ``hx_target="#upload-status"`` (right panel), so retarget to the centre
        # workspace in place — mirrors ``/journals/start``. On pages without a
        # workspace (``/submissions/journal``) return the fragment unwrapped so it
        # swaps into the form's own ``#upload-status`` target instead of retargeting
        # to a missing element.
        if not retarget_workspace:
            return fragment
        return HTMLResponse(
            to_xml(fragment),
            headers={"HX-Retarget": "#journal-workspace", "HX-Reswap": "outerHTML"},
        )

    stem = Path(filename).stem

    if processing_mode == "instructions_only":
        try:
            text_content = file_content.decode("utf-8")
        except UnicodeDecodeError:
            return render_journal_upload_status(
                "error",
                "File must be valid UTF-8 text for Instructions only mode",
                is_error=True,
            )
        compiled = await journal_batch.compile_text(
            text_content,
            instructions,
            user_uid=user_uid,
            is_founder=is_founder,
            summon_canon=summon_canon,
            summon_vault=summon_vault,
        )
        if compiled.is_error:
            return render_journal_upload_status("error", str(compiled.error), is_error=True)
        out_name = journal_batch.write_output(stem, "_out.md", compiled.value)
        return _workspace(
            FileOutputFragment(
                title=title,
                output_filename=out_name,
                response_output=compiled.value,
                is_founder=is_founder,
                transcript_json=_file_transcript(text_content, compiled.value),
                summon_canon=summon_canon,
                summon_vault=summon_vault,
            )
        )

    # Transcription modes (audio) — require Deepgram (FULL tier).
    if not journal_batch.transcription_available:
        return render_journal_upload_status(
            "error", "Transcription service not available (requires FULL tier)", is_error=True
        )

    # Preflight the LLM step before spending Deepgram quota: STANDARD
    # transcribe_and_instructions compiles the transcript via the LLM, so a
    # missing llm_caller must fail up front. (FOUNDER goes to review→Scribe and
    # does not compile here, so it needs no LLM at this stage.)
    if (
        processing_mode == "transcribe_and_instructions"
        and not is_founder
        and not journal_batch.llm_available
    ):
        return render_journal_upload_status(
            "error", "LLM service not available (requires INTELLIGENCE_TIER=full)", is_error=True
        )

    transcript_result = await journal_batch.transcribe_upload(
        file_content, Path(filename).suffix or ".audio"
    )
    if transcript_result.is_error:
        logger.error("Single-file transcription failed: %s", transcript_result.expect_error())
        return render_journal_upload_status(
            "error", "Transcription failed — please try again.", is_error=True
        )
    transcript = transcript_result.value

    if is_founder:
        # FOUNDER: save the raw transcript to je_out and hand it to the DNWF
        # review→Scribe flow (stateless stage routes take over from here).
        journal_batch.write_output(stem, ".txt", transcript)
        return _workspace(TranscriptReviewFragment(transcript=transcript, title=title))

    if processing_mode == "transcribe_and_instructions":
        compiled = await journal_batch.compile_text(
            transcript,
            instructions,
            user_uid=user_uid,
            is_founder=False,
        )
        if compiled.is_error:
            return render_journal_upload_status("error", str(compiled.error), is_error=True)
        out_name = journal_batch.write_output(stem, "_out.md", compiled.value)
        return _workspace(
            FileOutputFragment(
                title=title,
                output_filename=out_name,
                response_output=compiled.value,
                is_founder=is_founder,
                transcript_json=_file_transcript(transcript, compiled.value),
                summon_canon=summon_canon,
                summon_vault=summon_vault,
            )
        )

    # transcribe_only (STANDARD) — raw transcript download. source == output, so
    # a synthetic "Transcribe: {title}" user turn avoids duplicating the full
    # transcript in both turns (ADR-078 P3 decision 3, transcribe_only).
    out_name = journal_batch.write_output(stem, ".txt", transcript)
    return _workspace(
        FileOutputFragment(
            title=title,
            output_filename=out_name,
            response_output=transcript,
            is_founder=is_founder,
            transcript_json=_file_transcript(f"Transcribe: {title}", transcript),
            summon_canon=summon_canon,
            summon_vault=summon_vault,
        )
    )


# ---------------------------------------------------------------------------
# Route factory
# ---------------------------------------------------------------------------


def create_journals_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    services: Services,
) -> None:
    """Register Journal domain routes."""

    assert services.user is not None, "UserService must be wired before journals routes"
    user_service = services.user
    intelligence_tier = services.intelligence_tier  # system ceiling for the per-user AI gate
    journal_service = services.journal  # None when INTELLIGENCE_TIER=core
    user_entry_service = services.user_entry
    # The je_in/upload → je_out pipeline engine — tier-independent (present in
    # CORE and FULL; each mode degrades to its tier-error message internally).
    assert services.journal_batch is not None, (
        "JournalBatchService must be wired before journals routes"
    )
    journal_batch = services.journal_batch
    # ADR-078 discussion store — tier-independent (present in CORE and FULL), but
    # only reached at FULL tier since /journals/start requires journal_service.
    assert services.conversation is not None, (
        "ConversationService must be wired before journals routes"
    )
    conversation_service = services.conversation

    async def _load_ai_gated_user(user_uid: UserUID) -> tuple[User | None, str]:
        """Load the user behind the per-user AI gate (ADR-043) + daily LLM quota.

        Returns ``(user, "")`` when the gate passes, ``(None, denial_message)``
        when denied — the message distinguishes the subscription denial from
        the daily-quota denial, so a MEMBER at quota is never told to upgrade.

        REGISTERED signups resolve to effective CORE even on a FULL system, so
        they must never reach ``run_discussion``/``run_follow_up``/the upload
        pipeline — each call spends OpenAI/Deepgram money. Fail-secure: a
        missing tier or a failed user lookup means the gate cannot be
        evaluated, so deny rather than allow (mirrors ``askesis_ui.py``).

        The daily quota is checked LAST so subscription-denied users never
        record units (and always see the upgrade message). One unit per gated
        request, recorded at gate time — coarse but sufficient for a cost
        ceiling (``core.constants.LLMQuota``).

        Returns the loaded ``User`` so ONE lookup serves both this gate and any
        FOUNDER entitlement check on the same request — callers read
        ``user.journal_tier.is_founder()`` off the returned object instead of a
        second ``_resolve_founder`` load (pinned by
        ``test_journals_follow_up_gate.py``).
        """
        if intelligence_tier is None:
            return None, AI_SUBSCRIPTION_MESSAGE
        user_result = await user_service.get_user(user_uid)
        if user_result.is_error or user_result.value is None:
            return None, AI_SUBSCRIPTION_MESSAGE
        if not get_user_intelligence_tier(intelligence_tier, user_result.value.role).ai_enabled:
            return None, AI_SUBSCRIPTION_MESSAGE
        if not llm_quota_allowed(user_uid):
            return None, LLM_QUOTA_MESSAGE
        return user_result.value, ""

    async def _resolve_founder(user_uid: UserUID) -> bool:
        """THE FOUNDER-tier gate for journals entitlements (fail-closed).

        A POST flag is forgeable, so every founder entitlement resolves the tier
        server-side through this one helper — a load error reads as not-founder,
        never as founder (a drifted hand-rolled copy could silently open a paid
        feature). Handlers that already load the full ``User`` for the page use
        ``user.journal_tier.is_founder()`` directly on that object instead.
        """
        user_result = await user_service.get_user(user_uid)
        return (
            user_result.is_ok
            and user_result.value is not None
            and user_result.value.journal_tier.is_founder()
        )

    # ------------------------------------------------------------------
    # GET /journals — landing page
    # ------------------------------------------------------------------

    @rt("/journals", methods=["GET"])
    async def journals_page(request: Request) -> Any:
        user_uid = require_authenticated_user(request)

        from ui.journals.chat_page import JournalsLandingPage

        user_result = await user_service.get_user(user_uid)
        if user_result.is_error or user_result.value is None:
            return Response("Could not load user", status_code=500)
        user = user_result.value

        # The canon shelf source-picker is a FOUNDER dial (like the follow-up
        # composer's), so only FOUNDERs pay the shelf read. Fail-soft: an empty
        # list (CORE tier / no canon / read error) renders no picker.
        shelf_books: list[dict[str, str]] = []
        if user.journal_tier.is_founder() and journal_service is not None:
            shelf_result = await journal_service.list_canon_shelf()
            if shelf_result.is_ok:
                shelf_books = [
                    {"resource_uid": b["resource_uid"], "title": b["title"]}
                    for b in shelf_result.value
                ]

        # Revisit list (ADR-078): the user's owned discussion sessions, most-
        # recent first. Tier-independent + fail-soft — a read error or CORE tier
        # (no sessions created) simply renders the empty-state hint.
        sessions_result = await conversation_service.list_sessions(user_uid)
        sessions = sessions_result.value if sessions_result.is_ok else []

        # LLM-switcher options for the start-form picker (from the wired caller;
        # empty on CORE / no journal_service → no picker, safe default).
        model_options = journal_service.available_chat_models() if journal_service else []

        page_content = JournalsLandingPage(
            user=user, shelf_books=shelf_books, sessions=sessions, model_options=model_options
        )

        if request.headers.get("HX-Request"):
            return page_content

        from ui.layouts.base_page import BasePage
        from ui.layouts.page_types import PageType

        return BasePage(
            content=page_content,
            title="Journal",
            page_type=PageType.CUSTOM,
            request=request,
            active_page="journals",
        )

    # ------------------------------------------------------------------
    # POST /journals/start — run the workflow on typed text, return inline
    # ------------------------------------------------------------------

    @rt("/journals/start", methods=["POST"])
    @csrf_protected
    @rate_limited(per_user=10, window_s=60)
    async def journals_start(request: Request) -> Any:
        """Open a journal discussion on typed text and return it inline.

        Zero-persistence (ADR-073): the journal is a private workshop — nothing is
        written to the database. Both tiers get the same discussion experience
        (ruling: typed = discussion): a companion voice that lets the user lead
        (``run_discussion``). UserContext grounds every discussion; the canon
        shelf checkboxes and the vault toggle are FOUNDER dials, gated
        server-side (a forgeable POST flag can't unlock them for other tiers).
        The DNWF Scribe→Thought-Partner→What-Is-Related staging lives on the
        file/audio door, not here. Follow-ups run through ``/journals/follow-up``.

        On success returns ``StandardResponseFragment`` retargeted from the
        form's default ``#start-status`` to ``#journal-workspace`` so it replaces
        the landing centre in place. On error returns an inline message swapped
        into ``#start-status``.
        """
        from fasthtml.common import Div as _Div
        from fasthtml.common import P as _P
        from fasthtml.common import to_xml

        from core.models.enums.user_enums import JournalMode
        from ui.journals import StandardResponseFragment

        def _err(msg: str) -> Any:
            return _Div(_P(msg, cls="text-sm text-destructive"), id="start-status")

        user_uid = require_authenticated_user(request)

        gated_user, gate_denial = await _load_ai_gated_user(user_uid)
        if gated_user is None:
            return _err(gate_denial)

        form = await request.form()
        raw_entry = str(form.get("raw_entry", "")).strip()

        if not raw_entry:
            return _err("Please write something before continuing.")

        if journal_service is None:
            return _err("Journal AI features are not available.")

        is_founder = gated_user.journal_tier.is_founder()
        # Title = first ~60 chars of the opening message, no LLM (ADR-078 refinement
        # 2) — a deterministic label, inline-editable in the revisit list.
        title = raw_entry.split("\n")[0].strip()[:60] or "Journal Entry"

        # Source dials (FOUNDER entitlements — gated server-side). The canon
        # shelf is per-book checkboxes: the checked ``resource_uids`` scope the
        # draw (C3), and any book checked means "summon canon". The vault is a
        # single toggle. Non-FOUNDERs discuss on UserContext alone.
        canon_book_uids = (
            [u for u in form.getlist("canon_book_uids") if isinstance(u, str) and u]
            if is_founder
            else []
        )
        summon_vault = is_founder and str(form.get("summon_vault", "")).strip().lower() == "true"
        summon_canon = bool(canon_book_uids)

        # Per-conversation model choice from the start-form picker (gated
        # OpenAI-safe in the service; the picker only offers serveable models).
        model = str(form.get("model", "")).strip()

        ai_result = await journal_service.run_discussion(
            raw_entry,
            user_uid,
            JournalMode.default(),
            summon_canon=summon_canon,
            summon_vault=summon_vault,
            canon_book_uids=canon_book_uids or None,
            model=model or None,
        )

        if ai_result.is_error:
            logger.error(
                "journals_start AI call failed for %s: %s",
                user_uid,
                ai_result.expect_error(),
            )
            return _err("Could not generate a response. Please try again.")

        ai_text = ai_result.value.text

        # Ephemeral by default (ADR-078 §5, founder realignment 2026-07-13): a
        # discussion is NOT saved automatically. The opening user/assistant pair
        # rides the composer as a structured ``transcript_json`` accumulator that
        # dies on reload; nothing is written to the store until the user presses
        # *Save this chat* (POST /journals/save). This reverts P2's create-on-
        # first-reply auto-save (guard 7, ADR-078 §7).
        from core.models.conversation import ROLE_ASSISTANT, ROLE_USER

        transcript_json = serialize_transcript([(ROLE_USER, raw_entry), (ROLE_ASSISTANT, ai_text)])

        workspace = StandardResponseFragment(
            raw_entry=raw_entry,
            title=title,
            response_output=ai_text,
            transcript_json=transcript_json,
            mode=JournalMode.default(),
            is_founder=is_founder,
            sources=ai_result.value.sources,
            canon_book_uids=tuple(canon_book_uids),
            # Pre-check the composer dials to the opening grounding so a later
            # *Save* records the source selection the door actually used, not an
            # off-by-default one (Codex #638 P2).
            summon_canon=summon_canon,
            summon_vault=summon_vault,
            # Carry the chosen model into the composer so follow-ups keep it and a
            # later Save records it.
            model=model,
            model_options=journal_service.available_chat_models(),
        )

        return HTMLResponse(
            to_xml(workspace),
            headers={"HX-Retarget": "#journal-workspace", "HX-Reswap": "outerHTML"},
        )

    # ------------------------------------------------------------------
    # POST /journals/upload — file upload handler
    # ------------------------------------------------------------------

    @rt("/journals/upload", methods=["POST"])
    @csrf_protected
    @rate_limited(per_user=10, window_s=60)
    async def journals_upload(request: Request) -> Any:
        """HTMX endpoint for journal file upload — zero-persistence (ADR-073).

        Three processing modes driven by the ``processing_mode`` form field:
        - ``transcribe_only``            — audio → transcript (Deepgram)
        - ``transcribe_and_instructions``— audio → transcript → LLM structuring
        - ``instructions_only``          — text file → LLM compile

        Every path writes its output to the user's own ``je_out/`` folder and
        returns an inline fragment — nothing is written to Neo4j. A single file
        gets a rich inline result (FOUNDER audio → transcript review → Scribe);
        multiple files run the shared batch engine to ``je_out/``.
        """
        import tempfile

        from starlette.datastructures import UploadFile

        try:
            user_uid = require_authenticated_user(request)
            form = await request.form()
            raw_title = form.get("title")
            custom_title = str(raw_title).strip() if raw_title else ""

            upload_source = str(form.get("upload_source", "file"))
            status_id = "folder-upload-status" if upload_source == "folder" else "upload-status"

            # Every upload mode spends external-API money (Deepgram and/or LLM),
            # so the whole route sits behind the per-user AI gate.
            gated_user, gate_denial = await _load_ai_gated_user(user_uid)
            if gated_user is None:
                return render_journal_upload_status(
                    "error", gate_denial, is_error=True, status_id=status_id
                )

            raw_files = form.getlist("file")
            uploaded_files = [f for f in raw_files if isinstance(f, UploadFile)]

            if not uploaded_files:
                return render_journal_upload_status(
                    "error", "No file provided", is_error=True, status_id=status_id
                )

            max_journal_files = 20
            if len(uploaded_files) > max_journal_files:
                return render_journal_upload_status(
                    "error",
                    f"Too many files: {len(uploaded_files)} (max {max_journal_files})",
                    is_error=True,
                    status_id=status_id,
                )

            processing_mode = str(form.get("processing_mode", "transcribe_only")).strip()
            instruction_filename = str(form.get("instruction_filename", "")).strip()
            instruction_content = str(form.get("instruction_content", "")).strip()
            instructions = journal_batch.resolve_instructions(
                instruction_content=instruction_content,
                instruction_filename=instruction_filename,
                processing_mode=processing_mode,
            )

            is_founder = gated_user.journal_tier.is_founder()

            # Only the /journals landing form carries a #journal-workspace to
            # retarget into; the /submissions/journal form omits this flag and
            # keeps its result in #upload-status (Codex #478).
            retarget_workspace = bool(form.get("workspace_target"))

            # Grounding dials for the file path (FOUNDER instructions_only):
            # the compile has no review gate to check, so the intent rides the
            # upload form. Absent/anything-but-"true" → ungrounded (default).
            summon_canon = str(form.get("summon_canon", "")).strip().lower() == "true"
            summon_vault = str(form.get("summon_vault", "")).strip().lower() == "true"

            if len(uploaded_files) == 1:
                uploaded_file = uploaded_files[0]
                file_content = await uploaded_file.read()
                filename = uploaded_file.filename or "unknown"
                title = custom_title or filename
                return await _process_single_upload(
                    file_content=file_content,
                    filename=filename,
                    title=title,
                    processing_mode=processing_mode,
                    instructions=instructions,
                    user_uid=user_uid,
                    is_founder=is_founder,
                    retarget_workspace=retarget_workspace,
                    journal_batch=journal_batch,
                    summon_canon=summon_canon,
                    summon_vault=summon_vault,
                )

            # Multiple files — write to a temp dir and run the shared batch engine
            # (same je_in → je_out cycle as /journals/folder-process). No entries.
            #
            # Only files the selected mode actually processes produce je_out output,
            # so only those can collide — dedup by stem within that filtered set
            # (an ignored ``meeting.txt`` next to ``meeting.mp3`` under "Transcribe
            # only" is not a collision). Non-processed files are still written to
            # temp; the batch engine ignores them.
            from core.services.journal.journal_batch_service import TEXT_EXTENSIONS
            from core.services.transcription.batch_transcription_service import AUDIO_EXTENSIONS

            output_exts = (
                TEXT_EXTENSIONS if processing_mode == "instructions_only" else (AUDIO_EXTENSIONS)
            )
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = Path(tmp_dir)
                seen_stems: set[str] = set()
                for uploaded_file in uploaded_files:
                    name = Path(uploaded_file.filename or "unknown").name
                    # The batch writes je_out outputs by stem (``{stem}.txt`` /
                    # ``{stem}_out.md``), so two output-producing files sharing a stem
                    # (``meeting.mp3`` + ``meeting.wav``) would collapse — reject that.
                    if Path(name).suffix.lower() in output_exts:
                        file_stem = Path(name).stem
                        if file_stem in seen_stems:
                            return render_journal_upload_status(
                                "error",
                                f"Two files map to the same je_out/ output ('{file_stem}') "
                                "in this batch. Rename one and retry.",
                                is_error=True,
                                status_id=status_id,
                            )
                        seen_stems.add(file_stem)
                    (tmp_path / name).write_bytes(await uploaded_file.read())
                report = await journal_batch.run_batch_over_dir(
                    tmp_path,
                    processing_mode,
                    instructions,
                    # Uploads are fresh content — never reuse a stale same-stem
                    # transcript already sitting in the flat je_out/ folder.
                    skip_existing=False,
                )
                return _render_batch_report(report, status_id)

        except Exception as e:  # safety-net: HTMX fragment error boundary
            logger.error(f"Error uploading journal: {e}", exc_info=True)
            return render_journal_upload_status("error", f"Upload failed: {e}", is_error=True)

    # ------------------------------------------------------------------
    # POST /journals/folder-process — batch folder processing
    # ------------------------------------------------------------------

    @rt("/journals/folder-process", methods=["POST"])
    @csrf_protected
    @rate_limited(per_user=5, window_s=60)
    async def journals_folder_process(request: Request) -> Any:
        """HTMX endpoint: process every file in je_in/ with the selected pipeline.

        Zero-persistence (ADR-073): scans the user's own je_in/ folder, writes
        outputs to je_out/ via the shared batch engine, and touches Neo4j zero
        times — the same file-based cycle as multi-file upload.
        """
        try:
            user_uid = require_authenticated_user(request)

            # Same cost surface as /journals/upload (Deepgram and/or LLM per file).
            gated_user, gate_denial = await _load_ai_gated_user(user_uid)
            if gated_user is None:
                return render_journal_upload_status("error", gate_denial, is_error=True)

            form = await request.form()
            processing_mode = str(form.get("processing_mode", "transcribe_only")).strip()
            instruction_filename = str(form.get("instruction_filename", "")).strip()
            instruction_content = str(form.get("instruction_content", "")).strip()
            instructions = journal_batch.resolve_instructions(
                instruction_content=instruction_content,
                instruction_filename=instruction_filename,
                processing_mode=processing_mode,
            )

            report = await journal_batch.run_batch_over_dir(
                journal_batch.je_in_dir,
                processing_mode,
                instructions,
            )
            return _render_batch_report(report, "upload-status")

        except Exception as e:  # safety-net: HTMX fragment error boundary
            logger.error(f"Error in folder-process: {e}", exc_info=True)
            return render_journal_upload_status("error", f"Processing failed: {e}", is_error=True)

    # ------------------------------------------------------------------
    # GET /journals/je-out/{filename} — download compiled journal output
    # ------------------------------------------------------------------

    @rt("/journals/je-out/{filename}", methods=["GET"])
    def journals_download_output(request: Request, filename: str) -> Any:
        """Serve a journal output from je_out/ as a file download.

        je_out/ is the user's own, flat, local staging folder (ADR-073): outputs
        are written there by the recognised rename formula (``.txt`` transcripts,
        ``_out.md`` compiled) and opened directly in Obsidian — the download link
        is a convenience. It is excluded from vault sync; SKUEL never auto-syncs
        je_out/ into the vault. The filename guard blocks traversal out of it.

        Single-user-local by design (one vault per install): the flat folder has
        no per-user scoping, so on a hypothetical shared-filesystem multi-tenant
        deployment one authenticated user could overwrite/download another's
        output by basename. Accepted-as-designed for the local-Obsidian model;
        hosting would resolve je_out/ per-user (or add a per-output token). See
        ADR-073 § Consequences (residual, flat je_out) — Codex review, PR #478.
        """
        from starlette.responses import FileResponse

        require_authenticated_user(request)

        # Guard: no path traversal; only the two recognised output extensions.
        if "/" in filename or "\\" in filename or ".." in filename:
            return Response("Not found", status_code=404)
        if not (filename.endswith(".md") or filename.endswith(".txt")):
            return Response("Not found", status_code=404)

        candidate = (journal_batch.je_out_dir / filename).resolve()
        try:
            candidate.relative_to(journal_batch.je_out_dir.resolve())
        except ValueError:
            return Response("Not found", status_code=404)

        if not candidate.is_file():
            return Response("File not found", status_code=404)

        media_type = (
            "text/markdown; charset=utf-8"
            if filename.endswith(".md")
            else "text/plain; charset=utf-8"
        )
        return FileResponse(
            path=str(candidate),
            media_type=media_type,
            filename=filename,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # ------------------------------------------------------------------
    # GET /journals/daily/{date_str}  — find-or-create daily note
    # GET /journals/weekly/{year}/{week} — find-or-create weekly note
    # GET /journals/monthly/{year}/{month} — find-or-create monthly note
    #
    # These must be declared before the {entry_uid} catch-all below.
    # FastHTML resolves routes in declaration order.
    # ------------------------------------------------------------------

    # The UID-minting scheme + find-or-create live in
    # ``UserEntryService.ensure_periodic_note`` (the persistence contract);
    # routes only compute the period key + display title and redirect.

    @rt("/journals/daily/{date_str}", methods=["GET"])
    async def journal_daily_note(request: Request, date_str: str) -> Any:
        user_uid = require_authenticated_user(request)
        if user_entry_service is None:
            return Response("Service unavailable", status_code=503)
        try:
            target_date = date.fromisoformat(date_str)
        except ValueError:
            target_date = date.today()
        ensured = await user_entry_service.ensure_periodic_note(
            user_uid,
            "daily",
            target_date.isoformat(),
            f"Daily Note: {target_date.strftime('%A, %B %d, %Y')}",
        )
        if ensured.is_error:
            return Response("Error loading note", status_code=500)
        return RedirectResponse(f"/journals/{ensured.value}", status_code=302)

    @rt("/journals/weekly/{year}/{week}", methods=["GET"])
    async def journal_weekly_note(request: Request, year: int, week: int) -> Any:
        user_uid = require_authenticated_user(request)
        if user_entry_service is None:
            return Response("Service unavailable", status_code=503)
        ensured = await user_entry_service.ensure_periodic_note(
            user_uid, "weekly", f"{year}-W{week:02d}", f"Weekly Note: W{week}, {year}"
        )
        if ensured.is_error:
            return Response("Error loading note", status_code=500)
        return RedirectResponse(f"/journals/{ensured.value}", status_code=302)

    @rt("/journals/monthly/{year}/{month}", methods=["GET"])
    async def journal_monthly_note(request: Request, year: int, month: int) -> Any:
        user_uid = require_authenticated_user(request)
        if user_entry_service is None:
            return Response("Service unavailable", status_code=503)
        month_name = date(year, month, 1).strftime("%B")
        ensured = await user_entry_service.ensure_periodic_note(
            user_uid, "monthly", f"{year}-{month:02d}", f"Monthly Note: {month_name} {year}"
        )
        if ensured.is_error:
            return Response("Error loading note", status_code=500)
        return RedirectResponse(f"/journals/{ensured.value}", status_code=302)

    @rt("/journals/{entry_uid}/note", methods=["POST"])
    @csrf_protected
    async def journal_save_note(request: Request, entry_uid: str) -> Any:
        """Save edited periodic-note content. Returns the #note-save-status fragment."""
        from fasthtml.common import P as _P

        from core.models.user_entry.user_entry_request import UserEntryUpdateRequest

        user_uid = require_authenticated_user(request)
        if user_entry_service is None:
            return _P(
                "Service unavailable", id="note-save-status", cls="text-[13px] text-destructive"
            )
        # Guard: only allow saves on owned periodic notes (daily/weekly/monthly).
        # Prevents mutation of unrelated entries (e.g. TEACHER_REVIEW submissions)
        # via this route.
        entry_result = await user_entry_service.get_entry(entry_uid, user_uid)
        if entry_result.is_error or entry_result.value is None:
            return _P("Note not found", id="note-save-status", cls="text-[13px] text-destructive")
        if not user_entry_service.is_periodic_note(entry_result.value):
            return _P(
                "Not a periodic note", id="note-save-status", cls="text-[13px] text-destructive"
            )
        form = await request.form()
        content = str(form.get("content", ""))
        result = await user_entry_service.update_entry(
            uid=entry_uid,
            user_uid=user_uid,
            request=UserEntryUpdateRequest(content=content),
        )
        if result.is_error:
            logger.error("Periodic note save failed for %s: %s", entry_uid, result.expect_error())
            return _P("Could not save", id="note-save-status", cls="text-[13px] text-destructive")
        return _P("Saved ✓", id="note-save-status", cls="text-[13px] text-green-600")

    # ------------------------------------------------------------------
    # POST /journals/suggest-activities — lazy-loaded "Suggested activities" panel
    #
    # Declared before the {entry_uid} catch-all (FastHTML resolves in order).
    # Takes the reflection *content* in the POST body (zero-persistence, ADR-073),
    # runs the bridge, and returns inert copyable DSL lines. There is no stored
    # entry to read, own, or cache into — nothing is created or persisted (the
    # prose + suggestions boundary).
    # ------------------------------------------------------------------

    @rt("/journals/suggest-activities", methods=["POST"])
    @csrf_protected
    @rate_limited(per_user=20, window_s=60)
    async def journals_suggest_activities(request: Request) -> Any:
        from ui.journals import SuggestedActivitiesPanel

        user_uid = require_authenticated_user(request)

        # CORE tier (no journal_service), FULL-tier-without-OpenAI-key, or an
        # effective-CORE user (per-user AI gate — the bridge is an LLM call) →
        # inert cheat-sheet pointer. No stored entry exists, so there is no
        # ownership / allowlist invariant to protect: the content is supplied by
        # the caller.
        if journal_service is None or not journal_service.suggestions_available:
            return SuggestedActivitiesPanel(unavailable=True)
        gated_user, _gate_denial = await _load_ai_gated_user(user_uid)
        if gated_user is None:
            return SuggestedActivitiesPanel(unavailable=True)

        form = await request.form()
        content = str(form.get("content", "")).strip()
        if not content:
            return SuggestedActivitiesPanel(items=[])

        # Ground the bridge in the user's active goals (soft — a goals-query
        # failure degrades to ungrounded). Recomputed per request; the reflection
        # is inert and short-lived, so there is nothing to memoise.
        titles_result = await journal_service.active_goal_titles(user_uid)
        titles = titles_result.value if titles_result.is_ok else []

        result = await journal_service.suggest_activities(content, user_uid, titles)
        if result.is_error:
            logger.warning("suggest_activities failed for %s: %s", user_uid, result.expect_error())
            return SuggestedActivitiesPanel(error=True)

        return SuggestedActivitiesPanel(items=result.value)

    # ------------------------------------------------------------------
    # Discussion revisit / continue / delete / export / rename (ADR-078)
    #
    # Declared before the {entry_uid} catch-all. These carry ≥2 path segments,
    # so they never collide with the 1-segment periodic-note route; every op is
    # owner-scoped (a non-owner / missing session is 404, not 403).
    # ------------------------------------------------------------------

    @rt("/journals/discussion/{session_id}", methods=["GET"])
    async def journal_continue(request: Request, session_id: str) -> Any:
        """Continue an owned discussion — rehydrate the workspace from stored turns."""
        from ui.journals import DiscussionThreadFragment
        from ui.journals.chat_page import JournalsLandingPage

        user_uid = require_authenticated_user(request)
        user_result = await user_service.get_user(user_uid)
        if user_result.is_error or user_result.value is None:
            return Response("Could not load user", status_code=500)
        user = user_result.value
        is_founder = user.journal_tier.is_founder()

        session_result = await conversation_service.get_session(session_id, user_uid)
        if session_result.is_error:
            return Response("Service error", status_code=500)
        if session_result.value is None:
            return Response("Not found", status_code=404)  # 404-not-403
        session = session_result.value

        turns_result = await conversation_service.get_turns(session_id, user_uid)
        if turns_result.is_error:
            return Response("Not found", status_code=404)

        # Restore the session's last source selection (C3) — FOUNDER-gated, since
        # the composer dials are a FOUNDER entitlement.
        canon_books, canon_on, vault_on = parse_source_selection(session.source_selection)
        # LLM-switcher options + the session's restored model, so a continued
        # discussion resumes on the model it was last using (ADR-078 + switcher).
        model_options = journal_service.available_chat_models() if journal_service else []
        workspace = DiscussionThreadFragment(
            session_id=session_id,
            title=session.title,
            turns=turns_result.value,
            is_founder=is_founder,
            # Book scope is preserved even when the dial was last off, so
            # re-enabling canon restores the original books (not the whole shelf).
            canon_book_uids=tuple(canon_books),
            summon_canon=canon_on and is_founder,
            summon_vault=vault_on and is_founder,
            model=session.model,
            model_options=model_options,
        )

        sessions_result = await conversation_service.list_sessions(user_uid)
        sessions = sessions_result.value if sessions_result.is_ok else []

        # The per-book source PICKER lives on the fresh-entry form only; a
        # continued session reuses its stored book scope via the composer dials.
        page_content = JournalsLandingPage(
            user=user, shelf_books=[], sessions=sessions, workspace=workspace
        )

        if request.headers.get("HX-Request"):
            return page_content

        from ui.layouts.base_page import BasePage
        from ui.layouts.page_types import PageType

        return BasePage(
            content=page_content,
            title=session.title or "Discussion",
            page_type=PageType.CUSTOM,
            request=request,
            active_page="journals",
        )

    @rt("/journals/discussion/{session_id}/delete", methods=["POST"])
    @csrf_protected
    async def journal_discussion_delete(request: Request, session_id: str) -> Any:
        """Delete an owned discussion (session + all turns). Removes the row."""
        user_uid = require_authenticated_user(request)
        result = await conversation_service.delete_session(session_id, user_uid)
        if result.is_error:
            logger.error("Discussion delete failed for %s: %s", session_id, result.expect_error())
            return Response("Could not delete", status_code=500)
        # Empty body + hx-swap="outerHTML" removes the row. A non-owned/missing
        # session returns False (nothing deleted) — the row still vanishes for
        # this user, which is harmless since it was never theirs.
        return HTMLResponse("")

    @rt("/journals/discussion/{session_id}/export", methods=["GET"])
    async def journal_discussion_export(request: Request, session_id: str) -> Any:
        """Export an owned discussion as a markdown transcript download (ADR-078 §8)."""
        user_uid = require_authenticated_user(request)
        session_result = await conversation_service.get_session(session_id, user_uid)
        if session_result.is_error or session_result.value is None:
            return Response("Not found", status_code=404)
        session = session_result.value
        turns_result = await conversation_service.get_turns(session_id, user_uid)
        if turns_result.is_error:
            return Response("Not found", status_code=404)

        markdown = render_discussion_markdown(session.title, turns_result.value)
        filename = safe_export_filename(session.title)
        return Response(
            markdown,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @rt("/journals/discussion/{session_id}/rename", methods=["POST"])
    @csrf_protected
    async def journal_discussion_rename(request: Request, session_id: str, title: str = "") -> Any:
        """Rename an owned discussion; re-render the revisit-list row."""
        from ui.journals.chat_page import DiscussionRow

        user_uid = require_authenticated_user(request)
        new_title = title.strip()[:120] or "Untitled discussion"
        renamed = await conversation_service.rename_session(session_id, user_uid, new_title)
        if renamed.is_error or not renamed.value:
            return Response("Not found", status_code=404)  # not owned / missing
        session_result = await conversation_service.get_session(session_id, user_uid)
        if session_result.is_error or session_result.value is None:
            return Response("Not found", status_code=404)
        return DiscussionRow(session_result.value)

    # ------------------------------------------------------------------
    # GET /journals/{entry_uid} — dedicated journal session page
    # ------------------------------------------------------------------

    @rt("/journals/{entry_uid}", methods=["GET"])
    async def journal_chat(request: Request, entry_uid: str) -> Any:
        """Periodic-note page (daily / weekly / monthly).

        Journal *sessions* are zero-persistence (ADR-073) — they render inline on
        ``/journals`` and are never stored, so there is nothing to reopen here.
        This route serves only the deliberate stored feature: periodic notes.
        Any non-periodic entry_uid → 404.
        """
        from adapters.inbound.result_helpers import require_found
        from core.utils.result_simplified import ErrorCategory

        user_uid = require_authenticated_user(request)

        if user_entry_service is None:
            return Response("Service unavailable", status_code=503)

        entry_result = await user_entry_service.get_entry(entry_uid, user_uid)
        found = require_found(entry_result, "Journal entry", entry_uid)
        if found.is_error:
            err = found.expect_error()
            status = 404 if err.category == ErrorCategory.NOT_FOUND else 500
            return Response("Not found" if status == 404 else "Service error", status_code=status)
        entry = found.value

        # Only periodic notes have a stored page. Sessions (never stored) and any
        # other entry kind → 404.
        if not user_entry_service.is_periodic_note(entry):
            return Response("Not found", status_code=404)

        from ui.journals import PeriodicNoteFragment
        from ui.journals.chat_page import PeriodicNotePage
        from ui.layouts.base_page import BasePage
        from ui.layouts.page_types import PageType

        initial_workspace = PeriodicNoteFragment(
            entry_uid=entry.uid,
            title=entry.title or "",
            content=entry.content or "",
        )
        page_content = PeriodicNotePage(entry=entry, initial_workspace=initial_workspace)

        if request.headers.get("HX-Request"):
            return page_content

        return BasePage(
            content=page_content,
            title=entry.title or "Periodic Note",
            page_type=PageType.CUSTOM,
            request=request,
            active_page="calendar",
        )

    # ------------------------------------------------------------------
    # POST /journals/follow-up — conversation continuation
    # ------------------------------------------------------------------

    @rt("/journals/follow-up", methods=["POST"])
    @csrf_protected
    async def journals_follow_up(
        request: Request,
        user_reply: str,
        session_id: str = "",
        transcript_json: str = "",
        title: str = "",
        journal_mode: str = "",
        summon_canon: bool = False,
        summon_vault: bool = False,
        canon_book_uids: str = "",
        model: str = "",
    ) -> Any:
        """Continue a journal conversation.

        Two memory models, selected by ``session_id`` (ADR-078 §5):

        - **Session-backed** (``session_id`` set — a *saved* discussion): prior
          turns are read from Neo4j (owner-checked — a non-owner session is
          404-not-403), context is rebuilt from them, and the new user/assistant
          pair is appended to the store.
        - **Ephemeral structured** (no ``session_id`` — every unsaved discussion,
          both doors): context is rebuilt from the client-side ``transcript_json``
          accumulator (ordered ``{role, content}`` pairs) and the new pair is
          appended to it via an OOB swap. Nothing is persisted — this dies on
          reload until the user presses *Save this chat*.

        Returns FollowUpFragment: chat bubbles appended to #journal-thread (plus
        the OOB accumulator input on the two ephemeral paths).

        ``canon_book_uids`` is a CSV of the shelf books the discussion opened on
        (the composer carries it as a hidden field) — it keeps follow-ups scoped
        to the same books the session chose (C3).
        """
        from core.models.enums.user_enums import JournalMode
        from ui.journals import FollowUpErrorFragment, FollowUpFragment

        user_uid = require_authenticated_user(request)

        gated_user, gate_denial = await _load_ai_gated_user(user_uid)
        if gated_user is None:
            return FollowUpErrorFragment(gate_denial)

        if not user_reply or not user_reply.strip():
            return FollowUpErrorFragment("Please write something before sending.")

        if journal_service is None:
            return FollowUpErrorFragment("Journal AI features are not available (CORE tier).")

        # Both dials are FOUNDER entitlements — the composer dials are hidden
        # for other tiers, but a POST flag is forgeable, so gate them
        # server-side (Codex #572 P1). The AI gate above already loaded the
        # user, so the dials resolve off that object — still ONE lookup per
        # follow-up (pinned by test_journals_follow_up_gate.py).
        if summon_canon or summon_vault:
            is_founder = gated_user.journal_tier.is_founder()
            summon_canon = summon_canon and is_founder
            summon_vault = summon_vault and is_founder

        # Empty scope must mean "whole shelf" (None), never [] — an empty
        # resource_uids list is a guaranteed miss in retrieve(). The DNWF
        # file/audio composer carries no book scope, so its canon dial draws the
        # whole shelf; a typed discussion carries the books it opened on.
        book_uids = (
            ([u for u in canon_book_uids.split(",") if u.strip()] or None) if summon_canon else None
        )

        mode = JournalMode.from_string(journal_mode)
        reply = user_reply.strip()

        # Session-backed path: rebuild context from stored turns (owner-checked).
        if session_id:
            turns_result = await conversation_service.get_turns(session_id, user_uid)
            if turns_result.is_error:
                # 404-not-403: a missing OR not-owned session is indistinguishable.
                logger.warning(
                    "Follow-up on inaccessible session %s for %s: %s",
                    session_id,
                    user_uid,
                    turns_result.expect_error(),
                )
                return FollowUpErrorFragment("This discussion could not be found.")
            prior_entry, prior_ai = history_to_follow_up_context(turns_result.value)
            result = await journal_service.run_follow_up(
                original_entry=prior_entry,
                ai_response=prior_ai,
                user_reply=reply,
                user_uid=user_uid,
                mode=mode,
                summon_canon=summon_canon,
                summon_vault=summon_vault,
                canon_book_uids=book_uids,
                model=model or None,
            )
            if result.is_error:
                logger.error("Journal follow-up failed for %s: %s", user_uid, result.expect_error())
                return FollowUpErrorFragment("Could not generate a response. Please try again.")
            ai_text = result.value.text
            appended = await conversation_service.append_exchange(
                session_id, user_uid, reply, ai_text
            )
            if appended.is_error:
                logger.error(
                    "Could not persist follow-up turns for session %s: %s",
                    session_id,
                    appended.expect_error(),
                )
                return FollowUpErrorFragment("Could not save your message. Please try again.")
            # Persist this follow-up's source selection so a continued session
            # restores its LAST selection (C3, last-write-wins). The book *scope*
            # comes from the composer's hidden field (preserved across turns),
            # NOT the summon-gated book_uids — so an ungrounded follow-up records
            # canon_on=false WITHOUT erasing the session's books (Codex #635 P2).
            # Best-effort: a write miss must not fail the reply already shown.
            scope_books = [book for book in canon_book_uids.split(",") if book.strip()]
            selection = build_source_selection(scope_books, summon_canon, summon_vault)
            # Co-persist the per-conversation model (last-write-wins) so a mid-thread
            # switch on a saved discussion survives a later *continue* — model=None
            # (no picker sent) leaves the stored model unchanged.
            await conversation_service.update_source_selection(
                session_id, user_uid, selection, model=model or None
            )
            # transcript_json omitted → session-backed fragment (no OOB accumulator).
            return FollowUpFragment(
                user_reply=reply,
                ai_text=ai_text,
                title=title.strip(),
                mode=mode,
                sources=result.value.sources,
            )

        # Ephemeral structured path (every unsaved discussion, both doors): context
        # + memory live in the client-side transcript_json accumulator. Nothing is
        # persisted (ADR-078 §5) — the appended pair rides an OOB swap, gone on
        # reload until the user presses *Save this chat*.
        from core.models.conversation import ROLE_ASSISTANT, ROLE_USER

        items = parse_transcript(transcript_json)
        prior_entry, prior_ai = render_follow_up_context(items)
        result = await journal_service.run_follow_up(
            original_entry=prior_entry,
            ai_response=prior_ai,
            user_reply=reply,
            user_uid=user_uid,
            mode=mode,
            summon_canon=summon_canon,
            summon_vault=summon_vault,
            canon_book_uids=book_uids,
            model=model or None,
        )
        if result.is_error:
            logger.error("Journal follow-up failed for %s: %s", user_uid, result.expect_error())
            return FollowUpErrorFragment("Could not generate a response. Please try again.")
        ai_text = result.value.text
        updated = serialize_transcript([*items, (ROLE_USER, reply), (ROLE_ASSISTANT, ai_text)])
        return FollowUpFragment(
            user_reply=reply,
            ai_text=ai_text,
            title=title.strip(),
            mode=mode,
            sources=result.value.sources,
            transcript_json=updated,
        )

    # ------------------------------------------------------------------
    # POST /journals/save — persist an ephemeral discussion (ADR-078 §5 opt-in)
    # ------------------------------------------------------------------

    @rt("/journals/save", methods=["POST"])
    @csrf_protected
    @rate_limited(per_user=20, window_s=60)
    async def journals_save(
        request: Request,
        transcript_json: str = "",
        title: str = "",
        summon_canon: bool = False,
        summon_vault: bool = False,
        canon_book_uids: str = "",
        model: str = "",
    ) -> Any:
        """Save this chat — the single explicit persistence gesture (ADR-078 §5).

        Promotes the current ephemeral ``transcript_json`` accumulator into an
        owner-private :ConversationSession + its turn pairs. There is no LLM call
        and no auto-save anywhere: a discussion reaches the store ONLY through
        this route (guard 7). On success the composer is swapped for its
        session-backed shape (further turns append to the saved session) and the
        newly saved discussion is prepended to the revisit list via an OOB swap.
        Un-saving is the existing per-session delete on that list.
        """
        from fasthtml.common import to_xml

        from core.models.conversation import CONVERSATION_KIND_DISCUSSION
        from core.models.enums.user_enums import JournalMode
        from ui.journals import FollowUpErrorFragment, SessionBackedComposer
        from ui.journals.chat_page import discussions_revisit_panel

        def _save_error(msg: str) -> Any:
            # Retarget the error to the thread (append) rather than let the Save
            # button's #journal-composer/outerHTML swap replace the composer — a
            # failed save must leave the textarea + transcript_json intact so the
            # user can retry or keep talking (Codex #638 P2).
            return HTMLResponse(
                to_xml(FollowUpErrorFragment(msg)),
                headers={"HX-Retarget": "#journal-thread", "HX-Reswap": "beforeend"},
            )

        user_uid = require_authenticated_user(request)

        pairs = transcript_to_pairs(parse_transcript(transcript_json))
        if not pairs:
            return _save_error("There's nothing to save yet.")

        # The composer dials are a FOUNDER entitlement; resolve the tier once (a
        # POST flag is forgeable, so gate server-side) — also used to render the
        # session-backed composer's dials.
        is_founder = await _resolve_founder(user_uid)
        summon_canon = summon_canon and is_founder
        summon_vault = summon_vault and is_founder
        # Book scope is stored independent of the dial (an ungrounded save keeps
        # the session's books), mirroring the follow-up write (#635 P2).
        scope_books = [b for b in canon_book_uids.split(",") if b.strip()]
        source_selection = build_source_selection(scope_books, summon_canon, summon_vault)

        clean_title = (
            title.strip()[:120] or pairs[0][0].split("\n")[0].strip()[:60] or "Journal Entry"
        )
        # The per-conversation model chosen for this discussion (the picker only
        # offers serveable models; empty → the app-safe default).
        chosen_model = model.strip() or DEFAULT_CHAT_MODEL

        saved = await conversation_service.save_transcript(
            user_uid,
            CONVERSATION_KIND_DISCUSSION,
            clean_title,
            source_selection,
            chosen_model,
            pairs,
        )
        if saved.is_error:
            logger.error("Could not save discussion for %s: %s", user_uid, saved.expect_error())
            return _save_error("Could not save your discussion. Please try again.")
        session = saved.value

        # Refresh the revisit list so the saved chat appears immediately (its row's
        # delete IS the un-save). Fail-soft to just the new session on a read miss.
        sessions_result = await conversation_service.list_sessions(user_uid)
        sessions = sessions_result.value if sessions_result.is_ok else [session]

        return (
            SessionBackedComposer(
                clean_title,
                JournalMode.default().value,
                session_id=session.session_id,
                is_founder=is_founder,
                canon_book_uids=tuple(scope_books),
                summon_canon=summon_canon,
                summon_vault=summon_vault,
                model=chosen_model,
                model_options=journal_service.available_chat_models() if journal_service else [],
            ),
            discussions_revisit_panel(sessions, oob=True),
        )

    # ------------------------------------------------------------------
    # POST /journals/stage1 — Scribe
    # ------------------------------------------------------------------

    @rt("/journals/stage1", methods=["POST"])
    @csrf_protected
    async def journals_stage1(
        request: Request,
        raw_entry: str,
        title: str = "",
    ) -> Any:
        from ui.journals import ErrorFragment, Stage1Fragment

        user_uid = require_authenticated_user(request)

        if not raw_entry or not raw_entry.strip():
            return ErrorFragment("Please write something before proceeding.")

        if journal_service is None:
            return ErrorFragment("Journal AI features are not available (CORE tier).")

        if not await _resolve_founder(user_uid):
            return ErrorFragment("Founder workflow is not available for your account.")

        result = await journal_service.run_stage1(raw_entry.strip(), user_uid)
        if result.is_error:
            logger.error("Stage 1 failed for %s: %s", user_uid, result.expect_error())
            return ErrorFragment("Stage 1 failed. Please try again.")

        return Stage1Fragment(
            raw_entry=raw_entry.strip(),
            title=title.strip(),
            scribe_output=result.value,
        )

    # ------------------------------------------------------------------
    # POST /journals/stage2 — Thought Partner
    # ------------------------------------------------------------------

    @rt("/journals/stage2", methods=["POST"])
    @csrf_protected
    async def journals_stage2(
        request: Request,
        raw_entry: str,
        title: str = "",
        scribe_output: str = "",
        review_notes: str = "",
        summon_canon: bool = False,
        summon_vault: bool = False,
    ) -> Any:
        from ui.journals import ErrorFragment, Stage2Fragment

        user_uid = require_authenticated_user(request)

        if journal_service is None:
            return ErrorFragment("Journal AI features are not available (CORE tier).")

        if not await _resolve_founder(user_uid):
            return ErrorFragment("Founder workflow is not available for your account.")

        result = await journal_service.run_stage2(
            raw_entry=raw_entry,
            scribe_output=scribe_output,
            review_notes=review_notes,
            user_uid=user_uid,
            summon_canon=summon_canon,
            summon_vault=summon_vault,
        )
        if result.is_error:
            logger.error("Stage 2 failed for %s: %s", user_uid, result.expect_error())
            return ErrorFragment("Stage 2 failed. Please try again.")

        return Stage2Fragment(
            raw_entry=raw_entry,
            title=title,
            scribe_output=scribe_output,
            thought_partner_output=result.value,
        )

    # ------------------------------------------------------------------
    # POST /journals/stage3 — What Is Related
    # ------------------------------------------------------------------

    @rt("/journals/stage3", methods=["POST"])
    @csrf_protected
    async def journals_stage3(
        request: Request,
        raw_entry: str,
        title: str = "",
        scribe_output: str = "",
        thought_partner_output: str = "",
        review_notes: str = "",
        summon_canon: bool = False,
        summon_vault: bool = False,
    ) -> Any:
        from ui.journals import ErrorFragment, Stage3Fragment

        user_uid = require_authenticated_user(request)

        if journal_service is None:
            return ErrorFragment("Journal AI features are not available (CORE tier).")

        if not await _resolve_founder(user_uid):
            return ErrorFragment("Founder workflow is not available for your account.")

        result = await journal_service.run_stage3(
            raw_entry=raw_entry,
            thought_partner_output=thought_partner_output,
            review_notes=review_notes,
            user_uid=user_uid,
            summon_canon=summon_canon,
            summon_vault=summon_vault,
        )
        if result.is_error:
            logger.error("Stage 3 failed for %s: %s", user_uid, result.expect_error())
            return ErrorFragment("Stage 3 failed. Please try again.")

        # Ephemeral composer opens on the source→output pair (the original entry
        # as the user turn, the Stage 3 output as the assistant turn) + Save; the
        # run's grounding rides the dials so a Save records it (ADR-078 P3).
        from core.models.conversation import ROLE_ASSISTANT, ROLE_USER

        transcript_json = serialize_transcript(
            [(ROLE_USER, raw_entry), (ROLE_ASSISTANT, result.value)]
        )
        return Stage3Fragment(
            raw_entry=raw_entry,
            title=title,
            related_output=result.value,
            is_founder=True,  # route is FOUNDER-gated above
            transcript_json=transcript_json,
            summon_canon=summon_canon,
            summon_vault=summon_vault,
        )
