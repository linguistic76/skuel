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
from adapters.inbound.rate_limit import rate_limited
from core.config import get_settings
from core.models.enums.pipeline import JeUse, Pipeline
from core.utils.frontmatter import parse_frontmatter, split_frontmatter
from core.utils.logging import get_logger
from ui.journals.components import render_upload_status as render_journal_upload_status

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.models.conversation import ConversationTurn
    from core.models.type_hints import UserUID
    from core.ports import ConversationOperations
    from core.utils.result_simplified import Result
    from services_bootstrap._container import Services


logger = get_logger("skuel.routes.journals")

_JOURNAL_INSTRUCTIONS_DIR = Path(__file__).parents[2] / "data" / "instructions"


# The je_* journal-exchange staging folders live under the *personal* vault
# (VaultConfig.vault_root — the single source of truth for the vault root), so they
# follow VAULT_ROOT rather than drifting from a hardcoded literal. Resolved lazily
# (get_settings() is cached) to avoid an import-time config dependency.
def _je_in() -> Path:
    return get_settings().vault.vault_path / "je_in"


# je_out is a pipeline staging area — excluded from vault sync by the fail-closed
# SyncAllowlist (code-defined _DEFAULT_SYNC_SUBDIRS): only allowed folders ingest,
# and je_out is never one of them. Users open je_out files in Obsidian and
# manually decide what enters their personal vault. SKUEL never auto-syncs je_out.
def _je_out() -> Path:
    return get_settings().vault.vault_path / "je_out"


# je_raw/je_pro hold curated example input→output pairs, read *off disk at
# processing time* as few-shot exemplars that shape journal-processing STYLE.
# je_raw stays workshop: never ingested, walled unconditionally
# (STAGING_EXCLUDED_DIRS). je_pro is a CONDITIONAL doorway (ADR-073 amendment):
# a je_pro file with explicit `type: user_entry` + `pipeline:` frontmatter (and
# a compatible `je_use:`) ingests as a stored understanding entry; a bare file
# stays exemplar-only. The `je_use:` enum scopes dual duty — `exemplar` (style
# only, never ingested), `understanding` (ingested, never used as a style
# exemplar), `both`/absent (default). This loader is the second consumer that
# must respect it (the ingestion gate `je_pro_skip_reason` is the first).
def _je_raw() -> Path:
    return get_settings().vault.vault_path / "je_raw"


def _je_pro() -> Path:
    return get_settings().vault.vault_path / "je_pro"


_TEXT_EXTENSIONS = {".txt", ".md", ".rst"}
_LLM_MODEL_CLAUDE = "claude-sonnet-4-6"
_LLM_MODEL_GPT = "gpt-4o-mini"
_LLM_MAX_TOKENS = 4000
# Bound token cost of injected exemplars: at most N pairs, each side truncated.
_EXEMPLAR_MAX_PAIRS = 3
_EXEMPLAR_MAX_CHARS = 2000
# Extra read headroom so a je_pro file's YAML frontmatter block (stripped
# before injection — YAML is consent metadata, not style) doesn't eat into the
# exemplar's content budget.
_EXEMPLAR_FRONTMATTER_HEADROOM = 2048


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
    _je_out().mkdir(parents=True, exist_ok=True)
    filename = f"{Path(stem).name}{suffix}"
    (_je_out() / filename).write_text(content, encoding="utf-8")
    return filename


async def _compile_text(
    text: str,
    instructions: str | None,
    *,
    user_uid: str,
    is_founder: bool,
    journal_service: Any,
    processing_service: Any,
    summon_canon: bool = False,
    summon_vault: bool = False,
) -> Any:
    """Compile raw text to processed output — statelessly. Returns ``Result[str]``.

    FOUNDER runs the full DNWF compile (``run_compiled``); everyone else runs a
    single LLM pass over the text with the supplied instructions. Neither path
    touches Neo4j. ``summon_canon`` / ``summon_vault`` reach the FOUNDER compile
    only (ungrounded single passes have no stages to infuse).
    """
    if is_founder and journal_service is not None:
        return await journal_service.run_compiled(
            text, user_uid, summon_canon=summon_canon, summon_vault=summon_vault
        )
    return await _call_llm_with_instructions(text, instructions, processing_service)


