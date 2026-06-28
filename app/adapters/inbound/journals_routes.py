"""Journals domain routes — DNWF three-stage workflow (FOUNDER) and continuous (STANDARD).

Routes:
    GET  /journals                      — 3-column landing page (no Tasks+ sidebar)
    POST /journals/start                — create persistent session from text; redirects to chat
    POST /journals/upload               — file upload handler
    POST /journals/folder-process       — batch folder processing
    GET  /journals/je-out/{filename}    — download a compiled journal output from je_out/
    GET  /journals/{entry_uid}          — dedicated journal session chat page
    POST /journals/respond              — STANDARD tier single-response workflow (FULL tier)
    POST /journals/follow-up            — conversation continuation (all tiers)
    POST /journals/stage1               — Stage 1 Scribe (FOUNDER only, FULL tier)
    POST /journals/stage2               — Stage 2 Thought Partner (FOUNDER only, FULL tier)
    POST /journals/stage3               — Stage 3 What Is Related (FOUNDER only, FULL tier)
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import TYPE_CHECKING, Any

from datetime import date

from starlette.responses import HTMLResponse, RedirectResponse, Response

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.rate_limit import rate_limited
from core.models.enums.entity_enums import EntityStatus
from core.models.enums.pipeline import Pipeline
from core.models.user_entry.user_entry import UserEntry
from core.utils.logging import get_logger
from ui.journals.components import render_batch_upload_status
from ui.journals.components import render_upload_status as render_journal_upload_status

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from services_bootstrap._container import Services


logger = get_logger("skuel.routes.journals")

_JOURNAL_INSTRUCTIONS_DIR = Path(__file__).parents[2] / "data" / "instructions"
_JE_IN = Path("/home/mike/0bsidian/skuel/je_in")
# je_out is a pipeline staging area — excluded from vault sync (_VAULT_EXCLUDED_DIRS in
# vault_reconciler.py). Users open je_out files in Obsidian and manually decide what
# enters their personal vault. SKUEL never auto-syncs je_out content into the vault.
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
        _LLM_MODEL_CLAUDE if llm_caller.is_model_supported(_LLM_MODEL_CLAUDE) else _LLM_MODEL_GPT
    )
    prompt = f"{instructions}\n\n---\n\n{text}" if instructions else text
    try:
        return await llm_caller.generate(prompt=prompt, model=model, max_tokens=_LLM_MAX_TOKENS)
    except Exception as e:  # safety-net: LLM call errors in folder-batch context
        return Result.fail(Errors.integration(service="llm", message=f"LLM failed: {e}"))


def _status_value(entry: UserEntry) -> str:
    status = entry.status
    if isinstance(status, EntityStatus):
        return status.value
    return str(status) if status else "submitted"


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
    batch_transcription_service = services.batch_transcription
    processing_service = services.user_entry_processor

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

        _journal_pipelines = {
            Pipeline.LLM_SUMMARY,
            Pipeline.TRANSCRIBE,
            Pipeline.TRANSCRIBE_AND_STRUCTURE,
        }
        recent_entries: list[Any] = []
        if user_entry_service is not None:
            recent_result = await user_entry_service.list_for_user(user_uid, limit=60)
            recent_entries = [
                e
                for e in (recent_result.value if recent_result.is_ok else [])
                if e.pipeline in _journal_pipelines
            ][:30]

        page_content = JournalsLandingPage(user=user, recent_entries=recent_entries)

        if request.headers.get("HX-Request"):
            return page_content

        from ui.layouts.base_page import BasePage
        from ui.layouts.page_types import PageType

        return await BasePage(
            content=page_content,
            title="Journal",
            page_type=PageType.CUSTOM,
            request=request,
            active_page="journals",
        )

    # ------------------------------------------------------------------
    # POST /journals/start — create persistent session from text
    # ------------------------------------------------------------------

    @rt("/journals/start", methods=["POST"])
    @csrf_protected
    @rate_limited(per_user=10, window_s=60)
    async def journals_start(request: Request) -> Any:
        """Create a persistent journal session from direct text input.

        Both STANDARD and FOUNDER tiers use this route. STANDARD runs
        run_standard() and saves the response; FOUNDER runs run_stage1()
        and saves the scribe output (marked via metadata so the chat page
        can render Stage1Fragment with its review gate).

        On success returns HX-Redirect to /journals/{entry_uid}.
        On error returns an inline error div swapped into #start-status.
        """
        from fasthtml.common import Div as _Div
        from fasthtml.common import P as _P

        from core.models.enums.user_enums import JournalMode
        from core.models.user_entry.user_entry_request import UserEntryCreateRequest

        def _err(msg: str) -> Any:
            return _Div(
                _P(msg, cls="text-sm text-destructive"),
                id="start-status",
            )

        user_uid = require_authenticated_user(request)

        form = await request.form()
        raw_entry = str(form.get("raw_entry", "")).strip()

        if not raw_entry:
            return _err("Please write something before continuing.")

        if journal_service is None:
            return _err("Journal AI features are not available.")

        if user_entry_service is None:
            return _err("Journal service not available.")

        user_result = await user_service.get_user(user_uid)
        if user_result.is_error or user_result.value is None:
            return _err("Could not load your profile.")

        is_founder = user_result.value.journal_tier.is_founder()
        title = raw_entry.split("\n")[0][:80].strip() or "Journal Entry"

        req = UserEntryCreateRequest(
            title=title,
            pipeline=Pipeline.LLM_SUMMARY,
            content=raw_entry,
            metadata={"entry_type": "journal_stage1_start"} if is_founder else {},
        )
        create_result = await user_entry_service.create_entry(req, user_uid)
        if create_result.is_error:
            logger.error(
                "journals_start create_entry failed for %s: %s",
                user_uid,
                create_result.expect_error(),
            )
            return _err("Could not save your entry. Please try again.")

        entry, _ = create_result.value

        if is_founder:
            ai_result = await journal_service.run_stage1(raw_entry, user_uid)
        else:
            ai_result = await journal_service.run_standard(
                raw_entry, user_uid, JournalMode.default()
            )

        if ai_result.is_error:
            logger.error(
                "journals_start AI call failed for %s: %s",
                user_uid,
                ai_result.expect_error(),
            )
            return _err(
                "Could not generate a response. "
                "Your entry was saved — try again from the session list."
            )

        persist_result = await user_entry_service.update_processed_content(
            entry.uid, ai_result.value
        )
        if persist_result.is_error:
            logger.error(
                "journals_start persist failed for %s: %s",
                entry.uid,
                persist_result.expect_error(),
            )
            # Entry exists but has no processed content — chat page shows "Processing…"

        return HTMLResponse(status_code=200, headers={"HX-Redirect": f"/journals/{entry.uid}"})

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
                                # Save compiled output to je_out/{user_uid}/{stem}_out.md.
                                # User-scoped subdirectory prevents filename collisions across
                                # users and enforces ownership at the download endpoint.
                                stem = Path(filename).stem
                                # Entry UID suffix prevents collisions when the same
                                # basename is uploaded more than once.
                                output_filename = f"{stem}_{entry.uid}_out.md"
                                user_out_dir = _JE_OUT / user_uid
                                user_out_dir.mkdir(parents=True, exist_ok=True)
                                output_path = user_out_dir / output_filename
                                output_path.write_text(compiled_result.value, encoding="utf-8")
                                persist_result = await user_entry_service.update_processed_content(
                                    entry.uid,
                                    compiled_result.value,
                                    processed_file_path=str(output_path),
                                )
                                if persist_result.is_error:
                                    logger.error(
                                        "Failed to persist processed content for %s: %s",
                                        entry.uid,
                                        persist_result.expect_error(),
                                    )
                                    return render_journal_upload_status(
                                        "error",
                                        "Journal processed but could not save output — please try again.",
                                        is_error=True,
                                    )
                                return HTMLResponse(
                                    status_code=200,
                                    headers={"HX-Redirect": f"/journals/{entry.uid}"},
                                )
                            logger.error(
                                "Compiled DNWF failed for %s: %s",
                                entry.uid,
                                compiled_result.expect_error(),
                            )

                    # Fallthrough: CORE tier (no journal_service), empty file, or LLM error.
                    # Entry exists but has no processed content — show a status card so the
                    # user isn't stranded on a permanent spinner at /journals/{uid}.
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
                    metadata={"custom_title": custom_title} if custom_title else {},
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
                        return HTMLResponse(
                            status_code=200,
                            headers={"HX-Redirect": f"/journals/{entry.uid}"},
                        )

                # STANDARD tier: transcription is async — no content on the entry yet.
                # Return a status card so the user isn't stranded on a permanent spinner.
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
                        metadata={},
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
                        (_JE_OUT / f"{stem}_out.md").write_text(llm_result.value, encoding="utf-8")
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
                        (_JE_OUT / f"{text_file.stem}_out.md").write_text(
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
    # GET /journals/je-out/{filename} — download compiled journal output
    # ------------------------------------------------------------------

    @rt("/journals/je-out/{filename}", methods=["GET"])
    async def journals_download_output(request: Request, filename: str) -> Any:
        """Serve a compiled journal output from je_out/ as a file download.

        Files are written to je_out/{user_uid}/{filename} so ownership is
        enforced implicitly: each user can only reach their own subdirectory.
        No cross-user access is possible even if filenames collide.

        je_out/ is a pipeline staging area excluded from vault sync. Users open
        these files in Obsidian and decide what to carry into their personal vault.
        SKUEL never auto-syncs je_out/ into the vault.
        """
        from starlette.responses import FileResponse

        user_uid = require_authenticated_user(request)

        # Guard: no path traversal, only .md files
        if "/" in filename or "\\" in filename or ".." in filename:
            return Response("Not found", status_code=404)
        if not filename.endswith(".md"):
            return Response("Not found", status_code=404)

        user_out_dir = _JE_OUT / user_uid
        candidate = (user_out_dir / filename).resolve()
        try:
            candidate.relative_to(user_out_dir.resolve())
        except ValueError:
            return Response("Not found", status_code=404)

        if not candidate.is_file():
            return Response("File not found", status_code=404)

        return FileResponse(
            path=str(candidate),
            media_type="text/markdown; charset=utf-8",
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

    @rt("/journals/daily/{date_str}", methods=["GET"])
    async def journal_daily_note(request: Request, date_str: str) -> Any:
        from core.models.user_entry.user_entry_request import UserEntryCreateRequest

        user_uid = require_authenticated_user(request)
        if user_entry_service is None:
            return Response("Service unavailable", status_code=503)
        try:
            target_date = date.fromisoformat(date_str)
        except ValueError:
            target_date = date.today()
        uid = f"ue:daily:{target_date.isoformat()}"
        result = await user_entry_service.get_entry(uid, user_uid)
        if result.is_error:
            return Response("Error loading note", status_code=500)
        if result.value is None:
            create_result = await user_entry_service.create_entry(
                UserEntryCreateRequest(
                    uid=uid,
                    title=f"Daily Note: {target_date.strftime('%A, %B %d, %Y')}",
                    content="",
                    pipeline=Pipeline.NONE,
                    metadata={"entry_kind": "daily", "period_key": target_date.isoformat()},
                ),
                user_uid=user_uid,
            )
            if create_result.is_error:
                return Response("Error creating note", status_code=500)
        return RedirectResponse(f"/journals/{uid}", status_code=302)

    @rt("/journals/weekly/{year}/{week}", methods=["GET"])
    async def journal_weekly_note(request: Request, year: int, week: int) -> Any:
        from core.models.user_entry.user_entry_request import UserEntryCreateRequest

        user_uid = require_authenticated_user(request)
        if user_entry_service is None:
            return Response("Service unavailable", status_code=503)
        uid = f"ue:weekly:{year}-W{week:02d}"
        result = await user_entry_service.get_entry(uid, user_uid)
        if result.is_error:
            return Response("Error loading note", status_code=500)
        if result.value is None:
            create_result = await user_entry_service.create_entry(
                UserEntryCreateRequest(
                    uid=uid,
                    title=f"Weekly Note: W{week}, {year}",
                    content="",
                    pipeline=Pipeline.NONE,
                    metadata={"entry_kind": "weekly", "period_key": f"{year}-W{week:02d}"},
                ),
                user_uid=user_uid,
            )
            if create_result.is_error:
                return Response("Error creating note", status_code=500)
        return RedirectResponse(f"/journals/{uid}", status_code=302)

    @rt("/journals/monthly/{year}/{month}", methods=["GET"])
    async def journal_monthly_note(request: Request, year: int, month: int) -> Any:
        from core.models.user_entry.user_entry_request import UserEntryCreateRequest

        user_uid = require_authenticated_user(request)
        if user_entry_service is None:
            return Response("Service unavailable", status_code=503)
        uid = f"ue:monthly:{year}-{month:02d}"
        result = await user_entry_service.get_entry(uid, user_uid)
        if result.is_error:
            return Response("Error loading note", status_code=500)
        if result.value is None:
            month_name = date(year, month, 1).strftime("%B")
            create_result = await user_entry_service.create_entry(
                UserEntryCreateRequest(
                    uid=uid,
                    title=f"Monthly Note: {month_name} {year}",
                    content="",
                    pipeline=Pipeline.NONE,
                    metadata={"entry_kind": "monthly", "period_key": f"{year}-{month:02d}"},
                ),
                user_uid=user_uid,
            )
            if create_result.is_error:
                return Response("Error creating note", status_code=500)
        return RedirectResponse(f"/journals/{uid}", status_code=302)

    # ------------------------------------------------------------------
    # GET /journals/{entry_uid} — dedicated journal session page
    # ------------------------------------------------------------------

    @rt("/journals/{entry_uid}", methods=["GET"])
    async def journal_chat(request: Request, entry_uid: str) -> Any:
        """Dedicated chat page for a journal entry."""
        from ui.journals import FileOutputFragment, TranscriptReviewFragment
        from ui.journals.chat_page import JournalChatPage

        user_uid = require_authenticated_user(request)

        if user_entry_service is None:
            return Response("Service unavailable", status_code=503)

        from adapters.inbound.result_helpers import require_found
        from core.utils.result_simplified import ErrorCategory

        entry_result = await user_entry_service.get_entry(entry_uid, user_uid)
        found = require_found(entry_result, "Journal entry", entry_uid)
        if found.is_error:
            err = found.expect_error()
            status = 404 if err.category == ErrorCategory.NOT_FOUND else 500
            return Response("Not found" if status == 404 else "Service error", status_code=status)
        entry = found.value

        user_result = await user_service.get_user(user_uid)
        if user_result.is_error or user_result.value is None:
            return Response("Could not load user", status_code=500)
        user = user_result.value

        _journal_pipelines = {
            Pipeline.LLM_SUMMARY,
            Pipeline.TRANSCRIBE,
            Pipeline.TRANSCRIBE_AND_STRUCTURE,
        }
        recent_result = await user_entry_service.list_for_user(user_uid, limit=60)
        recent_entries = [
            e
            for e in (recent_result.value if recent_result.is_ok else [])
            if e.pipeline in _journal_pipelines
        ][:30]

        if entry.processed_file_path:
            initial_workspace = FileOutputFragment(
                title=entry.title or "",
                output_filename=Path(entry.processed_file_path).name,
                response_output=entry.processed_content or "",
            )
        elif entry.processed_content:
            from ui.journals import Stage1Fragment, StandardResponseFragment

            _transcript_pipelines = {Pipeline.TRANSCRIBE, Pipeline.TRANSCRIBE_AND_STRUCTURE}
            if entry.pipeline in _transcript_pipelines:
                initial_workspace = TranscriptReviewFragment(
                    transcript=entry.processed_content,
                    title=entry.title or "",
                )
            elif entry.metadata.get("entry_type") == "journal_stage1_start":
                # FOUNDER text-start: processed_content is the scribe output from run_stage1.
                # Render Stage1Fragment so the user can review and continue to Stage 2/3.
                initial_workspace = Stage1Fragment(
                    raw_entry=entry.content or "",
                    title=entry.title or "",
                    scribe_output=entry.processed_content,
                )
            else:
                initial_workspace = StandardResponseFragment(
                    raw_entry=entry.content or "",
                    title=entry.title or "",
                    response_output=entry.processed_content,
                )
        else:
            from fasthtml.common import Div as _Div
            from fasthtml.common import P as _P

            initial_workspace = _Div(
                _P("Processing…", cls="text-sm text-muted-foreground"),
                id="journal-workspace",
                cls="p-6",
            )

        page_content = JournalChatPage(
            entry=entry,
            recent_entries=recent_entries,
            initial_workspace=initial_workspace,
            user=user,
        )

        if request.headers.get("HX-Request"):
            return page_content

        from ui.layouts.base_page import BasePage
        from ui.layouts.page_types import PageType

        return await BasePage(
            content=page_content,
            title=entry.title or "Journal",
            page_type=PageType.CUSTOM,
            request=request,
            active_page="journals",
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

        Returns FollowUpFragment: two chat bubbles appended to #journal-thread
        plus OOB inputs that update the hidden context fields in #journal-composer.
        The conversation thread grows without replacing the workspace.
        """
        from core.models.enums.user_enums import JournalMode
        from ui.journals import FollowUpErrorFragment, FollowUpFragment

        user_uid = require_authenticated_user(request)

        if not user_reply or not user_reply.strip():
            return FollowUpErrorFragment("Please write something before sending.")

        if journal_service is None:
            return FollowUpErrorFragment("Journal AI features are not available (CORE tier).")

        mode = JournalMode.from_string(journal_mode)
        result = await journal_service.run_follow_up(
            original_entry=original_entry.strip(),
            ai_response=ai_response.strip(),
            user_reply=user_reply.strip(),
            user_uid=user_uid,
            mode=mode,
        )
        if result.is_error:
            logger.error("Journal follow-up failed for %s: %s", user_uid, result.expect_error())
            return FollowUpErrorFragment("Could not generate a response. Please try again.")

        # Accumulate conversation context so further follow-ups have the full history.
        combined = (
            f"{original_entry.strip()}"
            f"\n\n---\n\n# Response\n\n{ai_response.strip()}"
            f"\n\n---\n\n# Follow-up\n\n{user_reply.strip()}"
        )
        return FollowUpFragment(
            user_reply=user_reply.strip(),
            ai_text=result.value,
            combined=combined,
            title=title.strip(),
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
