"""
Knowledge-Grounding Service
===========================

Grounds an entity to the Kus it engages, by its stored embedding: one pass, two
sources. ``EntryGroundingService`` grounds UserEntries and ``TaskGroundingService``
grounds Tasks; each subclass names its judge prompt and publishes its substance event, and
its backend names which of its entities may ground.

Candidate stage (Analog — reads stored vectors only):
    Each pending entity's STORED embedding queries the Ku vector index
    (``Neo4jVectorSearchService.find_similar_by_vector``) at
    ``GroundingConfig.threshold``. No text is re-read or re-embedded — only
    embedded entities are pending, and every embedding store writes
    ``embedding_text_hash`` beside the vector (``EmbeddingsService``, ADR-074 §8).

Judge stage (Digital — FULL tier only):
    An LLM filters candidates — "does this entity genuinely engage this Ku, or
    merely brush past it?". With no chat port, candidates write vector-only,
    eagerly — that is the sanctioned Analog quality bar. With one, a judge FAILURE
    skips the entity un-stamped (retried next pass) rather than silently degrading
    to the vector-only bar.

Eager write, no confirm gate:
    ``(entity)-[:APPLIES_KNOWLEDGE {inferred: true, confidence, grounded_at}]->(ku)``
    to a published Ku. The owner is editor, not approver: edges are visible and
    one-click removable, and a removal is recorded on the entity
    (``grounding_rejected_ku_uids``) as threshold-calibration data and never
    re-inferred.

Substance + idempotency:
    Each genuinely NEW edge publishes the source's substance event — the same
    event the owner's own link publishes. An entity that gained an edge, or lost one
    at the removal door, publishes ``EntityLinksChanged`` for its owner, as every link
    door does, so the owner's cached context reads the links the pass wrote. Existing targets are read up front and
    the write reports created-vs-matched under the entity's write-lock, so neither
    a re-run nor a race with the owner's link writer double-counts.

Re-ground trigger is HASH-based: an entity is pending while its
``grounded_text_hash`` differs from ``embedding_text_hash`` (ADR-074 §8 pattern) —
a re-embedded entity re-grounds on the next pass, an unchanged one never re-runs
(``force`` overrides).

Backend: KnowledgeGroundingBackend (one subclass per source).
See: /docs/architecture/knowledge_substance_philosophy.md
"""

from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from core.events import publish_event
from core.events.link_events import EntityLinksChanged
from core.models.type_hints import UserUID
from core.prompts import PROMPT_REGISTRY
from core.utils.llm_json import parse_json_reply
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports.grounding_protocols import KnowledgeGroundingBackendOperations
    from core.ports.infrastructure_protocols import EventBusOperations
    from core.ports.llm_protocols import ChatMessage
    from core.ports.query_types import GroundingSourceRow
    from core.services.llm_service import LLMService
    from core.services.neo4j_vector_search_service import Neo4jVectorSearchService

#: Bumping this re-grounds nothing by itself (freshness is hash-based) but is
#: stamped on every pass so a future semantic change can target old passes.
GROUNDING_VERSION = 1


@dataclass(frozen=True)
class GroundingConfig:
    """Knobs for the candidate threshold and the LLM judge.

    ``threshold`` starts at the empirically derived 0.72 "related concepts"
    knob (``ku_similar_min_score``) — pairs above it are near-duplicate
    concept territory, which is exactly what "this entity engages this Ku"
    wants. It is calibrated over time by edge removals (each removal logs
    the removed edge's confidence).
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
    """One Ku the entity's vector matched above threshold.

    ``verdict is None`` = unjudged (no chat port); True/False = judge decision.
    """

    ku_uid: str
    ku_title: str
    similarity: float
    verdict: bool | None
    rationale: str | None


@dataclass(frozen=True)
class GroundingOutcome:
    """One entity's pass: what matched, what was (or would be) written."""

    source_uid: str
    source_title: str
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

    outcomes: tuple[GroundingOutcome, ...]
    scanned: int
    with_writes: int
    edges_written: int
    failed: int
    applied: bool
    judged: bool