def _load_journal_exemplars() -> list[tuple[str, str]]:
    """Read matched ``je_raw``↔``je_pro`` example pairs from disk (ADR-073 §4).

    Pairs are matched by filename **stem**: a ``je_raw`` text file pairs with the
    ``je_pro`` text file sharing its stem. Unmatched files are skipped. The result is
    bounded to ``_EXEMPLAR_MAX_PAIRS`` pairs, each side truncated to
    ``_EXEMPLAR_MAX_CHARS``, to keep token cost predictable.

    Read-only and in-memory: nothing is ingested, persisted, or turned into an entity.
    These teach the pipeline *how the user likes journals processed* (style), never
    facts about the user. Missing/empty folders yield ``[]`` — the caller degrades to
    today's no-exemplar behavior.

    ``je_use`` scoping (ADR-073 amendment): a je_pro file whose frontmatter
    resolves to UNDERSTANDING is never used as a style exemplar; an
    unrecognized ``je_use`` value also skips (garbled scoping intent is
    honored in neither direction — the ingestion gate skips it too). Any YAML
    frontmatter block is stripped before injection: it is consent metadata,
    not processing style.
    """

    def _text_files(directory: Path) -> dict[str, Path]:
        try:
            entries = sorted(directory.iterdir()) if directory.is_dir() else []
        except OSError as e:  # unscannable folder — degrade to no exemplars
            logger.warning(f"Skipping journal exemplar folder {directory}: {e}")
            return {}
        return {p.stem: p for p in entries if p.is_file() and p.suffix.lower() in _TEXT_EXTENSIONS}

    def _read_exemplar(path: Path) -> tuple[dict[str, Any], str] | None:
        # Read only a bounded prefix — never load an oversized exemplar fully.
        # Frontmatter headroom keeps the stripped body at full budget.
        # UnicodeDecodeError (a UnicodeError, NOT an OSError) must be caught here
        # too, or an undecodable file would abort the whole request instead of
        # being skipped.
        try:
            with path.open(encoding="utf-8") as fh:
                raw_text = fh.read(_EXEMPLAR_MAX_CHARS + _EXEMPLAR_FRONTMATTER_HEADROOM)
        except (OSError, UnicodeError) as e:  # unreadable/undecodable — skip it
            logger.warning(f"Skipping unreadable journal exemplar {path.name!r}: {e}")
            return None
        if raw_text.startswith("---") and split_frontmatter(raw_text)[0] is None:
            # An opening fence with no close inside the bounded read: parsing
            # would silently default je_use to BOTH and inject the raw YAML as
            # style (Codex #608) — fail closed, skip the file.
            logger.warning(
                f"Skipping journal exemplar {path.name!r}: frontmatter does not "
                "close within the bounded read"
            )
            return None
        frontmatter, body = parse_frontmatter(raw_text)
        return frontmatter, body[:_EXEMPLAR_MAX_CHARS]

    raw_by_stem = _text_files(_je_raw())
    pro_by_stem = _text_files(_je_pro())
    pairs: list[tuple[str, str]] = []
    for stem in sorted(raw_by_stem.keys() & pro_by_stem.keys()):
        if len(pairs) >= _EXEMPLAR_MAX_PAIRS:
            break
        pro_read = _read_exemplar(pro_by_stem[stem])
        if pro_read is None:
            continue
        pro_frontmatter, pro = pro_read
        if JeUse.from_string(pro_frontmatter.get("je_use")) not in (JeUse.BOTH, JeUse.EXEMPLAR):
            continue  # understanding-only (or garbled scoping) — never style
        raw_read = _read_exemplar(raw_by_stem[stem])
        if raw_read is None:
            continue
        _, raw = raw_read
        if raw.strip() and pro.strip():
            pairs.append((raw, pro))
    return pairs


