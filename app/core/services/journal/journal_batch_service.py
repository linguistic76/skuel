"""Batch journal processing — the zero-persistence je_in/upload → je_out engine.

The shared pipeline behind ``POST /journals/upload`` (single + multi-file) and
``POST /journals/folder-process``: transcribe audio (Deepgram), compile text
(LLM / FOUNDER DNWF), and land outputs *flat* in the user's own ``je_out/``
folder via the doorway rename formula — ``{stem}.txt`` for raw transcripts,
``{stem}_out.md`` for compiled output.

Zero-persistence (ADR-073): journals store ZERO — no method in this service
touches Neo4j. Outputs are local, user-owned files the user opens in Obsidian
and manually decides what (if anything) enters the vault via the doorway
folders. Filesystem writes are deliberately direct (not VaultBridgePort): the
je_* staging folders are pipeline workspace, not synced vault content.

The je_* staging folders live under the *personal* vault root
(``VaultConfig.vault_root``):

- ``je_in/``  — batch input folder scanned by folder-process
- ``je_out/`` — output staging, excluded from vault sync by the fail-closed
  ``SyncAllowlist`` (never an allowed folder); SKUEL never auto-syncs it
- ``je_raw/`` / ``je_pro/`` — curated example input→output pairs read *off disk
  at processing time* as few-shot style exemplars (ADR-073 §4). ``je_raw``
  stays workshop (never ingested, walled unconditionally). ``je_pro`` is a
  CONDITIONAL doorway (ADR-073 amendment) scoped by the ``je_use:`` enum —
  ``exemplar`` (style only), ``understanding`` (ingested, never style),
  ``both``/absent (default). This loader is the second consumer that must
  respect it (the ingestion gate ``je_pro_skip_reason`` is the first).

Instruction files resolve through the journal instruction-loading home:
``instruction_loader.load_named_instruction``.
"""

from __future__ import annotations

import contextlib
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.config import get_settings
from core.models.enums.pipeline import JeUse
from core.models.type_hints import UserUID
from core.services.chat import resolve_chat_model
from core.services.journal.instruction_loader import load_named_instruction
from core.utils.frontmatter import parse_frontmatter, split_frontmatter
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.journal.journal_service import JournalService
    from core.services.llm_caller import UnifiedLLMCaller
    from core.services.transcription.batch_transcription_service import (
        BatchTranscriptionService,
    )

logger = get_logger("skuel.services.journal.batch")

TEXT_EXTENSIONS = {".txt", ".md", ".rst"}
_LLM_MAX_TOKENS = 4000
# Bound token cost of injected exemplars: at most N pairs, each side truncated.
EXEMPLAR_MAX_PAIRS = 3
EXEMPLAR_MAX_CHARS = 2000
# Extra read headroom so a je_pro file's YAML frontmatter block (stripped
# before injection — YAML is consent metadata, not style) doesn't eat into the
# exemplar's content budget.
EXEMPLAR_FRONTMATTER_HEADROOM = 2048


@dataclass(frozen=True)
class BatchRunReport:
    """Outcome of a batch run — routes render it as their status fragment.

    ``ok`` maps to the fragment's completed/error pairing; ``message`` is the
    user-facing summary line (counts or the failure reason).
    """

    ok: bool
    message: str


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