class KnowledgeGroundingService(ABC):
    """Candidates → optional LLM judge → eager provenance-stamped edges, for one source."""

    #: The source's name in logs and error features ("entry", "task").
    source: ClassVar[str]
    #: The ``PROMPT_REGISTRY`` id of the source's judge prompt.
    judge_template: ClassVar[str]

    def __init__(
        self,
        backend: KnowledgeGroundingBackendOperations,
        vector_search: Neo4jVectorSearchService | None,
        event_bus: EventBusOperations | None = None,
        llm_service: LLMService | None = None,
        config: GroundingConfig | None = None,
    ) -> None:
        """
        Args:
            backend: Pending reads + provenance edge writes for this source.
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
        self.config = config or GroundingConfig()
        self.logger = get_logger(f"skuel.services.{self.source}_grounding")

    @property
    def judge_available(self) -> bool:
        """True when the multi-provider caller is wired (FULL tier)."""
        return self._llm is not None and self._llm.caller is not None

    # ------------------------------------------------------------------
    # The source's two parts
    # ------------------------------------------------------------------

    @abstractmethod
    def judge_fields(self, row: GroundingSourceRow, excerpt: str) -> dict[str, str]:
        """The judge prompt's fields naming the entity: its title and excerpt."""

    @abstractmethod
    async def _publish_substance(self, row: GroundingSourceRow, ku_uid: str) -> None:
        """Publish the event that credits a NEW inferred edge, the one the owner's link publishes.

        Called only with an event bus wired.
        """

    # ------------------------------------------------------------------
    # The pass
    # ------------------------------------------------------------------

    async def ground_pending(
        self,
        user_uid: UserUID | None = None,
        *,
        force: bool = False,
        apply: bool = True,
        source_uid: str | None = None,
        owner_of: str | None = None,
    ) -> Result[GroundingRunReport]:
        """Ground every pending entity (optionally scoped to one user, or one entity).

        ``owner_of`` scopes to every pending entity of the owner of the entity it
        names: a pass started for one entity also retries its owner's entities whose
        last pass failed (un-stamped, so still pending).

        Backend: KnowledgeGroundingBackend.get_pending. ``apply=False`` is the dry
        run: the full pipeline runs (including the judge on FULL) but nothing is
        written, stamped, or published — the report shows exactly what
        ``apply=True`` would do. An entity whose judge call fails is reported with
        ``error`` and left un-stamped so the next pass retries it; other entities
        still land.
        """
        if self._vector_search is None:
            return Result.fail(
                Errors.unavailable(
                    feature=f"{self.source}_grounding",
                    reason="Vector search service is not wired — grounding needs "
                    "the Ku vector index.",
                    operation="ground_pending",
                )
            )

        pending_result = await self.backend.get_pending(
            user_uid=user_uid, force=force, source_uid=source_uid, owner_of=owner_of
        )
        if pending_result.is_error:
            return Result.fail(pending_result)
        pending = pending_result.value

        semaphore = asyncio.Semaphore(self.config.judge_concurrency)

        async def process(row: GroundingSourceRow) -> GroundingOutcome:
            async with semaphore:
                return await self._ground_one(row, apply=apply)

        outcomes = list(await asyncio.gather(*(process(row) for row in pending)))

        report = GroundingRunReport(
            outcomes=tuple(outcomes),
            scanned=len(pending),
            with_writes=sum(1 for o in outcomes if o.written and o.error is None),
            edges_written=sum(len(o.written) for o in outcomes if o.error is None),
            failed=sum(1 for o in outcomes if o.error is not None),
            applied=apply,
            judged=self.judge_available,
        )
        if pending:
            self.logger.info(
                f"Grounding pass ({self.source}, {'applied' if apply else 'dry-run'}): "
                f"{report.edges_written} edge(s) across {report.with_writes}/"
                f"{report.scanned} ({report.failed} failed, "
                f"judge={'on' if report.judged else 'off'})"
            )
        return Result.ok(report)

    async def _ground_one(self, row: GroundingSourceRow, *, apply: bool) -> GroundingOutcome:
        """One entity: vector candidates → exclusions → judge → eager writes + stamp."""
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
            judge_result = await self._judge(row, candidates)
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
                    # An existing edge (race), or the Ku is gone or a draft —
                    # no substance event.
                    skipped_existing += 1
                    continue
                written.append(candidate)
                if self._event_bus is not None:
                    await self._publish_substance(row, candidate.ku_uid)
            if written and self._event_bus is not None:
                await publish_event(
                    self._event_bus,
                    EntityLinksChanged(user_uid=UserUID(row["user_uid"]), entity_uid=row["uid"]),
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

        return GroundingOutcome(
            source_uid=row["uid"],
            source_title=row["title"],
            user_uid=row["user_uid"],
            written=tuple(written),
            rejected_by_judge=rejected_by_judge,
            skipped_existing=skipped_existing,
            skipped_rejected=skipped_rejected,
            judged=judged,
        )

    @staticmethod
    def _failed_outcome(
        row: GroundingSourceRow,
        error: str,
        skipped_existing: int = 0,
        skipped_rejected: int = 0,
    ) -> GroundingOutcome:
        """Per-entity fail-soft record — other entities in the pass still land."""
        return GroundingOutcome(
            source_uid=row["uid"],
            source_title=row["title"],
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

    async def _judge(
        self, row: GroundingSourceRow, candidates: list[GroundingCandidate]
    ) -> Result[list[GroundingCandidate]]:
        """LLM-filter one entity's candidates: genuine engagement vs brush-past.

        Returns the candidates with verdict/rationale filled in. A transport
        error or malformed response fails the whole entity (the caller skips it
        un-stamped) — a half-judged entity must not write the unjudged half.
        """
        cfg = self.config
        candidates_block = "\n".join(
            f'{index}. "{c.ku_title}" (similarity {c.similarity:.2f})'
            for index, c in enumerate(candidates, start=1)
        )
        excerpt = " ".join(row["content"].split())[: cfg.excerpt_max_chars]
        prompt = PROMPT_REGISTRY.render(
            self.judge_template,
            candidates_block=candidates_block,
            **self.judge_fields(row, excerpt or "(no content)"),
        )

        caller = self._llm.caller if self._llm is not None else None
        if caller is None:  # pragma: no cover — guarded by the caller
            return Result.ok(candidates)

        messages: list[ChatMessage] = [{"role": "user", "content": prompt}]
        completion_result = await caller.complete(
            messages,
            model=cfg.judge_model,
            temperature=0.1,
            max_tokens=cfg.judge_max_tokens,
        )
        if completion_result.is_error:
            return Result.fail(completion_result)

        try:
            items = parse_json_reply(completion_result.value.text)
            if not isinstance(items, list):
                raise TypeError("judge output is not a JSON array")
        except (json.JSONDecodeError, TypeError) as e:
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
            # and write an edge the judge rejected. A non-bool verdict is
            # dropped, so the coverage check below fails the entity.
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
    # Removal (the "editor, not approver" half)
    # ------------------------------------------------------------------

    async def remove(self, source_uid: str, ku_uid: str, user_uid: UserUID) -> Result[bool]:
        """Remove one inferred ``APPLIES_KNOWLEDGE`` edge from an entity the user OWNS.

        Backend: KnowledgeGroundingBackend.remove_grounded_edge — the ownership
        anchor lives in the delete query itself, so a non-owned entity, an absent
        edge, or a link the owner made returns False and the route 404s. The
        removal is recorded on the entity so no future pass re-infers the pair, the
        owner's cached context is told (``EntityLinksChanged``), and the removed edge's
        confidence is logged as threshold-calibration data.
        """
        result = await self.backend.remove_grounded_edge(source_uid, ku_uid, user_uid)
        if result.is_error:
            return Result.fail(result)
        removal = result.value
        if removal is None:
            return Result.ok(False)
        if self._event_bus is not None:
            await publish_event(
                self._event_bus,
                EntityLinksChanged(user_uid=user_uid, entity_uid=source_uid),
                self.logger,
            )
        self.logger.info(
            f"Grounding removal (calibration, {self.source}): {source_uid} -/-> "
            f"{removal['ku_uid']} (confidence={removal['confidence']}, "
            f"threshold={self.config.threshold})"
        )
        return Result.ok(True)
