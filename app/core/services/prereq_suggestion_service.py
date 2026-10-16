"""
Prerequisite-Edge Suggestion Service
====================================

Discovery Analytics PR 4: candidates → LLM judge → admin queue → a ready Edge
YAML file per row, which the admin copies into the content vault. The app
writes nothing: curriculum is authored in the vault (ADR-091 N3). Reject is
stateless: a rejected suggestion simply reappears on regeneration.
Suggestions are EPHEMERAL — computed on demand, never persisted as nodes.

Candidate stage (Analog — works on CORE if embeddings exist on Ku nodes):
    Pairwise cosine over stored Ku embeddings, kept in a MID-similarity band.
    Phase A (2026-07-10) proved the high-similarity premise WRONG for
    prerequisites: the 8 authored PREREQUISITE_FOR pairs sit at cosine
    0.32-0.57, so the 0.72 "related concepts" knob recovers 0/8. A 0.40
    floor admits 6/8 (the recall ceiling); 0.72 caps the band because pairs
    above it are near-duplicate "related concepts" (PR 3 chip territory),
    not learning dependencies. Pairs already connected by ANY Ku↔Ku edge —
    or transitively covered by an authored directed path — are excluded.

Judge stage (Digital — FULL tier only):
    An LLM classifies each candidate pair as {prereq A→B | prereq B→A |
    related | skip} with a one-line rationale. On CORE the queue degrades to
    undirected pairs and the admin chooses relation + direction himself
    (Analog-complete). Phase A found NO structural direction heuristic beats
    a coin-flip in this corpus, which is why direction is judged, not derived.

Ready-file stage (pure):
    ``ready_edge_files`` renders, for each way to record a pair, the Edge
    YAML file in the authored format (``source: inferred-approved``). The
    admin copies the chosen one into the vault's ``edges/``; the edge lands
    in the graph on the next content-vault sync.

Backend: PrereqCandidateBackend (read-only).
See: /docs/roadmap/done/SEMANTIC_ANALYSIS_ROADMAP.md
"""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from core.models.relationship_names import RelationshipName
from core.prompts import PROMPT_REGISTRY
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.vector_math import dot, l2_normalize

if TYPE_CHECKING:
    from core.ports.curriculum_protocols import PrereqSuggestionBackendOperations
    from core.ports.llm_protocols import ChatMessage
    from core.ports.query_types import KuEmbeddingRow
    from core.services.llm_service import LLMService


# =============================================================================
# Verdicts + the ways to record a pair
# =============================================================================


class JudgeVerdict(StrEnum):
    """LLM-judge classification of one candidate pair."""

    PREREQ_A_TO_B = "prereq_a_to_b"
    PREREQ_B_TO_A = "prereq_b_to_a"
    RELATED = "related"
    SKIP = "skip"


class EdgeChoice(StrEnum):
    """One way to record a suggested pair (A/B as the queue shows them)."""

    PREREQ_A_TO_B = "prereq_a_to_b"
    PREREQ_B_TO_A = "prereq_b_to_a"
    RELATED = "related"
    COMPLEMENTARY = "complementary"


#: Each choice → (swap A/B into from/to, relationship). Direction is expressed
#: by from/to ordering, so both prereq choices are PREREQUISITE_FOR; the
#: symmetric pair covers "connected but unordered".
_EDGE_CHOICES: dict[EdgeChoice, tuple[bool, RelationshipName]] = {
    EdgeChoice.PREREQ_A_TO_B: (False, RelationshipName.PREREQUISITE_FOR),
    EdgeChoice.PREREQ_B_TO_A: (True, RelationshipName.PREREQUISITE_FOR),
    EdgeChoice.RELATED: (False, RelationshipName.RELATED_TO),
    EdgeChoice.COMPLEMENTARY: (False, RelationshipName.COMPLEMENTARY_TO),
}

#: Filename token per relationship a choice records
#: (edge_ku.mind.attention__prereq__ku.mind.labeling.md).
_REL_FILENAME_TOKENS: dict[RelationshipName, str] = {
    RelationshipName.PREREQUISITE_FOR: "prereq",
    RelationshipName.RELATED_TO: "related",
    RelationshipName.COMPLEMENTARY_TO: "complements",
}

#: Symmetric relationships carry no direction — from/to is canonicalized to
#: sorted-UID order, so the same pair always yields the same file whichever
#: A/B order a generate run happened to emit (a reverse duplicate would be a
#: second file for one edge).
_SYMMETRIC_RELATIONSHIPS: frozenset[RelationshipName] = frozenset(
    {RelationshipName.RELATED_TO, RelationshipName.COMPLEMENTARY_TO}
)


