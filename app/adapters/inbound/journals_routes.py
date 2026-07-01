"""Journals domain routes — DNWF three-stage workflow (FOUNDER) and continuous (STANDARD).

Routes:
    GET  /journals                      — 3-column landing page (no Tasks+ sidebar)
    POST /journals/start                — run workflow on typed text; returns response inline (zero-persistence, ADR-073)
    POST /journals/upload               — file upload handler
    POST /journals/folder-process       — batch folder processing
    GET  /journals/je-out/{filename}    — download a journal output from je_out/
    GET  /journals/{entry_uid}          — periodic-note page (daily/weekly/monthly)
    POST /journals/respond              — STANDARD tier single-response workflow (FULL tier)
    POST /journals/follow-up            — conversation continuation (all tiers)
    POST /journals/stage1               — Stage 1 Scribe (FOUNDER only, FULL tier)
    POST /journals/stage2               — Stage 2 Thought Partner (FOUNDER only, FULL tier)
    POST /journals/stage3               — Stage 3 What Is Related (FOUNDER only, FULL tier)
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from starlette.responses import HTMLResponse, RedirectResponse, Response

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.rate_limit import rate_limited
from core.models.enums.pipeline import Pipeline
from core.utils.logging import get_logger
from ui.journals.components import render_upload_status as render_journal_upload_status

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from services_bootstrap._container import Services


logger = get_logger("skuel.routes.journals")

_JOURNAL_INSTRUCTIONS_DIR = Path(__file__).parents[2] / "data" / "instructions"
_JE_IN = Path("/home/mike/0bsidian/skuel/je_in")
# je_out is a pipeline staging area — excluded from vault sync by the fail-closed
# SyncAllowlist (SKUEL_VAULT_SYNC_ALLOWED_DIRS): only explicitly-allowed folders
# ingest, and je_out is never one of them. Users open je_out files in Obsidian and
# manually decide what enters their personal vault. SKUEL never auto-syncs je_out.
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


def _write_je_out(stem: str, suffix: str, content: str) -> str:
    """Write processed content *flat* to ``je_out/`` and return the filename.

    Zero-persistence (ADR-073): journal processing outputs land in the user's
    own ``je_out/`` folder — local, user-owned, never synced to SKUEL and never
    written to Neo4j. The user opens these in Obsidian and decides what (if
    anything) enters the vault via the doorway folders. The rename formula is
    ``{stem}{suffix}`` (``.txt`` for raw transcripts, ``_out.md`` for compiled
    output), matching the batch/folder-process path so a single scheme applies
    across every entry point. ``Path(stem).name`` strips any path components
    from an untrusted upload filename.
    """
    _JE_OUT.mkdir(parents=True, exist_ok=True)
    filename = f"{Path(stem).name}{suffix}"
    (_JE_OUT / filename).write_text(content, encoding="utf-8")
    return filename


async def _compile_text(
    text: str,
    instructions: str | None,
    *,
    user_uid: str,
    is_founder: bool,
    journal_service: Any,
    processing_service: Any,
) -> Any:
    """Compile raw text to processed output — statelessly. Returns ``Result[str]``.

    FOUNDER runs the full DNWF compile (``run_compiled``); everyone else runs a
    single LLM pass over the text with the supplied instructions. Neither path
    touches Neo4j.
    """
    if is_founder and journal_service is not None:
        return await journal_service.run_compiled(text, user_uid)
    return await _call_llm_with_instructions(text, instructions, processing_service)


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


async def _process_single_upload(
    *,
    file_content: bytes,
    filename: str,
    title: str,
    processing_mode: str,
    instructions: str | None,
    user_uid: str,
    is_founder: bool,
    journal_service: Any,
    batch_transcription_service: Any,
    processing_service: Any,
) -> Any:
    """Process one uploaded file to ``je_out/`` and return an inline fragment.

    Zero-persistence (ADR-073): no ``UserEntry`` is created. Text files compile
    via the LLM; audio transcribes via Deepgram. FOUNDER audio hands the
    transcript to the interactive DNWF review→Scribe flow; everyone else gets a
    ``je_out/`` file plus a download fragment.
    """
    import contextlib
    import tempfile

    from fasthtml.common import to_xml

    from ui.journals import FileOutputFragment, TranscriptReviewFragment

    def _workspace(fragment: Any) -> Any:
        # Success fragments are rooted at ``#journal-workspace`` (the landing
        # centre column), but the upload form posts with ``hx_target="#upload-status"``
        # (right panel). Retarget so the result replaces the centre workspace in
        # place — mirrors ``/journals/start``. Error fragments keep the form's
        # default target and are returned unwrapped.
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
        compiled = await _compile_text(
            text_content,
            instructions,
            user_uid=user_uid,
            is_founder=is_founder,
            journal_service=journal_service,
            processing_service=processing_service,
        )
        if compiled.is_error:
            return render_journal_upload_status("error", str(compiled.error), is_error=True)
        out_name = _write_je_out(stem, "_out.md", compiled.value)
        return _workspace(
            FileOutputFragment(
                title=title, output_filename=out_name, response_output=compiled.value
            )
        )

    # Transcription modes (audio) — require Deepgram (FULL tier).
    if batch_transcription_service is None:
        return render_journal_upload_status(
            "error", "Transcription service not available (requires FULL tier)", is_error=True
        )

    suffix = Path(filename).suffix or ".audio"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file_content)
        tmp_path = tmp.name
    try:
        transcript_result = await batch_transcription_service.transcribe_one(tmp_path)
    finally:
        with contextlib.suppress(OSError):
            Path(tmp_path).unlink()

    if transcript_result.is_error:
        logger.error("Single-file transcription failed: %s", transcript_result.expect_error())
        return render_journal_upload_status(
            "error", "Transcription failed — please try again.", is_error=True
        )
    transcript = transcript_result.value

    if is_founder:
        # FOUNDER: save the raw transcript to je_out and hand it to the DNWF
        # review→Scribe flow (stateless stage routes take over from here).
        _write_je_out(stem, ".txt", transcript)
        return _workspace(TranscriptReviewFragment(transcript=transcript, title=title))

    if processing_mode == "transcribe_and_instructions":
        compiled = await _compile_text(
            transcript,
            instructions,
            user_uid=user_uid,
            is_founder=False,
            journal_service=journal_service,
            processing_service=processing_service,
        )
        if compiled.is_error:
            return render_journal_upload_status("error", str(compiled.error), is_error=True)
        out_name = _write_je_out(stem, "_out.md", compiled.value)
        return _workspace(
            FileOutputFragment(
                title=title, output_filename=out_name, response_output=compiled.value
            )
        )

    # transcribe_only (STANDARD) — raw transcript download.
    out_name = _write_je_out(stem, ".txt", transcript)
    return _workspace(
        FileOutputFragment(title=title, output_filename=out_name, response_output=transcript)
    )


async def _run_batch_over_dir(
    input_dir: Path,
    processing_mode: str,
    instructions: str | None,
    *,
    status_id: str,
    batch_transcription_service: Any,
    processing_service: Any,
) -> Any:
    """Run a batch pipeline over every file in ``input_dir`` → ``je_out/``.

    The shared, zero-persistence engine behind both ``/journals/folder-process``
    (scans ``je_in/``) and multi-file upload (scans a temp dir of uploads). Pure
    filesystem: outputs land in ``je_out/`` via the rename formula, nothing is
    written to Neo4j. Returns a rendered status fragment.
    """
    _JE_OUT.mkdir(parents=True, exist_ok=True)

    if processing_mode in ("transcribe_only", "transcribe_and_instructions"):
        if batch_transcription_service is None:
            return render_journal_upload_status(
                "error",
                "Transcription service not available (requires FULL tier)",
                is_error=True,
            )
        transcribe_result = await batch_transcription_service.transcribe_batch(input_dir, _JE_OUT)
        if transcribe_result.is_error:
            return render_journal_upload_status(
                "error", str(transcribe_result.error), is_error=True, status_id=status_id
            )
        r = transcribe_result.value

        if processing_mode == "transcribe_only":
            msg = (
                f"{r.succeeded} transcribed, {r.failed} failed, {r.skipped} skipped"
                " — results in je_out/"
            )
            is_err = r.failed > 0 and r.succeeded == 0
            return render_journal_upload_status(
                "error" if is_err else "completed", msg, is_error=is_err, status_id=status_id
            )

        # transcribe_and_instructions — LLM-structure each fresh transcript.
        if processing_service is None or getattr(processing_service, "llm_caller", None) is None:
            return render_journal_upload_status(
                "error",
                "LLM service not available (requires INTELLIGENCE_TIER=full)",
                is_error=True,
                status_id=status_id,
            )
        succeeded_stems = {
            Path(res["name"]).stem
            for res in transcribe_result.value.results
            if res.get("status") == "success"
        }
        llm_ok = 0
        llm_fail = 0
        for stem in succeeded_stems:
            txt_path = _JE_OUT / f"{stem}.txt"
            if not txt_path.exists():
                continue
            text = txt_path.read_text(encoding="utf-8")
            llm_result = await _call_llm_with_instructions(text, instructions, processing_service)
            if llm_result.is_error:
                logger.error(f"LLM failed for {stem}: {llm_result.error}")
                llm_fail += 1
            else:
                (_JE_OUT / f"{stem}_out.md").write_text(llm_result.value, encoding="utf-8")
                llm_ok += 1
        msg = (
            f"{r.succeeded} transcribed, {llm_ok} structured, "
            f"{r.failed + llm_fail} failed — results in je_out/"
        )
        # The deliverable is the structured _out.md; if nothing structured, this is
        # a failure even when raw transcripts were written (match the other branches).
        return render_journal_upload_status(
            "completed" if llm_ok > 0 else "error",
            msg,
            is_error=(llm_ok == 0),
            status_id=status_id,
        )

    if processing_mode == "instructions_only":
        if processing_service is None or getattr(processing_service, "llm_caller", None) is None:
            return render_journal_upload_status(
                "error",
                "LLM service not available (requires INTELLIGENCE_TIER=full)",
                is_error=True,
                status_id=status_id,
            )
        if not input_dir.is_dir():
            return render_journal_upload_status(
                "error", f"Input folder not found: {input_dir}", is_error=True, status_id=status_id
            )
        text_files = sorted(
            f for f in input_dir.iterdir() if f.is_file() and f.suffix.lower() in _TEXT_EXTENSIONS
        )
        if not text_files:
            return render_journal_upload_status(
                "error", "No text files found to process", is_error=True, status_id=status_id
            )
        ok = 0
        fail = 0
        for text_file in text_files:
            try:
                text = text_file.read_text(encoding="utf-8")
            except Exception:  # safety-net: per-file read error
                fail += 1
                continue
            llm_result = await _call_llm_with_instructions(text, instructions, processing_service)
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
            "completed" if ok > 0 else "error", msg, is_error=(ok == 0), status_id=status_id
        )

    return render_journal_upload_status(
        "error", f"Unknown processing mode: {processing_mode!r}", is_error=True, status_id=status_id
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

        # Journal sessions are zero-persistence (ADR-073) — there are no stored
        # sessions to list. The landing page is the workshop entry point only.
        page_content = JournalsLandingPage(user=user)

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
    # POST /journals/start — run the workflow on typed text, return inline
    # ------------------------------------------------------------------

    @rt("/journals/start", methods=["POST"])
    @csrf_protected
    @rate_limited(per_user=10, window_s=60)
    async def journals_start(request: Request) -> Any:
        """Run the journal workflow on typed text and return the response inline.

        Zero-persistence (ADR-073): the journal is a private workshop — nothing is
        written to the database. STANDARD tier returns ``StandardResponseFragment``;
        FOUNDER tier returns ``Stage1Fragment`` whose review gate drives the equally
        stateless Stage 2/3 routes. Follow-ups run through ``/journals/follow-up``.
        The user keeps whatever they choose to copy; SKUEL stores nothing.

        On success returns the workspace fragment, retargeted from the form's default
        ``#start-status`` to ``#journal-workspace`` so it replaces the landing centre
        in place. On error returns an inline message swapped into ``#start-status``.
        """
        from fasthtml.common import Div as _Div
        from fasthtml.common import P as _P
        from fasthtml.common import to_xml

        from core.models.enums.user_enums import JournalMode
        from ui.journals import Stage1Fragment, StandardResponseFragment

        def _err(msg: str) -> Any:
            return _Div(_P(msg, cls="text-sm text-destructive"), id="start-status")

        user_uid = require_authenticated_user(request)

        form = await request.form()
        raw_entry = str(form.get("raw_entry", "")).strip()

        if not raw_entry:
            return _err("Please write something before continuing.")

        if journal_service is None:
            return _err("Journal AI features are not available.")

        user_result = await user_service.get_user(user_uid)
        if user_result.is_error or user_result.value is None:
            return _err("Could not load your profile.")

        is_founder = user_result.value.journal_tier.is_founder()
        title = raw_entry.split("\n")[0][:80].strip() or "Journal Entry"

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
            return _err("Could not generate a response. Please try again.")

        if is_founder:
            workspace: Any = Stage1Fragment(
                raw_entry=raw_entry, title=title, scribe_output=ai_result.value
            )
        else:
            workspace = StandardResponseFragment(
                raw_entry=raw_entry, title=title, response_output=ai_result.value
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
            instructions = instruction_content or _load_journal_instruction_file(
                instruction_filename, processing_mode
            )

            user_result = await user_service.get_user(user_uid)
            is_founder = (
                user_result.is_ok
                and user_result.value is not None
                and user_result.value.journal_tier.is_founder()
            )

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
                    journal_service=journal_service,
                    batch_transcription_service=batch_transcription_service,
                    processing_service=processing_service,
                )

            # Multiple files — write to a temp dir and run the shared batch engine
            # (same je_in → je_out cycle as /journals/folder-process). No entries.
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = Path(tmp_dir)
                seen_stems: set[str] = set()
                for uploaded_file in uploaded_files:
                    name = Path(uploaded_file.filename or "unknown").name
                    # Reject duplicate output stems: the batch writes je_out outputs
                    # by stem (``{stem}.txt`` / ``{stem}_out.md``), so `meeting.mp3`
                    # and `meeting.wav` would collapse to the same output and silently
                    # drop one. Key the guard on stem, not the full filename.
                    file_stem = Path(name).stem
                    if file_stem in seen_stems:
                        return render_journal_upload_status(
                            "error",
                            f"Two files map to the same je_out/ output ('{file_stem}') in "
                            "this batch. Rename one and retry.",
                            is_error=True,
                            status_id=status_id,
                        )
                    seen_stems.add(file_stem)
                    (tmp_path / name).write_bytes(await uploaded_file.read())
                return await _run_batch_over_dir(
                    tmp_path,
                    processing_mode,
                    instructions,
                    status_id=status_id,
                    batch_transcription_service=batch_transcription_service,
                    processing_service=processing_service,
                )

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
            require_authenticated_user(request)
            form = await request.form()
            processing_mode = str(form.get("processing_mode", "transcribe_only")).strip()
            instruction_filename = str(form.get("instruction_filename", "")).strip()
            instruction_content = str(form.get("instruction_content", "")).strip()
            instructions = instruction_content or _load_journal_instruction_file(
                instruction_filename, processing_mode
            )

            return await _run_batch_over_dir(
                _JE_IN,
                processing_mode,
                instructions,
                status_id="upload-status",
                batch_transcription_service=batch_transcription_service,
                processing_service=processing_service,
            )

        except Exception as e:  # safety-net: HTMX fragment error boundary
            logger.error(f"Error in folder-process: {e}", exc_info=True)
            return render_journal_upload_status("error", f"Processing failed: {e}", is_error=True)

    # ------------------------------------------------------------------
    # GET /journals/je-out/{filename} — download compiled journal output
    # ------------------------------------------------------------------

    @rt("/journals/je-out/{filename}", methods=["GET"])
    async def journals_download_output(request: Request, filename: str) -> Any:
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

        candidate = (_JE_OUT / filename).resolve()
        try:
            candidate.relative_to(_JE_OUT.resolve())
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
        # user_uid in the UID makes it globally unique — two users sharing the
        # same calendar date get independent notes without backend UID collisions.
        uid = f"ue:daily:{user_uid}:{target_date.isoformat()}"
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
        uid = f"ue:weekly:{user_uid}:{year}-W{week:02d}"
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
        uid = f"ue:monthly:{user_uid}:{year}-{month:02d}"
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
        if entry_result.value.metadata.get("entry_kind") not in {"daily", "weekly", "monthly"}:
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

        # CORE tier (no journal_service) or FULL-tier-without-OpenAI-key → inert
        # cheat-sheet pointer. No stored entry exists, so there is no ownership /
        # allowlist invariant to protect: the content is supplied by the caller.
        if journal_service is None or not journal_service.suggestions_available:
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
        if entry.metadata.get("entry_kind") not in {"daily", "weekly", "monthly"}:
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

        return await BasePage(
            content=page_content,
            title=entry.title or "Periodic Note",
            page_type=PageType.CUSTOM,
            request=request,
            active_page="calendar",
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