class JournalBatchService:
    """Zero-persistence batch pipeline over the je_* staging folders.

    Every dependency is optional so the service exists at every intelligence
    tier: a missing transcription service or LLM caller degrades each mode to
    its tier-error message (never a crash). ``vault_root`` overrides the je_*
    folder root for tests; ``None`` (production) resolves lazily through
    ``get_settings()`` so the service tracks ``VAULT_ROOT``.
    """

    def __init__(
        self,
        *,
        batch_transcription_service: BatchTranscriptionService | None = None,
        llm_caller: UnifiedLLMCaller | None = None,
        journal_service: JournalService | None = None,
        vault_root: Path | None = None,
    ) -> None:
        self.batch_transcription_service = batch_transcription_service
        self.llm_caller = llm_caller
        self.journal_service = journal_service
        self._vault_root = vault_root
        self.logger = logger

    # ------------------------------------------------------------------
    # Staging folders
    # ------------------------------------------------------------------

    def _vault(self) -> Path:
        return self._vault_root or get_settings().vault.vault_path

    @property
    def je_in_dir(self) -> Path:
        """Batch input folder scanned by folder-process."""
        return self._vault() / "je_in"

    @property
    def je_out_dir(self) -> Path:
        """Flat output staging folder — never synced, never ingested."""
        return self._vault() / "je_out"

    @property
    def _je_raw_dir(self) -> Path:
        return self._vault() / "je_raw"

    @property
    def _je_pro_dir(self) -> Path:
        return self._vault() / "je_pro"

    # ------------------------------------------------------------------
    # Availability (tier preflights)
    # ------------------------------------------------------------------

    @property
    def transcription_available(self) -> bool:
        """Deepgram wired (FULL tier) — audio modes need it."""
        return self.batch_transcription_service is not None

    @property
    def llm_available(self) -> bool:
        """LLM caller wired (INTELLIGENCE_TIER=full) — compile modes need it."""
        return self.llm_caller is not None

    # ------------------------------------------------------------------
    # Building blocks
    # ------------------------------------------------------------------

    def resolve_instructions(
        self,
        *,
        instruction_content: str,
        instruction_filename: str,
        processing_mode: str,
    ) -> str | None:
        """Resolve the run's instructions: inline content wins over a named file.

        ``transcribe_only`` never carries instructions (there is no compile
        step), and an absent filename resolves to ``None`` — the pipeline runs
        uninstructed. File loading (with path containment) lives in
        ``instruction_loader.load_named_instruction``.
        """
        if instruction_content:
            return instruction_content
        if processing_mode == "transcribe_only" or not instruction_filename:
            return None
        return load_named_instruction(instruction_filename)

    def write_output(self, stem: str, suffix: str, content: str) -> str:
        """Write processed content *flat* to ``je_out/`` and return the filename.

        The doorway rename formula is ``{stem}{suffix}`` (``.txt`` for raw
        transcripts, ``_out.md`` for compiled output) — one scheme across every
        entry point. ``Path(stem).name`` strips any path components from an
        untrusted upload filename.
        """
        self.je_out_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{Path(stem).name}{suffix}"
        (self.je_out_dir / filename).write_text(content, encoding="utf-8")
        return filename

    async def transcribe_upload(self, file_content: bytes, suffix: str) -> Result[str]:
        """Transcribe one uploaded audio payload via a temp file → transcript text.

        The upload bytes never touch the je_* folders — they stage through a
        ``NamedTemporaryFile`` that is always unlinked.
        """
        if self.batch_transcription_service is None:
            return Result.fail(
                Errors.business(
                    rule="transcription_tier_required",
                    message="Transcription service not available (requires FULL tier)",
                )
            )
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name
        try:
            return await self.batch_transcription_service.transcribe_one(tmp_path)
        finally:
            with contextlib.suppress(OSError):
                Path(tmp_path).unlink()

    async def compile_text(
        self,
        text: str,
        instructions: str | None,
        *,
        user_uid: UserUID,
        is_founder: bool,
        summon_canon: bool = False,
        summon_vault: bool = False,
    ) -> Result[str]:
        """Compile raw text to processed output — statelessly. Returns ``Result[str]``.

        FOUNDER runs the full DNWF compile (``run_compiled``); everyone else runs
        a single LLM pass over the text with the supplied instructions. Neither
        path touches Neo4j. ``summon_canon`` / ``summon_vault`` reach the FOUNDER
        compile only (ungrounded single passes have no stages to infuse).
        """
        if is_founder and self.journal_service is not None:
            return await self.journal_service.run_compiled(
                text, user_uid, summon_canon=summon_canon, summon_vault=summon_vault
            )
        return await self._call_llm_with_instructions(text, instructions)

    async def _call_llm_with_instructions(self, text: str, instructions: str | None) -> Result[str]:
        """Call the LLM directly on raw text (no database records).

        When curated ``je_raw``/``je_pro`` example pairs are present, they are
        injected as few-shot style exemplars (ADR-073 §4) — read-only,
        zero-persistence.
        """
        if self.llm_caller is None:
            return Result.fail(
                Errors.business(
                    rule="llm_tier_required",
                    message="LLM processing requires INTELLIGENCE_TIER=full",
                )
            )
        # DNWF batch compile has no picker → the app-safe default via the shared
        # switcher seam (converges with JournalService; no implicit Claude default).
        model = resolve_chat_model(None, self.llm_caller)
        preamble = _build_exemplar_preamble(self._load_exemplars())
        header = "\n\n".join(part for part in (instructions, preamble) if part)
        prompt = f"{header}\n\n---\n\n{text}" if header else text
        try:
            return await self.llm_caller.generate(
                prompt=prompt, model=model, max_tokens=_LLM_MAX_TOKENS
            )
        except Exception as e:  # safety-net: LLM call errors in folder-batch context
            return Result.fail(Errors.integration(service="llm", message=f"LLM failed: {e}"))

    def _load_exemplars(self) -> list[tuple[str, str]]:
        """Read matched ``je_raw``↔``je_pro`` example pairs from disk (ADR-073 §4).

        Pairs are matched by filename **stem**: a ``je_raw`` text file pairs with
        the ``je_pro`` text file sharing its stem. Unmatched files are skipped.
        The result is bounded to ``EXEMPLAR_MAX_PAIRS`` pairs, each side
        truncated to ``EXEMPLAR_MAX_CHARS``, to keep token cost predictable.

        Read-only and in-memory: nothing is ingested, persisted, or turned into
        an entity. These teach the pipeline *how the user likes journals
        processed* (style), never facts about the user. Missing/empty folders
        yield ``[]`` — the caller degrades to no-exemplar behavior.

        ``je_use`` scoping (ADR-073 amendment): a je_pro file whose frontmatter
        resolves to UNDERSTANDING is never used as a style exemplar; an
        unrecognized ``je_use`` value also skips (garbled scoping intent is
        honored in neither direction — the ingestion gate skips it too). Any
        YAML frontmatter block is stripped before injection: it is consent
        metadata, not processing style.
        """

        def _text_files(directory: Path) -> dict[str, Path]:
            try:
                entries = sorted(directory.iterdir()) if directory.is_dir() else []
            except OSError as e:  # unscannable folder — degrade to no exemplars
                self.logger.warning(f"Skipping journal exemplar folder {directory}: {e}")
                return {}
            return {
                p.stem: p for p in entries if p.is_file() and p.suffix.lower() in TEXT_EXTENSIONS
            }

        def _read_exemplar(path: Path) -> tuple[dict[str, Any], str] | None:
            # Read only a bounded prefix — never load an oversized exemplar fully.
            # Frontmatter headroom keeps the stripped body at full budget.
            # UnicodeDecodeError (a UnicodeError, NOT an OSError) must be caught
            # here too, or an undecodable file would abort the whole request
            # instead of being skipped.
            try:
                with path.open(encoding="utf-8") as fh:
                    raw_text = fh.read(EXEMPLAR_MAX_CHARS + EXEMPLAR_FRONTMATTER_HEADROOM)
            except (OSError, UnicodeError) as e:  # unreadable/undecodable — skip it
                self.logger.warning(f"Skipping unreadable journal exemplar {path.name!r}: {e}")
                return None
            if raw_text.startswith("---") and split_frontmatter(raw_text)[0] is None:
                # An opening fence with no close inside the bounded read: parsing
                # would silently default je_use to BOTH and inject the raw YAML as
                # style (Codex #608) — fail closed, skip the file.
                self.logger.warning(
                    f"Skipping journal exemplar {path.name!r}: frontmatter does not "
                    "close within the bounded read"
                )
                return None
            frontmatter, body = parse_frontmatter(raw_text)
            return frontmatter, body[:EXEMPLAR_MAX_CHARS]

        raw_by_stem = _text_files(self._je_raw_dir)
        pro_by_stem = _text_files(self._je_pro_dir)
        pairs: list[tuple[str, str]] = []
        for stem in sorted(raw_by_stem.keys() & pro_by_stem.keys()):
            if len(pairs) >= EXEMPLAR_MAX_PAIRS:
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

    # ------------------------------------------------------------------
    # Batch engine
    # ------------------------------------------------------------------

    async def run_batch_over_dir(  # skuel-lint: disable=SKUEL005 -- total function: every failure is a user-renderable BatchRunReport line, not an error channel
        self,
        input_dir: Path,
        processing_mode: str,
        instructions: str | None,
        *,
        skip_existing: bool = True,
    ) -> BatchRunReport:
        """Run a batch pipeline over every file in ``input_dir`` → ``je_out/``.

        The shared, zero-persistence engine behind both folder-process (scans
        ``je_in/``) and multi-file upload (scans a temp dir of uploads). Pure
        filesystem: outputs land in ``je_out/`` via the rename formula, nothing
        is written to Neo4j.

        ``skip_existing`` controls transcription reuse: ``True`` (folder-process)
        keeps idempotent rerun semantics — a file whose ``je_out/{stem}.txt``
        already exists is not re-transcribed. ``False`` (uploads) forces fresh
        transcription, since an upload is new content that must not be shadowed
        by a stale same-stem transcript.
        """
        if processing_mode == "instructions_only":
            return await self._run_instructions_batch(input_dir, instructions)

        if processing_mode not in ("transcribe_only", "transcribe_and_instructions"):
            # Unknown mode fails before any filesystem effect — no je_out/ mkdir.
            return BatchRunReport(ok=False, message=f"Unknown processing mode: {processing_mode!r}")

        # transcribe_batch writes .txt outputs into je_out/ itself (outside
        # write_output), so the folder must exist before the batch starts.
        self.je_out_dir.mkdir(parents=True, exist_ok=True)
        return await self._run_transcription_batch(
            input_dir, processing_mode, instructions, skip_existing=skip_existing
        )

    async def _run_transcription_batch(
        self,
        input_dir: Path,
        processing_mode: str,
        instructions: str | None,
        *,
        skip_existing: bool,
    ) -> BatchRunReport:
        """The two audio modes: transcribe, then (t&i) LLM-structure each transcript."""
        if self.batch_transcription_service is None:
            return BatchRunReport(
                ok=False, message="Transcription service not available (requires FULL tier)"
            )
        # Verify the LLM branch BEFORE transcribing: transcription spends Deepgram
        # quota and writes .txt to je_out/, so a missing llm_caller must fail the
        # whole run up front, not after every file is transcribed for nothing.
        if processing_mode == "transcribe_and_instructions" and self.llm_caller is None:
            return BatchRunReport(
                ok=False, message="LLM service not available (requires INTELLIGENCE_TIER=full)"
            )
        # transcribe_and_instructions structures the transcript into ``_out.md``,
        # so the transcript must reflect the CURRENT audio — never reuse a stale
        # ``je_out/{stem}.txt`` from a prior run whose audio was since replaced
        # under the same basename. Force fresh transcription for that mode;
        # transcribe_only may reuse per the caller's ``skip_existing``
        # (folder-process reruns idempotently, uploads are always fresh).
        effective_skip = skip_existing if processing_mode == "transcribe_only" else False
        transcribe_result = await self.batch_transcription_service.transcribe_batch(
            input_dir, self.je_out_dir, skip_existing=effective_skip
        )
        if transcribe_result.is_error:
            return BatchRunReport(ok=False, message=str(transcribe_result.error))
        r = transcribe_result.value

        # No supported audio files at all (e.g. a text/PDF folder under "Transcribe
        # only") is a validation error, not a silent success.
        if r.total_files == 0:
            return BatchRunReport(ok=False, message="No supported audio files found to transcribe")

        if processing_mode == "transcribe_only":
            msg = (
                f"{r.succeeded} transcribed, {r.failed} failed, {r.skipped} skipped"
                " — results in je_out/"
            )
            is_err = r.failed > 0 and r.succeeded == 0
            return BatchRunReport(ok=not is_err, message=msg)

        # transcribe_and_instructions — LLM-structure each freshly-transcribed
        # transcript (LLM availability already verified above). This mode forces
        # skip_existing=False (see above), so every audio file yields a ``success``
        # with a current transcript — no ``skipped`` stems to worry about staleness.
        structurable_stems = {
            Path(res["name"]).stem for res in r.results if res.get("status") == "success"
        }
        llm_ok = 0
        llm_fail = 0
        for stem in structurable_stems:
            txt_path = self.je_out_dir / f"{stem}.txt"
            if not txt_path.exists():
                continue
            text = txt_path.read_text(encoding="utf-8")
            llm_result = await self._call_llm_with_instructions(text, instructions)
            if llm_result.is_error:
                self.logger.error(f"LLM failed for {stem}: {llm_result.error}")
                llm_fail += 1
            else:
                self.write_output(stem, "_out.md", llm_result.value)
                llm_ok += 1
        msg = (
            f"{r.succeeded} transcribed, {llm_ok} structured, "
            f"{r.failed + llm_fail} failed — results in je_out/"
        )
        # The deliverable is the structured _out.md; if nothing structured, this is
        # a failure even when raw transcripts were written (match the other branches).
        return BatchRunReport(ok=llm_ok > 0, message=msg)

    async def _run_instructions_batch(
        self, input_dir: Path, instructions: str | None
    ) -> BatchRunReport:
        """instructions_only: LLM-compile every text file in ``input_dir``."""
        if self.llm_caller is None:
            return BatchRunReport(
                ok=False, message="LLM service not available (requires INTELLIGENCE_TIER=full)"
            )
        if not input_dir.is_dir():
            return BatchRunReport(ok=False, message=f"Input folder not found: {input_dir}")
        text_files = sorted(
            f for f in input_dir.iterdir() if f.is_file() and f.suffix.lower() in TEXT_EXTENSIONS
        )
        if not text_files:
            return BatchRunReport(ok=False, message="No text files found to process")
        ok = 0
        fail = 0
        for text_file in text_files:
            try:
                text = text_file.read_text(encoding="utf-8")
            except Exception:  # safety-net: per-file read error
                fail += 1
                continue
            llm_result = await self._call_llm_with_instructions(text, instructions)
            if llm_result.is_error:
                self.logger.error(f"LLM failed for {text_file.name}: {llm_result.error}")
                fail += 1
            else:
                self.write_output(text_file.stem, "_out.md", llm_result.value)
                ok += 1
        msg = f"{ok} processed, {fail} failed — results in je_out/"
        return BatchRunReport(ok=ok > 0, message=msg)