def _build_exemplar_preamble(pairs: list[tuple[str, str]]) -> str:
    """Render exemplar pairs as a labeled few-shot block, or ``""`` if none."""
    if not pairs:
        return ""
    blocks = [
        f"### Example {i} — raw input\n{raw}\n\n### Example {i} — processed output\n{pro}"
        for i, (raw, pro) in enumerate(pairs, start=1)
    ]
    body = "\n\n".join(blocks)
    return (
        "The following are examples of how this user likes a journal processed. "
        "Match their STYLE and structure. Do NOT treat their content as facts about "
        f"the user or carry it into your output.\n\n{body}"
    )


async def _call_llm_with_instructions(
    text: str,
    instructions: str | None,
    processing_service: Any,
) -> Any:
    """Call LLM directly on raw text for folder processing (no database records).

    When curated ``je_raw``/``je_pro`` example pairs are present, they are injected as
    few-shot style exemplars (ADR-073 §4) — read-only, zero-persistence.
    """
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
    preamble = _build_exemplar_preamble(_load_journal_exemplars())
    header = "\n\n".join(part for part in (instructions, preamble) if part)
    prompt = f"{header}\n\n---\n\n{text}" if header else text
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
    retarget_workspace: bool,
    journal_service: Any,
    batch_transcription_service: Any,
    processing_service: Any,
    summon_canon: bool = False,
    summon_vault: bool = False,
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
        compiled = await _compile_text(
            text_content,
            instructions,
            user_uid=user_uid,
            is_founder=is_founder,
            journal_service=journal_service,
            processing_service=processing_service,
            summon_canon=summon_canon,
            summon_vault=summon_vault,
        )
        if compiled.is_error:
            return render_journal_upload_status("error", str(compiled.error), is_error=True)
        out_name = _write_je_out(stem, "_out.md", compiled.value)
        return _workspace(
            FileOutputFragment(
                title=title,
                output_filename=out_name,
                response_output=compiled.value,
                is_founder=is_founder,
            )
        )

    # Transcription modes (audio) — require Deepgram (FULL tier).
    if batch_transcription_service is None:
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
        and (processing_service is None or getattr(processing_service, "llm_caller", None) is None)
    ):
        return render_journal_upload_status(
            "error", "LLM service not available (requires INTELLIGENCE_TIER=full)", is_error=True
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
                title=title,
                output_filename=out_name,
                response_output=compiled.value,
                is_founder=is_founder,
            )
        )

    # transcribe_only (STANDARD) — raw transcript download.
    out_name = _write_je_out(stem, ".txt", transcript)
    return _workspace(
        FileOutputFragment(
            title=title,
            output_filename=out_name,
            response_output=transcript,
            is_founder=is_founder,
        )
    )


