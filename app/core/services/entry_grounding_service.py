"""
Entry-Grounding Service
=======================

Entry-Enrichment PR 3: grounds ``pipeline: knowledge`` UserEntries to Kus so
the substance entries-channel and ZPD's ``entry_application`` signal light up
for Mike's "teach SKUEL about me" notes (knowledge/ and je_pro/ doors alike).

Candidate stage (Analog — CORE tier, no API key):
    Each pending entry's STORED embedding queries the Ku vector index
    (``Neo4jVectorSearchService.find_similar_by_vector``) at the 0.72
    "related concepts" knob (#598). No text is re-read or re-embedded —
    PR 2 guaranteed every knowledge entry carries ``embedding`` +
    ``embedding_text_hash``.

Judge stage (Digital — FULL tier only):
    An LLM filters candidates — "does this entry genuinely engage this Ku,
    or merely brush past it?". On CORE (no chat port) candidates write
    vector-only, eagerly — that is the sanctioned Analog quality bar. On
    FULL, a judge FAILURE skips the entry un-stamped (retried next pass)
    rather than silently degrading to the vector-only bar.

Eager write (Mike's ruling 2026-07-11 — no confirm gate):
    ``(entry)-[:APPLIES_KNOWLEDGE {inferred: true, confidence, grounded_at}]->(ku)``.
    The user is editor, not approver: edges are visible and one-click
    removable (route in this PR, UI in PR 4); removals are recorded on the
    entry (``grounding_rejected_ku_uids``) as threshold-calibration data and
    are never re-inferred.

Substance + idempotency:
    Each genuinely NEW edge publishes ``KnowledgeReflectedInEntry`` — the
    same writer-agnostic event the EXTRACT_ACTIVITIES pipeline publishes
    (handler: KuBackend.increment_substance with PathStep fan-out,
    0.07/entry credit). Existing targets are read up front and the write
    reports created-vs-matched, so neither a re-run nor a race double-counts.

Re-ground trigger is HASH-based: an entry is pending while its
``grounded_text_hash`` differs from ``embedding_text_hash`` (ADR-074 §8
pattern) — a re-embedded entry re-grounds on the next pass, an unchanged one
never re-runs (``force`` overrides).

Backend: EntryGroundingBackend. Triggers: post-sync pass in the vault sync
doors + ``scripts/ground_knowledge_entries.py`` backfill (dry-run default).
See: /docs/architecture/knowledge_substance_philosophy.md
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.events import publish_event
from core.events.knowledge_substance_events import KnowledgeReflectedInEntry
from core.models.type_hints import UserUID
from core.prompts import PROMPT_REGISTRY
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports.infrastructure_protocols import EventBusOperations
    from core.ports.llm_protocols import ChatMessage
    from core.ports.query_types import GroundingEntryRow
    from core.ports.user_entry_protocols import EntryGroundingBackendOperations
    from core.services.llm_service import LLMService
    from core.services.neo4j_vector_search_service import Neo4jVectorSearchService

#: Bumping this re-grounds nothing by itself (freshness is hash-based) but is
#: stamped on every pass so a future semantic change can target old passes.
GROUNDING_VERSION = 1


@dataclass(frozen=True)
class EntryGroundingConfig:
    """Knobs for the candidate threshold and the LLM judge.

    ``threshold`` starts at the empirically derived 0.72 "related concepts"
    knob (#598) — pairs above it are near-duplicate concept territory, which
    is exactly what "this entry engages this Ku" wants. It is calibrated over
    time by edge removals (each removal logs the removed edge's confidence).
    """

    threshold: float = 0.72
    max_candidates: int = 8
    # Classification workload — fast/cheap model (PrereqSuggestionService precedent).
    judge_model: str = "gpt-4o-mini"
    judge_max_tokens: int = 1200
    judge_concurrency: int = 4
    excerpt_max_chars: int = 1500
    summary_max_chars: int = 280


@dataclass(frozen=True)
class GroundingCandidate:
    """One Ku the entry's vector matched above threshold.

    ``verdict is None`` = unjudged (CORE tier); True/False = judge decision.
    """

    ku_uid: str
    ku_title: str
    similarity: float
    verdict: bool | None
    rationale: str | None


@dataclass(frozen=True)
class EntryGroundingOutcome:
    """One entry's pass: what matched, what was (or would be) written."""

    entry_uid: str
    entry_title: str
    user_uid: str
    written: tuple[GroundingCandidate, ...]
    rejected_by_judge: tuple[GroundingCandidate, ...]
    skipped_existing: int
    skipped_rejected: int
    judged: bool
    error: str | None = None


@dataclass(frozen=True)
class GroundingRunReport:
    """Outcome of one ``ground_pending`` run (dry or applied)."""

    outcomes: tuple[EntryGroundingOutcome, ...]
    entries_scanned: int
    entries_with_writes: int
    edges_written: int
    entries_failed: int
    applied: bool
    judged: bool


class EntryGroundingService:
    """Candidates → optional LLM judge → eager provenance-stamped edges."""

    def __init__(
        self,
        backend: EntryGroundingBackendOperations,
        vector_search: Neo4jVectorSearchService | None,
        event_bus: EventBusOperations | None = None,
        llm_service: LLMService | None = None,
        config: EntryGroundingConfig | None = None,
    ) -> None:
        """
        Args:
            backend: Pending-entry reads + provenance edge writes.
            vector_search: Ku vector-index lookups (``find_similar_by_vector``
                reads stored vectors only — no embeddings client needed, so
                CORE composes a client-less instance).
            event_bus: Substance-event publisher; ``None`` skips publishing
                (edges still write — substance can be recounted, edges can't).
            llm_service: FULL-tier judge; ``None`` on CORE — candidates write
                vector-only, eagerly.
            config: Threshold/judge knobs.
        """
        self.backend = backend
        self._vector_search = vector_search
        self._event_bus = event_bus
        self._llm = llm_service
        self.config = config or EntryGroundingConfig()
        self.logger = get_logger("skuel.services.entry_grounding")

    @property
    def judge_available(self) -> bool:
        """True when an LLM chat port is wired (FULL tier)."""
        return self._llm is not None and self._llm.chat_port is not None

    # ------------------------------------------------------------------
    # The pass
    # ------------------------------------------------------------------

    async def ground_pending(
        self,
        user_uid: UserUID | None = None,
        *,
        force: bool = False,
        apply: bool = True,
    ) -> Result[GroundingRunReport]:
        """Ground every pending knowledge entry (optionally scoped to one user).

        Backend: EntryGroundingBackend.get_pending_entries. ``apply=False`` is
        the dry run: the full pipeline runs (including the judge on FULL) but
        nothing is written, stamped, or published — the report shows exactly
        what ``apply=True`` would do. An entry whose judge call fails is
        reported with ``error`` and left un-stamped so the next pass retries
        it; other entries still land.
        """
        if self._vector_search is None:
            return Result.fail(
                Errors.unavailable(
                    feature="entry_grounding",
                    reason="Vector search service is not wired — grounding needs "
                    "the Ku vector index.",
                    operation="ground_pending",
                )
            )

        pending_result = await self.backend.get_pending_entries(user_uid=user_uid, force=force)
        if pending_result.is_error:
            return Result.fail(pending_result)
        pending = pending_result.value

        semaphore = asyncio.Semaphore(self.config.judge_concurrency)

        async def process(row: GroundingEntryRow) -> EntryGroundingOutcome:
            async with semaphore:
                return await self._ground_entry(row, apply=apply)

        outcomes = list(await asyncio.gather(*(process(row) for row in pending)))

        report = GroundingRunReport(
            outcomes=tuple(outcomes),
            entries_scanned=len(pending),
            entries_with_writes=sum(1 for o in outcomes if o.written and o.error is None),
            edges_written=sum(len(o.written) for o in outcomes if o.error is None),
            entries_failed=sum(1 for o in outcomes if o.error is not None),
            applied=apply,
            judged=self.judge_available,
        )
        if pending:
            self.logger.info(
                f"Grounding pass ({'applied' if apply else 'dry-run'}): "
                f"{report.edges_written} edge(s) across {report.entries_with_writes}/"
                f"{report.entries_scanned} entries "
                f"({report.entries_failed} failed, judge={'on' if report.judged else 'off'})"
            )
        return Result.ok(report)

    async def _ground_entry(self, row: GroundingEntryRow, *, apply: bool) -> EntryGroundingOutcome:
        """One entry: vector candidates → exclusions → judge → eager writes + stamp."""
        if self._vector_search is None:  # pragma: no cover — guarded by ground_pending
            return self._failed_outcome(row, "vector search unavailable")
        similar_result = await self._vector_search.find_similar_by_vector(
            label="Ku",
            embedding=row["embedding"],
            limit=self.config.max_candidates,
            min_score=self.config.threshold,
        )
        if similar_result.is_error:
            return self._failed_outcome(row, f"vector search failed: {similar_result.error}")

        applied = set(row["applied_ku_uids"])
        rejected = set(row["rejected_ku_uids"])
        skipped_existing = 0
        skipped_rejected = 0
        candidates: list[GroundingCandidate] = []
        for item in similar_result.value:
            ku_uid = str(item["node"].get("uid") or "")
            if not ku_uid:
                continue
            if ku_uid in applied:
                skipped_existing += 1
                continue
            if ku_uid in rejected:
                skipped_rejected += 1
                continue
            candidates.append(
                GroundingCandidate(
                    ku_uid=ku_uid,
                    ku_title=str(item["node"].get("title") or ku_uid),
                    similarity=round(float(item["score"]), 4),
                    verdict=None,
                    rationale=None,
                )
            )

        judged = self.judge_available
        rejected_by_judge: tuple[GroundingCandidate, ...] = ()
        to_write = candidates
        if judged and candidates:
            judge_result = await self._judge_entry(row, candidates)
            if judge_result.is_error:
                # Conservative: no writes, no stamp — the next pass retries.
                return self._failed_outcome(
                    row,
                    f"judge failed: {judge_result.error}",
                    skipped_existing=skipped_existing,
                    skipped_rejected=skipped_rejected,
                )
            judged_candidates = judge_result.value
            to_write = [c for c in judged_candidates if c.verdict is True]
            rejected_by_judge = tuple(c for c in judged_candidates if c.verdict is not True)

        written: list[GroundingCandidate] = []
        if apply:
            for candidate in to_write:
                write_result = await self.backend.write_applies_knowledge(
                    row["uid"], candidate.ku_uid, candidate.similarity
                )
                if write_result.is_error:
                    return self._failed_outcome(
                        row,
                        f"edge write failed ({candidate.ku_uid}): {write_result.error}",
                        skipped_existing=skipped_existing,
                        skipped_rejected=skipped_rejected,
                    )
                if not write_result.value:
                    # Matched an existing edge (race) — no substance event.
                    skipped_existing += 1
                    continue
                written.append(candidate)
                if self._event_bus is not None:
                    await publish_event(
                        self._event_bus,
                        KnowledgeReflectedInEntry(
                            knowledge_uid=candidate.ku_uid,
                            entry_uid=row["uid"],
                            user_uid=UserUID(row["user_uid"]),
                        ),
                        self.logger,
                    )
            stamp_result = await self.backend.stamp_grounded(
                row["uid"], row["embedding_text_hash"], GROUNDING_VERSION
            )
            if stamp_result.is_error:
                # Edges landed; a missing stamp only means a redundant (and
                # idempotent) re-pass next time — report, don't fail.
                self.logger.warning(
                    f"Grounded {row['uid']} but failed to stamp: {stamp_result.error}"
                )
        else:
            written = list(to_write)

        return EntryGroundingOutcome(
            entry_uid=row["uid"],
            entry_title=row["title"],
            user_uid=row["user_uid"],
            written=tuple(written),
            rejected_by_judge=rejected_by_judge,
            skipped_existing=skipped_existing,
            skipped_rejected=skipped_rejected,
            judged=judged,
        )

    @staticmethod
    def _failed_outcome(
        row: GroundingEntryRow,
        error: str,
        skipped_existing: int = 0,
        skipped_rejected: int = 0,
    ) -> EntryGroundingOutcome:
        """Per-entry fail-soft record — other entries in the pass still land."""
        return EntryGroundingOutcome(
            entry_uid=row["uid"],
            entry_title=row["title"],
            user_uid=row["user_uid"],
            written=(),
            rejected_by_judge=(),
            skipped_existing=skipped_existing,
            skipped_rejected=skipped_rejected,
            judged=False,
            error=error,
        )

    # ------------------------------------------------------------------
    # Judge stage (FULL tier)
    # ------------------------------------------------------------------

    async def _judge_entry(
        self, row: GroundingEntryRow, candidates: list[GroundingCandidate]
    ) -> Result[list[GroundingCandidate]]:
        """LLM-filter one entry's candidates: genuine engagement vs brush-past.

        Returns the candidates with verdict/rationale filled in. A transport
        error or malformed response fails the whole entry (the caller skips it
        un-stamped) — a half-judged entry must not write the unjudged half.
        """
        cfg = self.config
        candidates_block = "\n".join(
            f'{index}. "{c.ku_title}" (similarity {c.similarity:.2f})'
            for index, c in enumerate(candidates, start=1)
        )
        excerpt = " ".join(row["content"].split())[: cfg.excerpt_max_chars]
        prompt = PROMPT_REGISTRY.render(
            "entry_ku_grounding_judge",
            entry_title=row["title"],
            entry_excerpt=excerpt or "(no content)",
            candidates_block=candidates_block,
        )

        chat_port = self._llm.chat_port if self._llm is not None else None
        if chat_port is None:  # pragma: no cover — guarded by the caller
            return Result.ok(candidates)

        messages: list[ChatMessage] = [{"role": "user", "content": prompt}]
        completion_result = await chat_port.complete(
            messages,
            model=cfg.judge_model,
            temperature=0.1,
            max_tokens=cfg.judge_max_tokens,
        )
        if completion_result.is_error:
            return Result.fail(completion_result)

        try:
            raw = completion_result.value.text
            if "```" in raw:
                raw = raw.split("```")[1]
                raw = raw.removeprefix("json")
            items = json.loads(raw.strip())
            if not isinstance(items, list):
                raise TypeError("judge output is not a JSON array")
        except (json.JSONDecodeError, TypeError, IndexError) as e:
            return Result.fail(
                Errors.integration(
                    service="llm",
                    message=f"Grounding judge returned malformed JSON for {row['uid']}: {e}",
                )
            )

        verdicts: dict[int, tuple[bool, str]] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                index = int(item.get("index", 0))
            except TypeError, ValueError:
                continue
            # Strict bool — truthiness would coerce a string "false" to True
            # and write an edge the judge rejected (Codex #610 P2). A non-bool
            # verdict is dropped, so the coverage check below fails the entry.
            engages = item.get("engages")
            if not isinstance(engages, bool):
                continue
            if not (1 <= index <= len(candidates)) or index in verdicts:
                continue
            verdicts[index] = (engages, " ".join(str(item.get("rationale", "")).split()))

        if len(verdicts) != len(candidates):
            return Result.fail(
                Errors.integration(
                    service="llm",
                    message=f"Grounding judge covered {len(verdicts)}/{len(candidates)} "
                    f"candidates for {row['uid']}",
                )
            )

        judged: list[GroundingCandidate] = []
        for index, candidate in enumerate(candidates, start=1):
            engages, rationale = verdicts[index]
            judged.append(
                GroundingCandidate(
                    ku_uid=candidate.ku_uid,
                    ku_title=candidate.ku_title,
                    similarity=candidate.similarity,
                    verdict=engages,
                    rationale=rationale or None,
                )
            )
        return Result.ok(judged)

    # ------------------------------------------------------------------
    # Removal (the "editor, not approver" half — route here, UI in PR 4)
    # ------------------------------------------------------------------

    async def remove(self, entry_uid: str, ku_uid: str, user_uid: UserUID) -> Result[bool]:
        """Remove one ``APPLIES_KNOWLEDGE`` edge from an entry the user OWNS.

        Backend: EntryGroundingBackend.remove_grounded_edge — the ownership
        anchor lives in the delete query itself, so a non-owned entry (or an
        absent edge) returns False and the route 404s. The removal is recorded
        on the entry so no future pass re-infers the pair, and the removed
        edge's confidence is logged as threshold-calibration data.
        """
        result = await self.backend.remove_grounded_edge(entry_uid, ku_uid, user_uid)
        if result.is_error:
            return Result.fail(result)
        removal = result.value
        if removal is None:
            return Result.ok(False)
        self.logger.info(
            f"Grounding removal (calibration): {entry_uid} -/-> {removal['ku_uid']} "
            f"(inferred={removal['inferred']}, confidence={removal['confidence']}, "
            f"threshold={self.config.threshold})"
        )
        return Result.ok(True)