# =============================================================================
# Data shapes (ephemeral — computed per generate run, held in the page)
# =============================================================================


@dataclass(frozen=True)
class PrereqSuggestionConfig:
    """Knobs for the candidate band and the LLM judge.

    Band values are empirical (Phase A, 2026-07-10): authored prereq pairs
    sit at cosine 0.32-0.57 over 121 Kus; 0.40 admits 6/8 authored pairs,
    0.72 hands off to the PR 3 "related concepts" lens. ``per_ku_cap`` +
    ``max_pairs`` keep the LLM batch bounded (~200 pairs).

    Measured budget/recall trade-off (PR 4 probe, 2026-07-10): the 0.40-0.72
    band holds ~835 pairs on this corpus, and authored prereqs scatter deep
    into it (per-Ku neighbour ranks 1-12) — a 200-pair budget admits 3/6
    in-band authored pairs whichever cap policy is used (similarity-desc cut
    beat rank-based and mutual-top-K cuts empirically). Reaching the full
    6/8 ceiling means judging the whole band: raise ``max_pairs`` (and
    ``per_ku_cap``) if a bigger queue is ever worth the review load.
    """

    band_low: float = 0.40
    band_high: float = 0.72
    per_ku_cap: int = 4
    max_pairs: int = 200
    judge_batch_size: int = 20
    judge_concurrency: int = 4
    # Classification workload — the fast/cheap model is the right tool
    # (UnifiedLLMCaller precedent); the recall probe validates quality.
    judge_model: str = "gpt-4o-mini"
    judge_max_tokens: int = 2000
    summary_max_chars: int = 280


@dataclass(frozen=True)
class PrereqCandidate:
    """One undirected mid-band Ku pair awaiting judgement (A/B order arbitrary)."""

    a_uid: str
    a_title: str
    a_summary: str
    b_uid: str
    b_title: str
    b_summary: str
    similarity: float


@dataclass(frozen=True)
class PrereqSuggestion:
    """One queue row. ``verdict is None`` = unjudged (CORE tier — admin decides)."""

    a_uid: str
    a_title: str
    b_uid: str
    b_title: str
    similarity: float
    verdict: JudgeVerdict | None
    rationale: str | None


@dataclass(frozen=True)
class PrereqSuggestionRun:
    """Outcome of one on-demand generation run (nothing is persisted)."""

    suggestions: tuple[PrereqSuggestion, ...]
    candidate_count: int
    judged: bool
    skipped_by_judge: int
    judge_failures: int


# =============================================================================
# Pure helpers (Edge YAML rendering — filesystem I/O stays in the adapter)
# =============================================================================


def _uid_slug(uid: str) -> str:
    """Filename slug for a Ku UID: the whole uid, any character outside
    ``[a-z0-9._-]`` replaced by ``-``.

    The whole uid, not its last segment: ``ku.math.attention`` and
    ``ku.sel.attention`` are different Kus, and a shared filename would have
    the admin's copy overwrite the other edge's file in the vault.
    """
    return "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in uid.lower()) or "ku"


def edge_filename(from_uid: str, to_uid: str, relationship: RelationshipName) -> str:
    """``edge_{from-uid}__{rel-token}__{to-uid}.md`` — one name per edge.

    ``__`` separates the parts because an authored uid never carries it (its
    segments join with ``.`` and ``-``).
    """
    token = _REL_FILENAME_TOKENS[relationship]
    return f"edge_{_uid_slug(from_uid)}__{token}__{_uid_slug(to_uid)}.md"


def _comment_line(text: str) -> str:
    """One-line YAML comment — newlines collapsed so a rationale can never
    inject frontmatter keys into the file."""
    return "# " + " ".join(text.split())


def render_edge_yaml(
    from_uid: str,
    to_uid: str,
    relationship: RelationshipName,
    rationale: str | None = None,
) -> str:
    """Render the exact authored Edge YAML format.

    UIDs are written in stored (dot) form (authored = stored). Matches the
    vault edge-file shape (comment header, ``type: Edge``, from/to/
    relationship) plus the ``source: inferred-approved`` provenance stamp: the
    app suggested the edge and the admin approved it by copying the file in.
    """
    lines = [
        "---",
        _comment_line(f"Edge: {from_uid} -> {relationship.value} -> {to_uid}"),
    ]
    if rationale and rationale.strip():
        lines.append(_comment_line(rationale))
    lines += [
        "type: Edge",
        "",
        f"from: {from_uid}",
        f"to: {to_uid}",
        f"relationship: {relationship.value}",
        "",
        "source: inferred-approved",
        "",
        "---",
        "",
    ]
    return "\n".join(lines)


