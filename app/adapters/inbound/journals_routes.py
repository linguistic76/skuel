"""Journals domain routes — DNWF three-stage workflow (FOUNDER) and continuous (STANDARD).

Routes:
    GET  /journals                  — tier-aware landing page (Tasks+ sidebar)
    POST /journals/upload           — file upload handler
    POST /journals/folder-process   — batch folder processing
    GET  /journals/browse           — journal history
    POST /journals/respond          — STANDARD tier single-response workflow (FULL tier)
    POST /journals/stage1           — Stage 1 Scribe (FOUNDER only, FULL tier)
    POST /journals/stage2           — Stage 2 Thought Partner (FOUNDER only, FULL tier)
    POST /journals/stage3           — Stage 3 What Is Related (FOUNDER only, FULL tier)
    POST /journals/save             — persist journal entry as UserEntry(pipeline=JOURNAL)
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fasthtml.common import A, Div, Span, Strong
from monsterui.franken import ButtonT, CardBody, CardHeader, CardTitle, UkIcon
from monsterui.franken import CardContainer as Card
from starlette.responses import HTMLResponse, Response

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.rate_limit import rate_limited
from core.models.enums.entity_enums import EntityStatus
from core.models.enums.pipeline import Pipeline
from core.models.user_entry.user_entry import UserEntry
from core.utils.logging import get_logger
from ui.feedback import StatusBadge
from ui.journals.components import render_batch_upload_status
from ui.journals.components import render_upload_status as render_journal_upload_status
from ui.patterns.card_generator import CardGenerator
from ui.patterns.empty_state import EmptyState
from ui.patterns.page_header import PageHeader
from ui.primitives import ButtonLink

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from services_bootstrap._container import Services


logger = get_logger("skuel.routes.journals")

_JOURNAL_INSTRUCTIONS_DIR = Path(__file__).parents[2] / "data" / "instructions"
_JE_IN = Path("/home/mike/0bsidian/skuel/je_in")
_JE_OUT = Path("/home/mike/0bsidian/skuel/je_out")
_TEXT_EXTENSIONS = {".txt", ".md", ".rst"}
_LLM_MODEL_CLAUDE = "claude-sonnet-4-6"
_LLM_MODEL_GPT = "gpt-4o-mini"
_LLM_MAX_TOKENS = 4000


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_journal_instruction_file(filename: str, processing_mode: str) -> str | None:
    """Read an instruction file from data/instructions/ with path-containment guard."""
    if processing_mode == "transcribe_only" or not filename:
        return None
    candidate = (_JOURNAL_INSTRUCTIONS_DIR / filename).resolve()
    try:
        candidate.relative_to(_JOURNAL_INSTRUCTIONS_DIR.resolve())
    except ValueError:
        logger.warning(f"Path traversal attempt blocked: {filename!r}")
        return None
    if not candidate.is_file():
        logger.warning(f"Instruction file not found: {candidate}")
        return None
    return candidate.read_text(encoding="utf-8")


async def _submit_text_file_for_llm(
    *,
    file_content: bytes,
    filename: str,
    title: str,
    user_uid: str,
    instructions: str | None,
    user_entry_service: Any,
) -> Any:
    """Submit a text file for LLM_SUMMARY by decoding content and using create_entry."""
    from core.models.user_entry.user_entry_request import UserEntryCreateRequest
    from core.utils.result_simplified import Errors, Result

    try:
        text_content = file_content.decode("utf-8")
    except UnicodeDecodeError:
        return Result.fail(
            Errors.validation(
                "File must be valid UTF-8 text for Instructions only mode",
                field="file",
            )
        )

    file_type = mimetypes.guess_type(filename)[0] or "text/plain"
    req = UserEntryCreateRequest(
        title=title,
        pipeline=Pipeline.LLM_SUMMARY,
        instructions=instructions,
        content=text_content,
        original_filename=filename,
        file_size=len(file_content),
        file_type=file_type,
    )
    return await user_entry_service.create_entry(request=req, user_uid=user_uid)


async def _call_llm_with_instructions(
    text: str,
    instructions: str | None,
    processing_service: Any,
) -> Any:
    """Call LLM directly on raw text for folder processing (no database records)."""
    from core.utils.result_simplified import Errors, Result

    llm_caller = getattr(processing_service, "llm_caller", None)
    if llm_caller is None:
        return Result.fail(
            Errors.business(
                rule="llm_tier_required",
                message="LLM processing requires INTELLIGENCE_TIER=full",
            )
        )
    model = (
        _LLM_MODEL_CLAUDE
        if llm_caller.is_model_supported(_LLM_MODEL_CLAUDE)
        else _LLM_MODEL_GPT
    )
    prompt = f"{instructions}\n\n---\n\n{text}" if instructions else text
    try:
        return await llm_caller.generate(
            prompt=prompt, model=model, max_tokens=_LLM_MAX_TOKENS
        )
    except Exception as e:  # safety-net: LLM call errors in folder-batch context
        return Result.fail(Errors.integration(service="llm", message=f"LLM failed: {e}"))


def _status_value(entry: UserEntry) -> str:
    status = entry.status
    if isinstance(status, EntityStatus):
        return status.value
    return str(status) if status else "submitted"


def _render_user_entry_journal_card(entry: UserEntry) -> Any:
    file_size = entry.file_size or 0
    file_size_mb = file_size / 1024 / 1024 if file_size else 0

    meta_parts: list[str] = []
    if entry.original_filename:
        meta_parts.append(entry.original_filename)
    if file_size_mb > 0:
        meta_parts.append(f"{file_size_mb:.2f} MB")
    if entry.file_type:
        meta_parts.append(entry.file_type)

    status_str = _status_value(entry)

    action_buttons: list[Any] = []
    if entry.status == EntityStatus.COMPLETED:
        action_buttons.append(
            ButtonLink(
                "Download",
                href=f"/submit/journals/{entry.uid}/download",
                cls=(ButtonT.primary, ButtonT.sm),
            )
        )

    return CardGenerator.from_dataclass(
        {"title": entry.title or "Untitled"},
        display_fields=[],
        header_badges=[StatusBadge(status_str) if status_str else None],
        show_labels=False,
        metadata=[" • ".join(meta_parts)] if meta_parts else None,
        actions=Div(*action_buttons, cls="flex gap-2") if action_buttons else None,
        card_attrs={"cls": "mb-2"},
    )


def _render_user_entry_journal_grid(entries: list[UserEntry]) -> Any:
    if not entries:
        return Div(EmptyState(title="No journals found"), id="journals-grid-container")
    return Div(
        *[_render_user_entry_journal_card(e) for e in entries],
        id="journals-grid-container",
    )


def _render_awaiting_response_section(entries: list[UserEntry]) -> Any:
    if not entries:
        return Div()
    return Card(
        CardHeader(CardTitle("Awaiting a response")),
        CardBody(
            *[
                Div(
                    Span(e.title or "Untitled entry", cls="font-medium text-sm"),
                    ButtonLink(
                        "Open",
                        href=f"/gradebook/{e.uid}",
                        cls=(ButtonT.ghost, ButtonT.sm),
                    ),
                    cls="flex items-center justify-between p-2 border-b border-border",
                )
                for e in entries
            ]
        ),
        cls="mb-6 bg-background shadow-sm",
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
    journal_service = services.journal  # None when INTELLIGENCE_TIER=core
    user_entry_service = services.user_entry
    orchestrator = services.user_entry_orchestrator
    batch_transcription_service = services.batch_transcription
    processing_service = services.user_entry_processor

    # ------------------------------------------------------------------
    # GET /journals — landing page
    # ------------------------------------------------------------------

    @rt("/journals", methods=["GET"])
    async def journals_page(request: Request) -> Any:
        user_uid = require_authenticated_user(request)

        from ui.activities.nav import render_activity_sidebar_page
        from ui.journals import JournalsPage

        user_result = await user_service.get_user(user_uid)
        if user_result.is_error or user_result.value is None:
            return Response("Could not load user", status_code=500)

        workspace = JournalsPage(user_result.value)

        if request.headers.get("HX-Request"):
            return workspace

        # PLANNED: /journals/about — privacy details + workflow guide
        browse_link = A(
            UkIcon("library", cls="w-[19px] h-[19px] text-muted-foreground"),
            Span(
                Strong("Browse", cls="font-bold text-foreground"),
                Span(" my journals", cls="font-normal text-muted-foreground"),
            ),
            href="/journals/browse",
            cls=(
                "text-[18px] text-foreground hover:text-brand inline-flex items-center gap-2 "
                "transition-colors"
            ),
        )
        page_content = Div(
            Div(browse_link, cls="flex justify-end mb-4 px-2"),
            workspace,
        )
        return await render_activity_sidebar_page(
            content=page_content,
            active="journals",
            request=request,
            title="Journal",
        )

    # ------------------------------------------------------------------
    # POST /journals/upload — file upload handler
    # ------------------------------------------------------------------

    @rt("/journals/upload", methods=["POST"])
    @csrf_protected
    @rate_limited(per_user=10, window_s=60)
    async def journals_upload(request: Request) -> Any:
        """HTMX endpoint for journal file upload.

        Supports three processing modes driven by the ``processing_mode`` form field:
        - ``transcribe_only``           — audio → text (Pipeline.TRANSCRIBE)
        - ``transcribe_and_instructions`` — audio → transcribe + LLM (Pipeline.TRANSCRIBE_AND_STRUCTURE)
        - ``instructions_only``         — text file → LLM (Pipeline.LLM_SUMMARY)

        For FOUNDER tier with transcribe modes, runs transcription synchronously and
        returns ``TranscriptReviewFragment`` so the user can review before Stage 1.
        """
        from starlette.datastructures import UploadFile

        if user_entry_service is None:
            return render_journal_upload_status(
                "error", "Upload service not available", is_error=True
            )

        try:
            user_uid = require_authenticated_user(request)
            form = await request.form()
            raw_title = form.get("title")
            custom_title = str(raw_title).strip() if raw_title else ""

            upload_source = str(form.get("upload_source", "file"))
            status_id = "folder-upload-status" if upload_source == "folder" else "upload-status"

            raw_files = form.getlist("file")
            uploaded_files = [f for f in raw_files if isinstance(f, UploadFile)]

            if not uploaded_files:
                return render_journal_upload_status("error", "No file provided", is_error=True)

            max_journal_files = 20
            if len(uploaded_files) > max_journal_files:
                return render_journal_upload_status(
                    "error",
                    f"Too many files: {len(uploaded_files)} (max {max_journal_files})",
                    is_error=True,
                )

            processing_mode = str(form.get("processing_mode", "transcribe_only")).strip()
            instruction_filename = str(form.get("instruction_filename", "")).strip()
            instruction_content = str(form.get("instruction_content", "")).strip()
            instructions = instruction_content or _load_journal_instruction_file(
                instruction_filename, processing_mode
            )

            pipeline_map: dict[str, Pipeline] = {
                "transcribe_only": Pipeline.TRANSCRIBE,
                "transcribe_and_instructions": Pipeline.TRANSCRIBE_AND_STRUCTURE,
                "instructions_only": Pipeline.LLM_SUMMARY,
            }
            pipeline = pipeline_map.get(processing_mode, Pipeline.TRANSCRIBE)

            if len(uploaded_files) == 1:
                uploaded_file = uploaded_files[0]
                file_content = await uploaded_file.read()
                filename = uploaded_file.filename or "unknown"
                title = custom_title or filename

                if processing_mode == "instructions_only":
                    result = await _submit_text_file_for_llm(
                        file_content=file_content,
                        filename=filename,
                        title=title,
                        user_uid=user_uid,
                        instructions=instructions,
                        user_entry_service=user_entry_service,
                    )
                    if result.is_error:
                        return render_journal_upload_status(
                            "error", str(result.error), is_error=True
                        )
                    entry, _outcome = result.value

                    # Run all three DNWF stages in sequence (FOUNDER only) and display
                    # compiled output. STANDARD users fall through to the status card.
                    if journal_service is not None:
                        user_result = await user_service.get_user(user_uid)
                        is_founder = (
                            user_result.is_ok
                            and user_result.value is not None
                            and user_result.value.journal_tier.is_founder()
                        )
                        if not is_founder:
                            return render_journal_upload_status(
                                _status_value(entry),
                                f"Journal entry created: {entry.title}",
                                je_input_uid=entry.uid,
                            )

                        try:
                            text_content = file_content.decode("utf-8")
                        except UnicodeDecodeError:
                            text_content = ""

                        if text_content:
                            compiled_result = await journal_service.run_compiled(
                                text_content, user_uid
                            )
                            if not compiled_result.is_error:
                                from fasthtml.common import to_xml

                                from ui.journals import StandardResponseFragment

                                fragment = StandardResponseFragment(
                                    raw_entry=text_content,
                                    title=title,
                                    response_output=compiled_result.value,
                                    mode=None,
                                    already_saved=True,
                                )
                                return HTMLResponse(
                                    content=to_xml(fragment),
                                    headers={
                                        "HX-Retarget": "#journal-workspace",
                                        "HX-Reswap": "outerHTML",
                                    },
                                )
                            logger.error(
                                "Compiled DNWF failed for %s: %s",
                                entry.uid,
                                compiled_result.expect_error(),
                            )

                    return render_journal_upload_status(
                        _status_value(entry),
                        f"Journal entry created: {entry.title}",
                        je_input_uid=entry.uid,
                    )

                # Transcription modes — submit file
                result = await user_entry_service.submit_file(
                    file_content=file_content,
                    original_filename=filename,
                    user_uid=user_uid,
                    pipeline=pipeline,
                    title=title,
                    instructions=instructions,
                    metadata={"custom_title": custom_title} if custom_title else None,
                )

                if result.is_error:
                    return render_journal_upload_status("error", str(result.error), is_error=True)

                entry, _outcome = result.value

                # FOUNDER tier: run transcription synchronously → TranscriptReviewFragment
                is_transcription_mode = processing_mode in (
                    "transcribe_only",
                    "transcribe_and_instructions",
                )
                if is_transcription_mode and processing_service is not None:
                    user_result = await user_service.get_user(user_uid)
                    is_founder = (
                        user_result.is_ok
                        and user_result.value is not None
                        and user_result.value.journal_tier.is_founder()
                    )
                    if is_founder:
                        from fasthtml.common import to_xml

                        from ui.journals import TranscriptReviewFragment

                        process_result = await processing_service.process(entry)
                        if process_result.is_error:
                            logger.error(
                                "Transcription failed for %s: %s",
                                entry.uid,
                                process_result.expect_error(),
                            )
                            return render_journal_upload_status(
                                "error",
                                "Transcription failed — please try again.",
                                is_error=True,
                            )
                        transcript = (
                            process_result.value.processed_content or ""
                            if process_result.value is not None
                            else ""
                        )

                        fragment = TranscriptReviewFragment(
                            transcript=transcript,
                            title=title,
                        )
                        return HTMLResponse(
                            content=to_xml(fragment),
                            headers={
                                "HX-Retarget": "#journal-workspace",
                                "HX-Reswap": "outerHTML",
                            },
                        )

                return render_journal_upload_status(
                    _status_value(entry),
                    f"Journal entry created: {entry.title}",
                    je_input_uid=entry.uid,
                )

            # Multiple files — batch processing
            if processing_mode == "instructions_only":
                return render_journal_upload_status(
                    "error",
                    "Instructions only mode supports a single file at a time",
                    is_error=True,
                )

            batch_results: list[tuple[str, bool, str | None, str | None]] = []
            for uploaded_file in uploaded_files:
                filename = uploaded_file.filename or "unknown"
                try:
                    file_content = await uploaded_file.read()
                    result = await user_entry_service.submit_file(
                        file_content=file_content,
                        original_filename=filename,
                        user_uid=user_uid,
                        pipeline=pipeline,
                        title=filename,
                        instructions=instructions,
                        metadata=None,
                    )
                    if result.is_error:
                        batch_results.append((filename, False, None, str(result.error)))
                    else:
                        entry, _outcome = result.value
                        batch_results.append((filename, True, entry.uid, None))
                except Exception as e:  # safety-net: per-file error boundary
                    logger.error(f"Error processing journal file {filename!r}: {e}", exc_info=True)
                    batch_results.append((filename, False, None, str(e)))

            return render_batch_upload_status(batch_results, status_id=status_id)

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
        """HTMX endpoint: process all files in je_in/ with the selected pipeline."""
        try:
            require_authenticated_user(request)
            form = await request.form()
            processing_mode = str(form.get("processing_mode", "transcribe_only")).strip()
            instruction_filename = str(form.get("instruction_filename", "")).strip()
            instruction_content = str(form.get("instruction_content", "")).strip()
            instructions = instruction_content or _load_journal_instruction_file(
                instruction_filename, processing_mode
            )

            _JE_OUT.mkdir(parents=True, exist_ok=True)

            if processing_mode == "transcribe_only":
                if batch_transcription_service is None:
                    return render_journal_upload_status(
                        "error",
                        "Transcription service not available (requires FULL tier)",
                        is_error=True,
                    )
                result = await batch_transcription_service.transcribe_batch(_JE_IN, _JE_OUT)
                if result.is_error:
                    return render_journal_upload_status("error", str(result.error), is_error=True)
                r = result.value
                msg = (
                    f"{r.succeeded} transcribed, {r.failed} failed, {r.skipped} skipped"
                    f" — results in je_out/"
                )
                is_err = r.failed > 0 and r.succeeded == 0
                return render_journal_upload_status(
                    "error" if is_err else "completed", msg, is_error=is_err
                )

            if processing_mode == "transcribe_and_instructions":
                if batch_transcription_service is None:
                    return render_journal_upload_status(
                        "error",
                        "Transcription service not available (requires FULL tier)",
                        is_error=True,
                    )
                if (
                    processing_service is None
                    or getattr(processing_service, "llm_caller", None) is None
                ):
                    return render_journal_upload_status(
                        "error",
                        "LLM service not available (requires INTELLIGENCE_TIER=full)",
                        is_error=True,
                    )
                transcribe_result = await batch_transcription_service.transcribe_batch(
                    _JE_IN, _JE_OUT
                )
                if transcribe_result.is_error:
                    return render_journal_upload_status(
                        "error", str(transcribe_result.error), is_error=True
                    )
                succeeded_stems = {
                    Path(r["name"]).stem
                    for r in transcribe_result.value.results
                    if r.get("status") == "success"
                }
                llm_ok = 0
                llm_fail = 0
                for stem in succeeded_stems:
                    txt_path = _JE_OUT / f"{stem}.txt"
                    if not txt_path.exists():
                        continue
                    text = txt_path.read_text(encoding="utf-8")
                    llm_result = await _call_llm_with_instructions(
                        text, instructions, processing_service
                    )
                    if llm_result.is_error:
                        logger.error(f"LLM failed for {stem}: {llm_result.error}")
                        llm_fail += 1
                    else:
                        (_JE_OUT / f"{stem}.md").write_text(llm_result.value, encoding="utf-8")
                        llm_ok += 1
                r = transcribe_result.value
                msg = (
                    f"{r.succeeded} transcribed, {llm_ok} structured, "
                    f"{r.failed + llm_fail} failed — results in je_out/"
                )
                return render_journal_upload_status("completed", msg)

            if processing_mode == "instructions_only":
                if (
                    processing_service is None
                    or getattr(processing_service, "llm_caller", None) is None
                ):
                    return render_journal_upload_status(
                        "error",
                        "LLM service not available (requires INTELLIGENCE_TIER=full)",
                        is_error=True,
                    )
                if not _JE_IN.is_dir():
                    return render_journal_upload_status(
                        "error", f"Input folder not found: {_JE_IN}", is_error=True
                    )
                text_files = sorted(
                    f
                    for f in _JE_IN.iterdir()
                    if f.is_file() and f.suffix.lower() in _TEXT_EXTENSIONS
                )
                if not text_files:
                    return render_journal_upload_status(
                        "error", "No text files found in je_in/", is_error=True
                    )
                ok = 0
                fail = 0
                for text_file in text_files:
                    try:
                        text = text_file.read_text(encoding="utf-8")
                    except Exception:  # safety-net: per-file read error
                        fail += 1
                        continue
                    llm_result = await _call_llm_with_instructions(
                        text, instructions, processing_service
                    )
                    if llm_result.is_error:
                        logger.error(f"LLM failed for {text_file.name}: {llm_result.error}")
                        fail += 1
                    else:
                        (_JE_OUT / f"{text_file.stem}.md").write_text(
                            llm_result.value, encoding="utf-8"
                        )
                        ok += 1
                msg = f"{ok} processed, {fail} failed — results in je_out/"
                return render_journal_upload_status(
                    "completed" if ok > 0 else "error", msg, is_error=(ok == 0)
                )

            return render_journal_upload_status(
                "error", f"Unknown processing mode: {processing_mode!r}", is_error=True
            )

        except Exception as e:  # safety-net: HTMX fragment error boundary
            logger.error(f"Error in folder-process: {e}", exc_info=True)
            return render_journal_upload_status("error", f"Processing failed: {e}", is_error=True)

    # ------------------------------------------------------------------
    # GET /journals/browse — journal history
    # ------------------------------------------------------------------

    @rt("/journals/browse", methods=["GET"])
    async def journals_browse(request: Request) -> Any:
        """Browse the user's journal entries."""
        if orchestrator is None:
            return Response("Journal browse not available", status_code=503)

        user_uid = require_authenticated_user(request)

        from ui.activities.nav import render_activity_sidebar_page

        entries: list[UserEntry] = []
        result = await orchestrator.list_journal_entries(user_uid)
        if not result.is_error and result.value:
            entries = list(result.value)

        awaiting_result = await orchestrator.get_entries_awaiting_response(user_uid)
        awaiting_uids = set(awaiting_result.value or []) if awaiting_result.is_ok else set()
        awaiting_entries: list[UserEntry] = []
        if awaiting_uids:
            pool_result = await orchestrator.list_for_user(user_uid, limit=100)
            pool = list(pool_result.value) if pool_result.is_ok and pool_result.value else entries
            awaiting_entries = [e for e in pool if e.uid in awaiting_uids]

        content = Div(
            PageHeader(
                "My Journals",
                subtitle="Browse your AI-processed journal entries",
                actions=ButtonLink(
                    "New Journal",
                    href="/journals",
                    cls=(ButtonT.primary, ButtonT.sm),
                ),
            ),
            _render_awaiting_response_section(awaiting_entries),
            _render_user_entry_journal_grid(entries),
        )
        return await render_activity_sidebar_page(
            content=content,
            active="journals",
            request=request,
            title="My Journals",
        )

    # ------------------------------------------------------------------
    # POST /journals/respond — STANDARD tier single-response workflow
    # ------------------------------------------------------------------

    @rt("/journals/respond", methods=["POST"])
    @csrf_protected
    async def journals_respond(
        request: Request,
        raw_entry: str,
        title: str = "",
        journal_mode: str = "",
    ) -> Any:
        from core.models.enums.user_enums import JournalMode
        from ui.journals import ErrorFragment, StandardResponseFragment

        user_uid = require_authenticated_user(request)

        if not raw_entry or not raw_entry.strip():
            return ErrorFragment("Please write something before getting a response.")

        if journal_service is None:
            return ErrorFragment("Journal AI features are not available (CORE tier).")

        mode = JournalMode.from_string(journal_mode)
        result = await journal_service.run_standard(raw_entry.strip(), user_uid, mode)
        if result.is_error:
            logger.error("Journal respond failed for %s: %s", user_uid, result.expect_error())
            return ErrorFragment("Could not generate a response. Please try again.")

        return StandardResponseFragment(
            raw_entry=raw_entry.strip(),
            title=title.strip(),
            response_output=result.value,
            mode=mode,
        )

    # ------------------------------------------------------------------
    # POST /journals/follow-up — conversation continuation
    # ------------------------------------------------------------------

    @rt("/journals/follow-up", methods=["POST"])
    @csrf_protected
    async def journals_follow_up(
        request: Request,
        original_entry: str,
        ai_response: str,
        user_reply: str,
        title: str = "",
        journal_mode: str = "",
    ) -> Any:
        """Continue a journal conversation.

        Builds combined context from the previous exchange and calls
        run_standard() so the model responds to the follow-up, not the
        original note alone.
        """
        from core.models.enums.user_enums import JournalMode
        from ui.journals import ErrorFragment, StandardResponseFragment

        user_uid = require_authenticated_user(request)

        if not user_reply or not user_reply.strip():
            return ErrorFragment("Please write something before sending.")

        if journal_service is None:
            return ErrorFragment("Journal AI features are not available (CORE tier).")

        mode = JournalMode.from_string(journal_mode)
        result = await journal_service.run_follow_up(
            original_entry=original_entry.strip(),
            ai_response=ai_response.strip(),
            user_reply=user_reply.strip(),
            user_uid=user_uid,
            mode=mode,
        )
        if result.is_error:
            logger.error(
                "Journal follow-up failed for %s: %s", user_uid, result.expect_error()
            )
            return ErrorFragment("Could not generate a response. Please try again.")

        # Pass the combined context so further follow-ups have the full conversation.
        combined = (
            f"{original_entry.strip()}"
            f"\n\n---\n\n# Response\n\n{ai_response.strip()}"
            f"\n\n---\n\n# Follow-up\n\n{user_reply.strip()}"
        )
        return StandardResponseFragment(
            raw_entry=combined,
            title=title.strip(),
            response_output=result.value,
            mode=mode,
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

        user_result = await user_service.get_user(user_uid)
        if user_result.is_error or user_result.value is None:
            return ErrorFragment("Could not load your profile.")
        if not user_result.value.journal_tier.is_founder():
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
    ) -> Any:
        from ui.journals import ErrorFragment, Stage2Fragment

        user_uid = require_authenticated_user(request)

        if journal_service is None:
            return ErrorFragment("Journal AI features are not available (CORE tier).")

        user_result = await user_service.get_user(user_uid)
        if user_result.is_error or user_result.value is None:
            return ErrorFragment("Could not load your profile.")
        if not user_result.value.journal_tier.is_founder():
            return ErrorFragment("Founder workflow is not available for your account.")

        result = await journal_service.run_stage2(
            raw_entry=raw_entry,
            scribe_output=scribe_output,
            review_notes=review_notes,
            user_uid=user_uid,
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
    ) -> Any:
        from ui.journals import ErrorFragment, Stage3Fragment

        user_uid = require_authenticated_user(request)

        if journal_service is None:
            return ErrorFragment("Journal AI features are not available (CORE tier).")

        user_result = await user_service.get_user(user_uid)
        if user_result.is_error or user_result.value is None:
            return ErrorFragment("Could not load your profile.")
        if not user_result.value.journal_tier.is_founder():
            return ErrorFragment("Founder workflow is not available for your account.")

        result = await journal_service.run_stage3(
            raw_entry=raw_entry,
            thought_partner_output=thought_partner_output,
            review_notes=review_notes,
            user_uid=user_uid,
        )
        if result.is_error:
            logger.error("Stage 3 failed for %s: %s", user_uid, result.expect_error())
            return ErrorFragment("Stage 3 failed. Please try again.")

        return Stage3Fragment(
            raw_entry=raw_entry,
            title=title,
            related_output=result.value,
        )

    # ------------------------------------------------------------------
    # POST /journals/save — persist entry
    # ------------------------------------------------------------------

    @rt("/journals/save", methods=["POST"])
    @csrf_protected
    async def journals_save(
        request: Request,
        raw_entry: str,
        title: str = "",
    ) -> Any:
        from ui.journals import ErrorFragment, SavedFragment

        user_uid = require_authenticated_user(request)

        if not raw_entry or not raw_entry.strip():
            return ErrorFragment("Cannot save an empty entry.")

        if journal_service is None:
            return ErrorFragment("Journal save is not available (CORE tier).")

        result = await journal_service.save_entry(
            title=title.strip(),
            raw_entry=raw_entry.strip(),
            user_uid=user_uid,
        )
        if result.is_error:
            logger.error("Journal save failed for %s: %s", user_uid, result.expect_error())
            return ErrorFragment("Could not save your journal entry.")

        return SavedFragment(entry_uid=result.value)