async def _run_batch_over_dir(
    input_dir: Path,
    processing_mode: str,
    instructions: str | None,
    *,
    status_id: str,
    batch_transcription_service: Any,
    processing_service: Any,
    skip_existing: bool = True,
) -> Any:
    """Run a batch pipeline over every file in ``input_dir`` → ``je_out/``.

    The shared, zero-persistence engine behind both ``/journals/folder-process``
    (scans ``je_in/``) and multi-file upload (scans a temp dir of uploads). Pure
    filesystem: outputs land in ``je_out/`` via the rename formula, nothing is
    written to Neo4j. Returns a rendered status fragment.

    ``skip_existing`` controls transcription reuse: ``True`` (folder-process) keeps
    idempotent rerun semantics — a file whose ``je_out/{stem}.txt`` already exists
    is not re-transcribed. ``False`` (uploads) forces fresh transcription, since an
    upload is new content that must not be shadowed by a stale same-stem transcript.
    """
    _je_out().mkdir(parents=True, exist_ok=True)

    if processing_mode in ("transcribe_only", "transcribe_and_instructions"):
        if batch_transcription_service is None:
            return render_journal_upload_status(
                "error",
                "Transcription service not available (requires FULL tier)",
                is_error=True,
                status_id=status_id,
            )
        # Verify the LLM branch BEFORE transcribing: transcription spends Deepgram
        # quota and writes .txt to je_out/, so a missing llm_caller must fail the
        # whole run up front, not after every file is transcribed for nothing.
        if processing_mode == "transcribe_and_instructions" and (
            processing_service is None or getattr(processing_service, "llm_caller", None) is None
        ):
            return render_journal_upload_status(
                "error",
                "LLM service not available (requires INTELLIGENCE_TIER=full)",
                is_error=True,
                status_id=status_id,
            )
        # transcribe_and_instructions structures the transcript into ``_out.md``,
        # so the transcript must reflect the CURRENT audio — never reuse a stale
        # ``je_out/{stem}.txt`` from a prior run whose audio was since replaced
        # under the same basename. Force fresh transcription for that mode;
        # transcribe_only may reuse per the caller's ``skip_existing``
        # (folder-process reruns idempotently, uploads are always fresh).
        effective_skip = skip_existing if processing_mode == "transcribe_only" else False
        transcribe_result = await batch_transcription_service.transcribe_batch(
            input_dir, _je_out(), skip_existing=effective_skip
        )
        if transcribe_result.is_error:
            return render_journal_upload_status(
                "error", str(transcribe_result.error), is_error=True, status_id=status_id
            )
        r = transcribe_result.value

        # No supported audio files at all (e.g. a text/PDF folder under "Transcribe
        # only") is a validation error, not a silent success.
        if r.total_files == 0:
            return render_journal_upload_status(
                "error",
                "No supported audio files found to transcribe",
                is_error=True,
                status_id=status_id,
            )

        if processing_mode == "transcribe_only":
            msg = (
                f"{r.succeeded} transcribed, {r.failed} failed, {r.skipped} skipped"
                " — results in je_out/"
            )
            is_err = r.failed > 0 and r.succeeded == 0
            return render_journal_upload_status(
                "error" if is_err else "completed", msg, is_error=is_err, status_id=status_id
            )

        # transcribe_and_instructions — LLM-structure each freshly-transcribed
        # transcript (LLM availability already verified above). This mode forces
        # skip_existing=False (see above), so every audio file yields a ``success``
        # with a current transcript — no ``skipped`` stems to worry about staleness.
        structurable_stems = {
            Path(res["name"]).stem
            for res in transcribe_result.value.results
            if res.get("status") == "success"
        }
        llm_ok = 0
        llm_fail = 0
        for stem in structurable_stems:
            txt_path = _je_out() / f"{stem}.txt"
            if not txt_path.exists():
                continue
            text = txt_path.read_text(encoding="utf-8")
            llm_result = await _call_llm_with_instructions(text, instructions, processing_service)
            if llm_result.is_error:
                logger.error(f"LLM failed for {stem}: {llm_result.error}")
                llm_fail += 1
            else:
                (_je_out() / f"{stem}_out.md").write_text(llm_result.value, encoding="utf-8")
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
                (_je_out() / f"{text_file.stem}_out.md").write_text(
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
# Discussion persistence helpers (ADR-078) — typed /journals/start door
# ---------------------------------------------------------------------------


async def _create_discussion_session(
    conversation_service: ConversationOperations,
    *,
    user_uid: UserUID,
    title: str,
    canon_book_uids: list[str],
    summon_vault: bool,
    raw_entry: str,
    ai_text: str,
) -> Result[str]:
    """Create an owner-private discussion session + its opening turn pair.

    Records the opening source selection (canon shelf books + vault toggle) as
    JSON so a continued session can restore it (C3, consumed in P3). The opening
    pair is written atomically. Returns the session id, or the first failure.
    """
    import json

    from core.models.conversation import CONVERSATION_KIND_DISCUSSION
    from core.utils.result_simplified import Result

    # canon_on == whether canon is summoned; at start that is exactly "any book
    # checked" (the landing panel has no whole-shelf toggle).
    source_selection = json.dumps(
        {
            "canon": list(canon_book_uids),
            "canon_on": bool(canon_book_uids),
            "vault": bool(summon_vault),
        }
    )
    created = await conversation_service.create_session(
        user_uid, CONVERSATION_KIND_DISCUSSION, title, source_selection
    )
    if created.is_error:
        return Result.fail(created)
    appended = await conversation_service.append_exchange(
        created.value.session_id, user_uid, raw_entry, ai_text
    )
    if appended.is_error:
        return Result.fail(appended)
    return Result.ok(created.value.session_id)


def _history_to_follow_up_context(turns: list[ConversationTurn]) -> tuple[str, str]:
    """Reconstruct ``(original_entry, ai_response)`` for ``run_follow_up`` from turns.

    Replaces the deleted client-side accumulator with the Neo4j turn history:
    ``ai_response`` is the most recent assistant turn (the "previous response");
    ``original_entry`` is a rendered transcript of everything before it. A
    session always opens with a user/assistant pair, so both are populated.
    """
    from core.models.conversation import ROLE_ASSISTANT, ROLE_USER

    if not turns:
        return "", ""
    split = len(turns)
    ai_response = ""
    for index in range(len(turns) - 1, -1, -1):
        if turns[index].role == ROLE_ASSISTANT:
            ai_response = turns[index].content
            split = index
            break
    rendered = "\n\n".join(
        f"# {'You' if turn.role == ROLE_USER else 'Journal'}\n\n{turn.content}"
        for turn in turns[:split]
    )
    return rendered, ai_response


def _parse_source_selection(raw: str) -> tuple[list[str], bool, bool]:
    """Parse a stored ``source_selection`` JSON → (canon book uids, canon on, vault on).

    Shape: ``{"canon": [uid, …], "canon_on": bool, "vault": bool}``. The book
    *scope* (``canon``) is kept independent of the *dial* (``canon_on``) so an
    ungrounded follow-up never erases the session's book scope (Codex #635 P2).
    Fail-soft: a malformed / empty value restores nothing. Back-compat: pre-PR3
    sessions carry no ``canon_on`` — infer it from a non-empty book list.
    """
    import json

    try:
        data = json.loads(raw) if raw else {}
    except ValueError, TypeError:
        return [], False, False
    if not isinstance(data, dict):
        return [], False, False
    raw_canon = data.get("canon")
    canon = [str(u) for u in raw_canon if isinstance(u, str)] if isinstance(raw_canon, list) else []
    canon_on = bool(data.get("canon_on", bool(canon)))
    vault = bool(data.get("vault"))
    return canon, canon_on, vault


def _render_discussion_markdown(title: str, turns: list[ConversationTurn]) -> str:
    """Render a discussion to a markdown transcript for export (ADR-078 §8).

    A user-ownable copy — NOT a vault read-back folder (ADR-073 has none).
    """
    from core.models.conversation import ROLE_USER

    lines = [f"# {title or 'Discussion'}", ""]
    for turn in turns:
        lines.append(f"## {'You' if turn.role == ROLE_USER else 'Journal'}")
        lines.append("")
        lines.append(turn.content)
        lines.append("")
    return "\n".join(lines)


def _safe_export_filename(title: str) -> str:
    """A safe ``.md`` download filename derived from the discussion title."""
    import re

    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", (title or "discussion").strip()).strip("-")
    return f"{slug[:60] or 'discussion'}.md"


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
    # ADR-078 discussion store — tier-independent (present in CORE and FULL), but
    # only reached at FULL tier since /journals/start requires journal_service.
    assert services.conversation is not None, (
        "ConversationService must be wired before journals routes"
    )
    conversation_service = services.conversation

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

        page_content = JournalsLandingPage(user=user, shelf_books=shelf_books, sessions=sessions)

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

        ai_result = await journal_service.run_discussion(
            raw_entry,
            user_uid,
            JournalMode.default(),
            summon_canon=summon_canon,
            summon_vault=summon_vault,
            canon_book_uids=canon_book_uids or None,
        )

        if ai_result.is_error:
            logger.error(
                "journals_start AI call failed for %s: %s",
                user_uid,
                ai_result.expect_error(),
            )
            return _err("Could not generate a response. Please try again.")

        ai_text = ai_result.value.text

        # Persist the discussion (ADR-078): create the owner-private session, then
        # the opening user/assistant turn pair. The session records the opening
        # source selection so a continued session (P3) can restore it. Only after
        # a successful LLM response — a failed discussion leaves no session.
        session_result = await _create_discussion_session(
            conversation_service,
            user_uid=user_uid,
            title=title,
            canon_book_uids=canon_book_uids,
            summon_vault=summon_vault,
            raw_entry=raw_entry,
            ai_text=ai_text,
        )
        if session_result.is_error:
            logger.error(
                "journals_start could not persist discussion for %s: %s",
                user_uid,
                session_result.expect_error(),
            )
            return _err("Could not save your discussion. Please try again.")

        workspace = StandardResponseFragment(
            raw_entry=raw_entry,
            title=title,
            response_output=ai_text,
            session_id=session_result.value,
            mode=JournalMode.default(),
            is_founder=is_founder,
            sources=ai_result.value.sources,
            canon_book_uids=tuple(canon_book_uids),
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
                    journal_service=journal_service,
                    batch_transcription_service=batch_transcription_service,
                    processing_service=processing_service,
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
            from core.services.transcription.batch_transcription_service import AUDIO_EXTENSIONS

            output_exts = (
                _TEXT_EXTENSIONS if processing_mode == "instructions_only" else (AUDIO_EXTENSIONS)
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
                return await _run_batch_over_dir(
                    tmp_path,
                    processing_mode,
                    instructions,
                    status_id=status_id,
                    batch_transcription_service=batch_transcription_service,
                    processing_service=processing_service,
                    # Uploads are fresh content — never reuse a stale same-stem
                    # transcript already sitting in the flat je_out/ folder.
                    skip_existing=False,
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
                _je_in(),
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

        candidate = (_je_out() / filename).resolve()
        try:
            candidate.relative_to(_je_out().resolve())
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
                    # SEAM (intended): an in-app periodic note is a SKUEL-only stub.
                    # It is NOT task-round-trip-eligible — outbound sync
                    # (vault_reconciler._run_outbound) processes only entries with
                    # pipeline=EXTRACT_ACTIVITIES that also carry a vault_file_path.
                    # This stub has neither; the *vault file* (created/edited in
                    # Obsidian with `pipeline: extract_activities` frontmatter, then
                    # ingested) is the source of truth for round-trip eligibility.
                    # Setting the pipeline here would NOT make it eligible (no
                    # vault_file_path), so it would only mislead — hence NONE.
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
                    # SEAM (intended): SKUEL-only stub, not round-trip-eligible.
                    # See the daily-note handler above for the full rationale.
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
                    # SEAM (intended): SKUEL-only stub, not round-trip-eligible.
                    # See the daily-note handler above for the full rationale.
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
        canon_books, canon_on, vault_on = _parse_source_selection(session.source_selection)
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

        return await BasePage(
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

        markdown = _render_discussion_markdown(session.title, turns_result.value)
        filename = _safe_export_filename(session.title)
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
    # POST /journals/follow-up — conversation continuation
    # ------------------------------------------------------------------

    @rt("/journals/follow-up", methods=["POST"])
    @csrf_protected
    async def journals_follow_up(
        request: Request,
        user_reply: str,
        session_id: str = "",
        original_entry: str = "",
        ai_response: str = "",
        title: str = "",
        journal_mode: str = "",
        summon_canon: bool = False,
        summon_vault: bool = False,
        canon_book_uids: str = "",
    ) -> Any:
        """Continue a journal conversation.

        Two memory models, selected by ``session_id`` (ADR-078):

        - **Session-backed** (``session_id`` set — the typed ``/journals/start``
          door): prior turns are read from Neo4j (owner-checked — a non-owner
          session is 404-not-403), context is rebuilt from them, and the new
          user/assistant pair is appended. No client-side accumulator.
        - **Stateless** (no ``session_id`` — the file-output / DNWF-stage-3
          doors, zero-persistence until P3): context comes from the
          ``original_entry`` / ``ai_response`` hidden fields and grows via OOB
          swaps, exactly as before.

        Returns FollowUpFragment: chat bubbles appended to #journal-thread (plus
        the OOB accumulator inputs only on the stateless path).

        ``canon_book_uids`` is a CSV of the shelf books the discussion opened on
        (the composer carries it as a hidden field) — it keeps follow-ups scoped
        to the same books the session chose (C3).
        """
        from core.models.enums.user_enums import JournalMode
        from ui.journals import FollowUpErrorFragment, FollowUpFragment

        user_uid = require_authenticated_user(request)

        if not user_reply or not user_reply.strip():
            return FollowUpErrorFragment("Please write something before sending.")

        if journal_service is None:
            return FollowUpErrorFragment("Journal AI features are not available (CORE tier).")

        # Both dials are FOUNDER entitlements — the composer dials are hidden
        # for other tiers, but a POST flag is forgeable, so gate them
        # server-side (Codex #572 P1). One user resolve covers both; only load
        # the user when a summon is actually requested (no cost on the common
        # ungrounded follow-up).
        if summon_canon or summon_vault:
            user_result = await user_service.get_user(user_uid)
            is_founder = (
                user_result.is_ok
                and user_result.value is not None
                and user_result.value.journal_tier.is_founder()
            )
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
            prior_entry, prior_ai = _history_to_follow_up_context(turns_result.value)
            result = await journal_service.run_follow_up(
                original_entry=prior_entry,
                ai_response=prior_ai,
                user_reply=reply,
                user_uid=user_uid,
                mode=mode,
                summon_canon=summon_canon,
                summon_vault=summon_vault,
                canon_book_uids=book_uids,
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
            import json

            scope_books = [book for book in canon_book_uids.split(",") if book.strip()]
            selection = json.dumps(
                {
                    "canon": scope_books,
                    "canon_on": bool(summon_canon),
                    "vault": bool(summon_vault),
                }
            )
            await conversation_service.update_source_selection(session_id, user_uid, selection)
            # combined=None → session-backed fragment (no OOB accumulator).
            return FollowUpFragment(
                user_reply=reply,
                ai_text=ai_text,
                title=title.strip(),
                mode=mode,
                sources=result.value.sources,
            )

        # Stateless path (file-output / DNWF doors) — context from hidden fields.
        result = await journal_service.run_follow_up(
            original_entry=original_entry.strip(),
            ai_response=ai_response.strip(),
            user_reply=reply,
            user_uid=user_uid,
            mode=mode,
            summon_canon=summon_canon,
            summon_vault=summon_vault,
            canon_book_uids=book_uids,
        )
        if result.is_error:
            logger.error("Journal follow-up failed for %s: %s", user_uid, result.expect_error())
            return FollowUpErrorFragment("Could not generate a response. Please try again.")

        # Accumulate conversation context so further follow-ups have the full history.
        combined = (
            f"{original_entry.strip()}"
            f"\n\n---\n\n# Response\n\n{ai_response.strip()}"
            f"\n\n---\n\n# Follow-up\n\n{reply}"
        )
        return FollowUpFragment(
            user_reply=reply,
            ai_text=result.value.text,
            title=title.strip(),
            mode=mode,
            sources=result.value.sources,
            combined=combined,
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
        summon_canon: bool = False,
        summon_vault: bool = False,
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
            summon_canon=summon_canon,
            summon_vault=summon_vault,
        )
        if result.is_error:
            logger.error("Stage 3 failed for %s: %s", user_uid, result.expect_error())
            return ErrorFragment("Stage 3 failed. Please try again.")

        return Stage3Fragment(
            raw_entry=raw_entry,
            title=title,
            related_output=result.value,
            is_founder=True,  # route is FOUNDER-gated above
        )