@dataclass(frozen=True)
class ReadyEdgeFile:
    """One Edge YAML file ready to copy into the content vault's ``edges/``."""

    choice: EdgeChoice
    filename: str
    content: str


def ready_edge_files(suggestion: PrereqSuggestion) -> tuple[ReadyEdgeFile, ...]:
    """The Edge YAML file for each way to record a suggested pair, in ``EdgeChoice`` order.

    A symmetric relationship's from/to is sorted, so the file is the same
    whichever A/B order the run emitted.
    """
    files = []
    for choice, (swap, relationship) in _EDGE_CHOICES.items():
        from_uid, to_uid = (
            (suggestion.b_uid, suggestion.a_uid) if swap else (suggestion.a_uid, suggestion.b_uid)
        )
        if relationship in _SYMMETRIC_RELATIONSHIPS:
            from_uid, to_uid = sorted((from_uid, to_uid))
        files.append(
            ReadyEdgeFile(
                choice=choice,
                filename=edge_filename(from_uid, to_uid, relationship),
                content=render_edge_yaml(
                    from_uid, to_uid, relationship, rationale=suggestion.rationale
                ),
            )
        )
    return tuple(files)


# =============================================================================
# Service
# =============================================================================


class PrereqSuggestionService:
    """Candidates → optional LLM judge. Read-only: it writes nothing anywhere."""

    def __init__(
        self,
        backend: PrereqSuggestionBackendOperations,
        llm_service: LLMService | None = None,
        config: PrereqSuggestionConfig | None = None,
    ) -> None:
        """
        Args:
            backend: Read-only Ku embedding/edge reads.
            llm_service: FULL-tier judge; ``None`` on CORE — the queue then
                serves undirected pairs for the admin to classify himself.
            config: Band/judge knobs (defaults are the Phase A derivation).
        """
        self.backend = backend
        self._llm = llm_service
        self._config = config or PrereqSuggestionConfig()
        self.logger = get_logger("skuel.services.prereq_suggestions")

    @property
    def judge_available(self) -> bool:
        """True when the multi-provider caller is wired (FULL tier) — the queue says which mode."""
        return self._llm is not None and self._llm.caller is not None

    # ------------------------------------------------------------------
    # Candidate stage
    # ------------------------------------------------------------------

    async def generate_candidates(self) -> Result[list[PrereqCandidate]]:
        """Mid-band, unedged, non-transitively-covered Ku pairs, capped per Ku.

        Backend: PrereqCandidateBackend.get_kus_with_embeddings /
        get_ku_ku_edges. Fails soft with a clear message when no Ku
        embeddings exist (fresh CORE install — embeddings are generated on
        FULL tier).
        """
        kus_result = await self.backend.get_kus_with_embeddings()
        if kus_result.is_error:
            return Result.fail(kus_result)
        kus = self._drop_stale_dimensions(kus_result.value)
        if not kus:
            return Result.fail(
                Errors.business(
                    rule="no_ku_embeddings",
                    message="No Ku embeddings available — candidate generation needs "
                    "stored embeddings (generated on FULL tier; run the embedding "
                    "backfill or a FULL-tier sync first).",
                )
            )

        edges_result = await self.backend.get_ku_ku_edges()
        if edges_result.is_error:
            return Result.fail(edges_result)

        adjacency: dict[str, set[str]] = {}
        for edge in edges_result.value:
            adjacency.setdefault(edge["from_uid"], set()).add(edge["to_uid"])
        reachable = {uid: self._reachable_from(uid, adjacency) for uid in adjacency}

        return Result.ok(self._band_pairs(kus, reachable))

    def _drop_stale_dimensions(self, kus: list[KuEmbeddingRow]) -> list[KuEmbeddingRow]:
        """Keep only embeddings of the dominant dimension.

        A model/dimension change (ADR-068) can leave a stale vector of a
        different length until the backfill sweeps it; one such row would
        crash the strict pairwise scorer and 500 the generate action.
        Majority dimension wins; dropped rows are logged for the backfill.
        """
        if not kus:
            return kus
        counts = Counter(len(ku["embedding"]) for ku in kus)
        if len(counts) == 1:
            return kus
        dominant = counts.most_common(1)[0][0]
        kept = [ku for ku in kus if len(ku["embedding"]) == dominant]
        self.logger.warning(
            f"Dropped {len(kus) - len(kept)} Ku embedding(s) with stale dimensions "
            f"from candidate generation (dominant {dominant}, seen {dict(counts)}) — "
            "run the embedding backfill to refresh them"
        )
        return kept

    @staticmethod
    def _reachable_from(start: str, adjacency: dict[str, set[str]]) -> set[str]:
        """All nodes reachable from ``start`` along stored edge directions (BFS)."""
        seen: set[str] = set()
        frontier = [start]
        while frontier:
            node = frontier.pop()
            for neighbor in adjacency.get(node, ()):
                if neighbor not in seen:
                    seen.add(neighbor)
                    frontier.append(neighbor)
        return seen

    def _band_pairs(
        self, kus: list[KuEmbeddingRow], reachable: dict[str, set[str]]
    ) -> list[PrereqCandidate]:
        """Pairwise cosine → band filter → coverage exclusion → per-Ku cap."""
        cfg = self._config
        normalized = [l2_normalize(ku["embedding"]) for ku in kus]

        def covered(a_uid: str, b_uid: str) -> bool:
            # Any directed path a→…→b or b→…→a (length 1 = a direct edge,
            # either direction) means the pair is already authored territory.
            return b_uid in reachable.get(a_uid, ()) or a_uid in reachable.get(b_uid, ())

        band: dict[tuple[int, int], float] = {}
        per_ku: dict[int, list[tuple[float, int]]] = {}
        for i in range(len(kus)):
            for j in range(i + 1, len(kus)):
                sim = dot(normalized[i], normalized[j])
                if not (cfg.band_low <= sim < cfg.band_high):
                    continue
                if covered(kus[i]["uid"], kus[j]["uid"]):
                    continue
                band[(i, j)] = sim
                per_ku.setdefault(i, []).append((sim, j))
                per_ku.setdefault(j, []).append((sim, i))

        # A pair survives when it is within EITHER endpoint's top-N band
        # neighbours (recall-leaning; the global max_pairs bound still holds).
        kept: set[tuple[int, int]] = set()
        for i, neighbors in per_ku.items():
            for _sim, j in sorted(neighbors, reverse=True)[: cfg.per_ku_cap]:
                kept.add((min(i, j), max(i, j)))

        ranked = sorted(kept, key=band.__getitem__, reverse=True)[: cfg.max_pairs]
        candidates: list[PrereqCandidate] = []
        for i, j in ranked:
            a, b = kus[i], kus[j]
            candidates.append(
                PrereqCandidate(
                    a_uid=a["uid"],
                    a_title=a["title"],
                    a_summary=a["summary"][: cfg.summary_max_chars],
                    b_uid=b["uid"],
                    b_title=b["title"],
                    b_summary=b["summary"][: cfg.summary_max_chars],
                    similarity=round(band[(i, j)], 4),
                )
            )
        return candidates

    # ------------------------------------------------------------------
    # Judge stage (FULL tier)
    # ------------------------------------------------------------------

    async def generate_suggestions(self) -> Result[PrereqSuggestionRun]:
        """The full on-demand pipeline: candidates, then the LLM judge when available.

        CORE degrade: without a caller every candidate passes through
        unjudged (``verdict=None``) — the admin queue serves undirected pairs
        and Mike chooses relation + direction himself.
        """
        candidates_result = await self.generate_candidates()
        if candidates_result.is_error:
            return Result.fail(candidates_result)
        candidates = candidates_result.value

        caller = self._llm.caller if self._llm is not None else None
        if caller is None or not candidates:
            suggestions = tuple(
                PrereqSuggestion(
                    a_uid=c.a_uid,
                    a_title=c.a_title,
                    b_uid=c.b_uid,
                    b_title=c.b_title,
                    similarity=c.similarity,
                    verdict=None,
                    rationale=None,
                )
                for c in candidates
            )
            return Result.ok(
                PrereqSuggestionRun(
                    suggestions=suggestions,
                    candidate_count=len(candidates),
                    judged=False,
                    skipped_by_judge=0,
                    judge_failures=0,
                )
            )

        cfg = self._config
        batches = [
            candidates[i : i + cfg.judge_batch_size]
            for i in range(0, len(candidates), cfg.judge_batch_size)
        ]
        semaphore = asyncio.Semaphore(cfg.judge_concurrency)

        async def judge_batch(
            batch: list[PrereqCandidate],
        ) -> tuple[list[PrereqSuggestion], int, int]:
            async with semaphore:
                return await self._judge_batch(batch)

        batch_results = await asyncio.gather(*(judge_batch(b) for b in batches))

        suggestions_list: list[PrereqSuggestion] = []
        skipped = 0
        failures = 0
        for batch_suggestions, batch_skipped, batch_failures in batch_results:
            suggestions_list.extend(batch_suggestions)
            skipped += batch_skipped
            failures += batch_failures

        if failures == len(candidates):
            return Result.fail(
                Errors.integration(
                    service="llm",
                    message="LLM judge failed on every candidate batch — no suggestions produced",
                )
            )

        suggestions_list.sort(key=self._suggestion_sort_key)
        return Result.ok(
            PrereqSuggestionRun(
                suggestions=tuple(suggestions_list),
                candidate_count=len(candidates),
                judged=True,
                skipped_by_judge=skipped,
                judge_failures=failures,
            )
        )

    @staticmethod
    def _suggestion_sort_key(suggestion: PrereqSuggestion) -> tuple[int, float]:
        """Prereq verdicts first, then by descending similarity."""
        is_prereq = suggestion.verdict in (JudgeVerdict.PREREQ_A_TO_B, JudgeVerdict.PREREQ_B_TO_A)
        return (0 if is_prereq else 1, -suggestion.similarity)

    async def _judge_batch(
        self, batch: list[PrereqCandidate]
    ) -> tuple[list[PrereqSuggestion], int, int]:
        """Judge one batch. Returns (suggestions, skipped_count, failure_count).

        Fail-soft: a malformed LLM response drops only this batch's
        candidates (counted as failures) — other batches still land.
        """
        pairs_block = "\n".join(
            f'{index}. A: "{c.a_title}" — {c.a_summary or "(no summary)"}\n'
            f'   B: "{c.b_title}" — {c.b_summary or "(no summary)"}'
            for index, c in enumerate(batch, start=1)
        )
        prompt = PROMPT_REGISTRY.render("prereq_edge_judge", pairs_block=pairs_block)

        caller = self._llm.caller if self._llm is not None else None
        if caller is None:  # pragma: no cover — guarded by the caller
            return [], 0, len(batch)

        messages: list[ChatMessage] = [{"role": "user", "content": prompt}]
        completion_result = await caller.complete(
            messages,
            model=self._config.judge_model,
            temperature=0.1,
            max_tokens=self._config.judge_max_tokens,
        )
        if completion_result.is_error:
            self.logger.warning(
                f"Prereq judge batch failed ({len(batch)} pairs): {completion_result.error}"
            )
            return [], 0, len(batch)

        try:
            raw = completion_result.value.text
            if "```" in raw:
                raw = raw.split("```")[1]
                raw = raw.removeprefix("json")
            items = json.loads(raw.strip())
            if not isinstance(items, list):
                raise TypeError("judge output is not a JSON array")
        except (json.JSONDecodeError, TypeError, IndexError) as e:
            self.logger.warning(f"Prereq judge returned malformed JSON ({len(batch)} pairs): {e}")
            return [], 0, len(batch)

        verdicts: dict[int, tuple[JudgeVerdict, str]] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                index = int(item.get("index", 0))
                verdict = JudgeVerdict(str(item.get("verdict", "")))
            except TypeError, ValueError:
                continue
            if not (1 <= index <= len(batch)) or index in verdicts:
                continue
            verdicts[index] = (verdict, " ".join(str(item.get("rationale", "")).split()))

        suggestions: list[PrereqSuggestion] = []
        skipped = 0
        failures = 0
        for index, candidate in enumerate(batch, start=1):
            judged = verdicts.get(index)
            if judged is None:
                failures += 1
                continue
            verdict, rationale = judged
            if verdict is JudgeVerdict.SKIP:
                skipped += 1
                continue
            suggestions.append(
                PrereqSuggestion(
                    a_uid=candidate.a_uid,
                    a_title=candidate.a_title,
                    b_uid=candidate.b_uid,
                    b_title=candidate.b_title,
                    similarity=candidate.similarity,
                    verdict=verdict,
                    rationale=rationale or None,
                )
            )
        return suggestions, skipped, failures
