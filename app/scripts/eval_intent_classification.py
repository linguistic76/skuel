#!/usr/bin/env python3
"""Intent-classification eval — is the gate reachable, and does it pick the right intent?

The instrument for PR-1 of docs/roadmap/askesis-intent-classification-activation.md.
`IntentClassifier` has never returned anything but `SPECIFIC` in production, and
an entire intent-conditioned layer of Askesis has therefore never executed. Before
PR-2 turns those branches on, this measures — against a reviewable labelled set —
what the classifier would actually decide, and under which aggregation.

Three aggregation arms over the SAME query embedding and the SAME exemplar
embeddings, so the only variable is how an intent's eight per-exemplar
similarities collapse into one score:

  mean       — production today (`_score_against_exemplars`). Averaging eight
               diverse short sentences puts the mean far below any single match.
  max        — the single best-matching exemplar wins.
  top3_mean  — the mean of an intent's three best-matching exemplars.

⚠ The `mean` arm is not a re-implementation to be trusted on its word: every row
is ALSO classified through the production `classify_intent_scored`, and the run
FAILS if the two disagree. The counterfactual arms are only worth reading while
the arm that mirrors production provably mirrors it (`production_agreement` in
the report).

`classify_intent_scored`, never `classify_intent`: the latter is fail-soft by
contract and converts an embeddings outage into `Result.ok(SPECIFIC)` — which is
byte-identical to a genuine below-gate verdict, i.e. exactly the finding this
script exists to measure, manufactured out of a provider blip.

What a run reports, per arm: accuracy at the live gate, the ranking accuracy
that ignores the gate, the score and margin distributions, how many queries
clear `IntelligenceThreshold.INTENT_CLASSIFICATION`, and a threshold sweep —
the inputs PR-2 needs to re-base aggregation AND threshold together.

⚠ PR-1 acceptance condition (see the arc doc): after the AGGREGATION/EXPLORATORY
exemplar rewrite, EVERY query's best score must stay BELOW the live threshold on
the production arm. Editing exemplars is not behaviour-neutral — a more coherent
set scores HIGHER — and a query that starts classifying before PR-2 exists is
answered by branches that have no tool behind them yet. `cleared_gate` on the
mean arm is that condition, and the human summary states it outright.

Query set: scripts/eval_intent_classification_queries.yaml (reviewable, checked
in; it evolves under review — this script does not). Runs print a DRAFT banner
until the set carries a `ratified:` date; the first RATIFIED run IS the baseline.

Usage:
    uv run python scripts/eval_intent_classification.py           # human summary
    uv run python scripts/eval_intent_classification.py --json    # machine output
    uv run python scripts/eval_intent_classification.py --queries other_set.yaml

Requires INTELLIGENCE_TIER=full (embeddings). Read-only apart from the embedding
API calls: it writes nothing, and classification touches no telemetry.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import statistics
import sys
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

import yaml

# Sibling module: sys.path[0] is scripts/ when run as `python scripts/...`,
# which is how ./dev invokes it. The `ratified:`/int parses are SHARED with the
# chunk-retrieval set on purpose — one ratification contract, one parse.
from eval_query_set import (  # type: ignore[import-not-found]
    parse_int_field,
    parse_ratified_field,
)

if TYPE_CHECKING:
    from core.services.askesis.intent_classifier import IntentClassifier
    from core.services.embeddings_service import EmbeddingsService

DEFAULT_QUERY_SET = Path(__file__).parent / "eval_intent_classification_queries.yaml"

# The catch-all verdict. It has no exemplars — it is what the classifier returns
# when NOTHING clears the gate — so a SPECIFIC-labelled row is a claim that no
# intent should fire, not a claim about a seventh exemplar set.
SPECIFIC_LABEL = "specific"

ARMS = ("mean", "max", "top3_mean")
TOP_N = 3

# How far the re-implemented `mean` arm may sit from the production score before
# the run is void. Same text through the same provider should embed identically;
# this tolerates float noise, not a different computation.
PRODUCTION_SCORE_TOLERANCE = 1e-3

# Candidate gates for PR-2, which must re-base aggregation and threshold
# together. Reported as accuracy + mis-fire counts per arm, never as a
# recommendation: a threshold that maximises accuracy on 44 labelled queries is
# a starting point for a ruling, not the ruling.
SWEEP_THRESHOLDS = (0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80)

# Advisory flag, not a gate: a labelled query this close to an exemplar is
# measuring the exemplar against itself. One such probe is deliberate (the
# ceiling row); an UNMARKED one means the set flatters the classifier, which is
# the exact defect that made the arc doc's 12-probe sketch optimistic.
EXEMPLAR_DUPLICATE_SCORE = 0.85

VALID_KINDS = frozenset({"real_usage", "natural", "near_exemplar", "collision_probe"})


@cache
def allowed_labels() -> frozenset[str]:
    """The intent values a labelled query may claim.

    DERIVED from `INTENT_EXEMPLARS` plus the catch-all, never re-spelled: the
    classifier can only ever return an intent it holds exemplars for, so a set
    labelling a query `goal_achievement` (a real `QueryIntent` member with no
    exemplars) is claiming an outcome no aggregation can produce. Deriving it
    means adding a seventh exemplar set widens this automatically, and deleting
    one breaks the set loudly instead of silently unmeasuring its rows.

    Imported lazily so the module stays importable — and `--help` usable —
    without loading the app.
    """
    from core.services.askesis.intent_classifier import INTENT_EXEMPLARS

    return frozenset({intent.value for intent in INTENT_EXEMPLARS} | {SPECIFIC_LABEL})


class SweepPoint(TypedDict):
    """One candidate gate's outcome for one arm."""

    threshold: float
    accuracy: float
    cleared_gate: int
    wrong_activations: int


class FrontierPoint(TypedDict):
    """One arm's EXACT lowest zero-wrong-activation gate.

    The threshold ladder cannot answer this: it samples 0.05 steps, so an arm
    whose last mis-route scores 0.527 is credited with the ladder's 0.55 and
    undercounted by every query between. PR-2 chooses a gate on exactly this
    number, so it is computed at OBSERVED scores instead (Codex, #1206).
    """

    threshold: float | None
    cleared_gate: int
    accuracy: float
    forced_by_score: float | None
    forced_by_query: str | None


class LabelReport(TypedDict):
    """Per-expected-intent aggregate within one arm."""

    queries: int
    correct: int
    accuracy: float
    cleared_gate: int


class ArmReport(TypedDict):
    """One aggregation strategy's full result."""

    strategy: str
    scored: int
    correct: int
    accuracy: float
    # Gate-blind: does the top-scoring intent match the label? Scored only over
    # rows with a non-SPECIFIC label, because SPECIFIC has no exemplars and so
    # can never BE the argmax — counting those rows would measure the gate again
    # under a name that promises not to.
    ranking_scored: int
    ranking_correct: int
    ranking_accuracy: float
    cleared_gate: int
    cleared_gate_share: float
    # An intent fired and it was the wrong one (label mismatch, predicted not
    # SPECIFIC) — the user-visible failure. Its mirror, `missed_activations`, is
    # a labelled intent that stayed below the gate: today's total behaviour.
    wrong_activations: int
    missed_activations: int
    score_min: float
    score_median: float
    score_max: float
    margin_median: float
    by_label: dict[str, LabelReport]
    zero_wrong_frontier: FrontierPoint
    threshold_sweep: list[SweepPoint]


class ArmRowReport(TypedDict):
    """One arm's verdict on one query, as serialized."""

    best_intent: str
    best_score: float
    runner_up: str | None
    runner_up_score: float
    margin: float
    predicted: str
    cleared_gate: bool
    correct: bool


class RowReport(TypedDict):
    """One labelled query's outcome across every arm."""

    query: str
    label: str
    kind: str
    nearest_exemplar: str | None
    production_intent: str | None
    production_score: float | None
    agrees_with_production: bool | None
    arms: dict[str, ArmRowReport]
    error: str | None


class ProductionAgreement(TypedDict):
    """Whether the `mean` arm actually mirrors production.

    The premise of every counterfactual number in the report. Proven per run,
    never assumed. A `disagreement` is EITHER a different predicted intent or a
    score more than `PRODUCTION_SCORE_TOLERANCE` from production's — the two are
    one verdict because either one means the arms were not computed on the
    embeddings production actually used; `max_score_delta` says which it was.
    """

    checked: int
    disagreements: int
    max_score_delta: float


class EvalReport(TypedDict):
    """The full report — the JSON contract of a recorded run."""

    query_set_version: int
    ratified: str | None
    threshold: float
    query_count: int
    errors: int
    label_counts: dict[str, int]
    production_agreement: ProductionAgreement
    arms: dict[str, ArmReport]
    rows: list[RowReport]


@dataclass(frozen=True)
class LabelledQuery:
    """One reviewable query → expected-intent claim from the labelled set."""

    query: str
    label: str
    kind: str
    note: str


@dataclass(frozen=True)
class LabelledSet:
    """The parsed, validated labelled-set file."""

    version: int
    ratified: str | None
    queries: tuple[LabelledQuery, ...]


def fires(best_intent: str, best_score: float, threshold: float) -> bool:
    """THE definition of "this arm activates an intent" (pure, DB-free).

    Two conditions, and the second is easy to forget: the score must clear the
    gate, AND an intent must have won at all. `score_arm` leaves `best_intent`
    empty when no intent scores above zero — cosine can be zero or negative —
    and production returns SPECIFIC there, so an empty winner is NOT an
    activation.

    This lived as three separate copies until one of them (the zero-wrong
    frontier) was written without the empty check and reported a correctly
    classified SPECIFIC row as a mis-route (Codex, #1206). Every consumer calls
    this now; do not re-inline it.
    """
    return best_score >= threshold and bool(best_intent)


@dataclass(frozen=True)
class ArmOutcome:
    """One aggregation's verdict on one query (pure, DB-free)."""

    best_intent: str
    best_score: float
    runner_up: str | None
    runner_up_score: float
    predicted: str
    cleared_gate: bool
    correct: bool

    def fires_at(self, threshold: float) -> bool:
        """Whether this verdict activates an intent at `threshold`."""
        return fires(self.best_intent, self.best_score, threshold)

    def predicted_at(self, threshold: float) -> str:
        """The intent returned at `threshold` — the catch-all when it does not fire."""
        return self.best_intent if self.fires_at(threshold) else SPECIFIC_LABEL

    def is_misroute_at(self, label: str, threshold: float) -> bool:
        """Fires at `threshold` AND on the WRONG intent — the expensive error.

        Distinct from "incorrect": a labelled intent that stays below the gate is
        a miss, which costs the user nothing beyond today's behaviour.
        """
        return self.fires_at(threshold) and self.best_intent != label

    @property
    def margin(self) -> float:
        """How far the winner sits above the runner-up — the separation PR-2 reads."""
        return self.best_score - self.runner_up_score

    def to_dict(self) -> ArmRowReport:
        return {
            "best_intent": self.best_intent,
            "best_score": round(self.best_score, 4),
            "runner_up": self.runner_up,
            "runner_up_score": round(self.runner_up_score, 4),
            "margin": round(self.margin, 4),
            "predicted": self.predicted,
            "cleared_gate": self.cleared_gate,
            "correct": self.correct,
        }


@dataclass
class QueryRow:
    """One labelled query's measured outcome."""

    query: str
    label: str
    kind: str
    arms: dict[str, ArmOutcome]
    nearest_exemplar: str | None = None
    production_intent: str | None = None
    production_score: float | None = None
    agrees_with_production: bool | None = None
    error: str | None = None

    def to_dict(self) -> RowReport:
        return {
            "query": self.query,
            "label": self.label,
            "kind": self.kind,
            "nearest_exemplar": self.nearest_exemplar,
            "production_intent": self.production_intent,
            "production_score": (
                None if self.production_score is None else round(self.production_score, 4)
            ),
            "agrees_with_production": self.agrees_with_production,
            "arms": {name: outcome.to_dict() for name, outcome in self.arms.items()},
            "error": self.error,
        }


def load_labelled_set(path: Path) -> LabelledSet:
    """Parse and validate the labelled-set YAML; every defect is a loud ValueError.

    The set is hand-edited under review, so this validation is its only
    structural gate — precise messages over lenient parsing.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: top level must be a mapping")

    version = parse_int_field(raw.get("version"), str(path), "version")
    # Unforgeable by a typo: the FIRST ratified run becomes the baseline, so
    # `ratified: yes` must never coerce into a truthy date string.
    ratified = parse_ratified_field(raw.get("ratified"), str(path))

    entries = raw.get("queries")
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"{path}: 'queries' must be a non-empty list")

    labels = allowed_labels()
    queries: list[LabelledQuery] = []
    seen_texts: set[str] = set()
    for i, entry in enumerate(entries):
        where = f"{path}: queries[{i}]"
        if not isinstance(entry, dict):
            raise ValueError(f"{where}: must be a mapping")
        text = entry.get("query")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"{where}: 'query' must be a non-empty string")
        if text in seen_texts:
            raise ValueError(f"{where}: duplicate query text {text!r}")
        seen_texts.add(text)
        label = entry.get("intent")
        if label not in labels:
            raise ValueError(f"{where}: 'intent' must be one of {sorted(labels)}, got {label!r}")
        kind = entry.get("kind")
        if kind not in VALID_KINDS:
            raise ValueError(f"{where}: 'kind' must be one of {sorted(VALID_KINDS)}, got {kind!r}")
        note = entry.get("note", "")
        if not isinstance(note, str):
            raise ValueError(f"{where}: 'note' must be a string")
        queries.append(LabelledQuery(query=text, label=str(label), kind=kind, note=note))

    return LabelledSet(version=version, ratified=ratified, queries=tuple(queries))


def aggregate(similarities: list[float], strategy: str) -> float:
    """Collapse one intent's per-exemplar similarities into a single score (pure).

    `mean` is production's arithmetic, reproduced here rather than imported
    because the point is to run the OTHER two over identical inputs; the run
    proves the reproduction by comparing against `classify_intent_scored`.
    """
    if not similarities:
        return 0.0
    if strategy == "mean":
        return sum(similarities) / len(similarities)
    if strategy == "max":
        return max(similarities)
    if strategy == "top3_mean":
        top = sorted(similarities, reverse=True)[:TOP_N]
        return sum(top) / len(top)
    raise ValueError(f"unknown aggregation strategy: {strategy!r}")


def score_arm(scores: dict[str, float], label: str, threshold: float) -> ArmOutcome:
    """Turn one arm's per-intent scores into a verdict (pure, DB-free).

    Mirrors `_score_against_exemplars`: strict `>` over the intents in
    `INTENT_EXEMPLARS` order, so a tie goes to the first-declared intent exactly
    as production resolves it, and a below-gate best is the catch-all SPECIFIC —
    a classification, not a failure.
    """
    best_intent = ""
    best_score = 0.0
    for intent, score in scores.items():
        if score > best_score:
            best_intent, best_score = intent, score

    runner_up: str | None = None
    runner_up_score = 0.0
    for intent, score in scores.items():
        if intent == best_intent:
            continue
        if runner_up is None or score > runner_up_score:
            runner_up, runner_up_score = intent, score

    cleared = fires(best_intent, best_score, threshold)
    predicted = best_intent if cleared else SPECIFIC_LABEL
    return ArmOutcome(
        best_intent=best_intent,
        best_score=best_score,
        runner_up=runner_up,
        runner_up_score=runner_up_score,
        predicted=predicted,
        cleared_gate=cleared,
        correct=predicted == label,
    )


def sweep(rows: list[QueryRow], arm: str) -> list[SweepPoint]:
    """Re-score one arm at each candidate gate (pure, DB-free).

    Post-processing of scores already measured — no second measurement, and no
    recommendation: PR-2 rules on the mechanism, this only says what each gate
    would have done to THIS set.
    """
    scored = [row for row in rows if row.error is None]
    points: list[SweepPoint] = []
    for threshold in SWEEP_THRESHOLDS:
        correct = 0
        cleared = 0
        wrong = 0
        for row in scored:
            outcome = row.arms[arm]
            if outcome.fires_at(threshold):
                cleared += 1
            if outcome.predicted_at(threshold) == row.label:
                correct += 1
            elif outcome.is_misroute_at(row.label, threshold):
                wrong += 1
        points.append(
            {
                "threshold": threshold,
                "accuracy": round(correct / len(scored), 4) if scored else 0.0,
                "cleared_gate": cleared,
                "wrong_activations": wrong,
            }
        )
    return points


def zero_wrong_frontier(rows: list[QueryRow], arm: str) -> FrontierPoint:
    """The lowest gate at which this arm mis-routes NOTHING (pure, DB-free).

    Evaluated at every observed score rather than on a fixed ladder, because the
    frontier is pinned by one query — the highest-scoring mis-route — and a
    0.05 grid rounds that up to the next step, crediting the arm with a stricter
    gate and fewer activations than it actually needs. Comparing arms on the
    rounded number can invert which one activates most (Codex, #1206).

    ``threshold`` is None when no cutoff over the observed scores is clean —
    i.e. the top-scoring query is itself a mis-route, so only an empty gate is.
    ``forced_by_*`` names the query that sets the frontier: fix ITS routing and
    the gate can come down.
    """
    scored = [row for row in rows if row.error is None]
    if not scored:
        return {
            "threshold": None,
            "cleared_gate": 0,
            "accuracy": 0.0,
            "forced_by_score": None,
            "forced_by_query": None,
        }

    # A row that never fires can never mis-route, whatever its label.
    wrong = [
        (row.arms[arm].best_score, row.query)
        for row in scored
        if row.arms[arm].is_misroute_at(row.label, row.arms[arm].best_score)
    ]
    forced_score, forced_query = max(wrong) if wrong else (None, None)

    for cutoff in sorted({row.arms[arm].best_score for row in scored}):
        firing = [row for row in scored if row.arms[arm].fires_at(cutoff)]
        if any(row.arms[arm].is_misroute_at(row.label, cutoff) for row in scored):
            continue
        correct = sum(1 for row in scored if row.arms[arm].predicted_at(cutoff) == row.label)
        return {
            "threshold": round(cutoff, 4),
            "cleared_gate": len(firing),
            "accuracy": round(correct / len(scored), 4),
            "forced_by_score": None if forced_score is None else round(forced_score, 4),
            "forced_by_query": forced_query,
        }

    # Every observed cutoff admits a mis-route: only a gate above the top score
    # is clean, and that one activates nothing.
    return {
        "threshold": None,
        "cleared_gate": 0,
        "accuracy": round(sum(1 for row in scored if row.label == SPECIFIC_LABEL) / len(scored), 4),
        "forced_by_score": None if forced_score is None else round(forced_score, 4),
        "forced_by_query": forced_query,
    }


def summarize_arm(rows: list[QueryRow], arm: str, threshold: float) -> ArmReport:
    """Aggregate one arm's per-query outcomes (pure, DB-free)."""
    scored = [row for row in rows if row.error is None]
    outcomes = [(row, row.arms[arm]) for row in scored]
    correct = sum(1 for _, o in outcomes if o.correct)
    cleared = sum(1 for _, o in outcomes if o.cleared_gate)
    wrong = sum(1 for r, o in outcomes if o.is_misroute_at(r.label, threshold))
    missed = sum(
        1 for r, o in outcomes if r.label != SPECIFIC_LABEL and o.predicted == SPECIFIC_LABEL
    )
    ranked = [(r, o) for r, o in outcomes if r.label != SPECIFIC_LABEL]
    ranking_correct = sum(1 for r, o in ranked if o.best_intent == r.label)
    scores = [o.best_score for _, o in outcomes]
    margins = [o.margin for _, o in outcomes]

    by_label: dict[str, LabelReport] = {}
    for row, outcome in outcomes:
        entry = by_label.setdefault(
            row.label, {"queries": 0, "correct": 0, "accuracy": 0.0, "cleared_gate": 0}
        )
        entry["queries"] += 1
        entry["correct"] += int(outcome.correct)
        entry["cleared_gate"] += int(outcome.cleared_gate)
    for entry in by_label.values():
        entry["accuracy"] = round(entry["correct"] / entry["queries"], 4)

    total = len(outcomes)
    return {
        "strategy": arm,
        "scored": total,
        "correct": correct,
        "accuracy": round(correct / total, 4) if total else 0.0,
        "ranking_scored": len(ranked),
        "ranking_correct": ranking_correct,
        "ranking_accuracy": round(ranking_correct / len(ranked), 4) if ranked else 0.0,
        "cleared_gate": cleared,
        "cleared_gate_share": round(cleared / total, 4) if total else 0.0,
        "wrong_activations": wrong,
        "missed_activations": missed,
        "score_min": round(min(scores), 4) if scores else 0.0,
        "score_median": round(statistics.median(scores), 4) if scores else 0.0,
        "score_max": round(max(scores), 4) if scores else 0.0,
        "margin_median": round(statistics.median(margins), 4) if margins else 0.0,
        "by_label": {label: by_label[label] for label in sorted(by_label)},
        "zero_wrong_frontier": zero_wrong_frontier(rows, arm),
        "threshold_sweep": sweep(rows, arm),
    }


def summarize(rows: list[QueryRow], labelled_set: LabelledSet, threshold: float) -> EvalReport:
    """Aggregate every arm into the report dict (pure, DB-free)."""
    checked = [row for row in rows if row.agrees_with_production is not None]
    deltas = [
        abs(row.production_score - row.arms["mean"].best_score)
        for row in checked
        if row.production_score is not None
    ]
    label_counts: dict[str, int] = {}
    for row in rows:
        label_counts[row.label] = label_counts.get(row.label, 0) + 1

    return {
        "query_set_version": labelled_set.version,
        "ratified": labelled_set.ratified,
        "threshold": threshold,
        "query_count": len(rows),
        "errors": sum(1 for row in rows if row.error is not None),
        "label_counts": {label: label_counts[label] for label in sorted(label_counts)},
        "production_agreement": {
            "checked": len(checked),
            "disagreements": sum(1 for row in checked if not row.agrees_with_production),
            "max_score_delta": round(max(deltas), 6) if deltas else 0.0,
        },
        "arms": {arm: summarize_arm(rows, arm, threshold) for arm in ARMS},
        "rows": [row.to_dict() for row in rows],
    }


async def embed_exemplars(
    embeddings_service: EmbeddingsService,
) -> dict[str, list[list[float]]] | str:
    """Embed every intent exemplar, or return an error string that voids the run.

    A PARTIAL set is not a degraded measurement, it is a wrong one: per-intent
    scores would be averaged over unequal denominators, and a smaller
    denominator RAISES the mean — so an intent that lost exemplars looks more
    confident, not less. Production refuses a partial load for exactly this
    reason (`ExemplarLoad`); so does this.
    """
    from core.services.askesis.intent_classifier import INTENT_EXEMPLARS

    embedded: dict[str, list[list[float]]] = {}
    for intent, exemplars in INTENT_EXEMPLARS.items():
        vectors: list[list[float]] = []
        for exemplar in exemplars:
            result = await embeddings_service.create_embedding(exemplar)
            if result.is_error:
                return (
                    f"exemplar {exemplar!r} ({intent.value}) failed to embed: "
                    f"{result.expect_error()} — a partial exemplar set averages over "
                    "unequal denominators and cannot be scored"
                )
            vectors.append(result.value)
        embedded[intent.value] = vectors
    return embedded


def nearest_exemplar(
    similarities: dict[str, list[float]], exemplar_texts: dict[str, list[str]]
) -> str | None:
    """The single exemplar a query sits closest to, across every intent (pure).

    The `max` arm's best score IS this similarity, so the pair reads as "how
    close, and to WHAT" — which is what makes a `near_exemplar` label auditable
    instead of trusted. A set whose rows quietly duplicate exemplars measures the
    exemplar against itself and reports it as classifier skill.
    """
    best_text: str | None = None
    best_score = 0.0
    for intent, sims in similarities.items():
        for i, score in enumerate(sims):
            if score > best_score:
                best_score, best_text = score, exemplar_texts[intent][i]
    return best_text


async def measure_production(classifier: IntentClassifier, query: str) -> tuple[str, float] | str:
    """Classify one query through the OBSERVABLE production API.

    `classify_intent_scored`, not `classify_intent`: the fail-soft one turns an
    embeddings outage into `Result.ok(SPECIFIC)`, indistinguishable from the
    genuine below-gate verdict this eval measures — an outage would score as a
    clean sweep of the very finding under test.
    """
    scored = await classifier.classify_intent_scored(query)
    if scored.is_error:
        return f"intent classification failed: {scored.expect_error()}"
    return scored.value.intent.value, scored.value.score


async def run_eval(labelled_set: LabelledSet, *, as_json: bool) -> tuple[int, EvalReport | None]:
    """Compose services, score every arm per query, and return (exit_code, report)."""
    from adapters.infrastructure.event_bus import InMemoryEventBus
    from adapters.persistence.neo4j_adapter import Neo4jAdapter
    from core.constants import IntelligenceThreshold
    from core.services.askesis.intent_classifier import INTENT_EXEMPLARS, IntentClassifier
    from core.utils.vector_math import cosine_similarity
    from services_bootstrap import compose_services

    threshold = float(IntelligenceThreshold.INTENT_CLASSIFICATION)

    if not as_json:
        print("Connecting to Neo4j...", file=sys.stderr)
    adapter = Neo4jAdapter()
    await adapter.connect()
    try:
        composed = await compose_services(adapter, InMemoryEventBus())
        if composed.is_error:
            print(f"ERROR: composition failed: {composed.expect_error()}", file=sys.stderr)
            return 1, None

        embeddings = composed.value.embeddings_service
        if embeddings is None:
            # Without embeddings every arm scores zero and every row "confirms"
            # that nothing clears the gate — the predictable wrong-firing mode.
            print(
                "ERROR: this eval requires INTELLIGENCE_TIER=full (embeddings). "
                "Refusing to run three empty arms.",
                file=sys.stderr,
            )
            return 2, None

        exemplars = await embed_exemplars(embeddings)
        if isinstance(exemplars, str):
            print(f"ERROR: {exemplars}", file=sys.stderr)
            return 2, None

        exemplar_texts = {intent.value: list(texts) for intent, texts in INTENT_EXEMPLARS.items()}
        classifier = IntentClassifier(embeddings)
        rows: list[QueryRow] = []
        for labelled in labelled_set.queries:
            query_result = await embeddings.create_embedding(labelled.query)
            if query_result.is_error:
                rows.append(
                    QueryRow(
                        query=labelled.query,
                        label=labelled.label,
                        kind=labelled.kind,
                        arms={},
                        error=f"query embedding failed: {query_result.expect_error()}",
                    )
                )
                continue
            query_embedding = query_result.value

            similarities = {
                intent: [cosine_similarity(query_embedding, vector) for vector in vectors]
                for intent, vectors in exemplars.items()
            }
            arms = {
                arm: score_arm(
                    {intent: aggregate(sims, arm) for intent, sims in similarities.items()},
                    labelled.label,
                    threshold,
                )
                for arm in ARMS
            }

            row = QueryRow(
                query=labelled.query,
                label=labelled.label,
                kind=labelled.kind,
                arms=arms,
                nearest_exemplar=nearest_exemplar(similarities, exemplar_texts),
            )
            measured = await measure_production(classifier, labelled.query)
            if isinstance(measured, str):
                row.error = measured
            else:
                row.production_intent, row.production_score = measured
                row.agrees_with_production = (
                    row.production_intent == arms["mean"].predicted
                    and abs(row.production_score - arms["mean"].best_score)
                    <= PRODUCTION_SCORE_TOLERANCE
                )
            rows.append(row)

        report = summarize(rows, labelled_set, threshold)
        # A disagreement voids the counterfactual arms: they are only meaningful
        # while the arm mirroring production provably mirrors it.
        void = report["errors"] or report["production_agreement"]["disagreements"]
        return (1 if void else 0), report
    finally:
        await adapter.close()


def _print_human(report: EvalReport) -> None:
    """Render the report as a readable console summary."""
    if report["ratified"]:
        print(
            f"\n=== Intent-Classification Eval (set v{report['query_set_version']}, "
            f"ratified {report['ratified']}) ==="
        )
    else:
        print(f"\n=== Intent-Classification Eval (set v{report['query_set_version']}) ===")
        print("⚠ DRAFT labelled set — labels not yet ratified; this run is NOT a baseline.")
    print(f"gate: IntelligenceThreshold.INTENT_CLASSIFICATION = {report['threshold']}")
    counts = ", ".join(f"{label} {n}" for label, n in report["label_counts"].items())
    print(f"labels: {counts}\n")

    for row in report["rows"]:
        if row["error"] is not None:
            print(f"  ✗ ERROR  {row['query']!r}: {row['error']}")
            continue
        mean = row["arms"]["mean"]
        mark = "✓" if mean["correct"] else "✗"
        others = "  ".join(
            f"{arm}={row['arms'][arm]['best_intent']}@{row['arms'][arm]['best_score']:.3f}"
            for arm in ARMS
            if arm != "mean"
        )
        print(
            f"  {mark} {row['label']:<13}{row['query']!r}\n"
            f"      mean={mean['best_intent']}@{mean['best_score']:.3f}"
            f" (runner-up {mean['runner_up']}@{mean['runner_up_score']:.3f},"
            f" margin {mean['margin']:.3f})  {others}"
        )

    for arm in ARMS:
        a = report["arms"][arm]
        marker = " (production)" if arm == "mean" else ""
        print(f"\n--- {arm}{marker} ---")
        print(
            f"  accuracy at gate: {a['correct']}/{a['scored']} ({a['accuracy']:.0%})"
            f" — ranking (gate-blind): {a['ranking_correct']}/{a['ranking_scored']}"
            f" ({a['ranking_accuracy']:.0%})"
        )
        print(
            f"  cleared the gate: {a['cleared_gate']}/{a['scored']}"
            f" ({a['cleared_gate_share']:.0%});"
            f" wrong activations {a['wrong_activations']}, missed {a['missed_activations']}"
        )
        print(
            f"  best score min/median/max: {a['score_min']:.3f} / {a['score_median']:.3f}"
            f" / {a['score_max']:.3f}; median margin {a['margin_median']:.3f}"
        )
        frontier = a["zero_wrong_frontier"]
        if frontier["threshold"] is None:
            print("  zero-wrong frontier: none — every cutoff admits a mis-route")
        else:
            # An arm that mis-routes NOTHING anywhere has no pinning query, so
            # `forced_by_score` is None — and formatting None with `:.3f` raises.
            # Today every arm has a mis-route, which is why this never fired; a
            # cleaner set or a smaller --queries set reaches it (Kody, #1206).
            pinned = (
                f"pinned by {frontier['forced_by_query']!r} @ {frontier['forced_by_score']:.3f}"
                if frontier["forced_by_score"] is not None
                else "no mis-routes at any gate"
            )
            print(
                f"  zero-wrong frontier: gate {frontier['threshold']:.4f} →"
                f" {frontier['cleared_gate']} fire, accuracy {frontier['accuracy']:.0%}"
                f" ({pinned})"
            )
        best = max(a["threshold_sweep"], key=lambda p: p["accuracy"])
        print(
            f"  sweep best: threshold {best['threshold']:.2f} →"
            f" accuracy {best['accuracy']:.0%},"
            f" {best['cleared_gate']} fire, {best['wrong_activations']} wrong"
        )

    flattering = [
        row
        for row in report["rows"]
        if row["error"] is None and row["arms"]["max"]["best_score"] >= EXEMPLAR_DUPLICATE_SCORE
    ]
    if flattering:
        print(
            f"\n{len(flattering)} row(s) within {EXEMPLAR_DUPLICATE_SCORE} of an exemplar"
            " — upper-bound probes, not evidence about real phrasing:"
        )
        for row in flattering:
            print(
                f"    {row['query']!r} ({row['kind']}) ≈ {row['nearest_exemplar']!r}"
                f" @ {row['arms']['max']['best_score']:.3f}"
            )

    agreement = report["production_agreement"]
    print(
        f"\nproduction agreement: {agreement['checked']} checked,"
        f" {agreement['disagreements']} disagreement(s),"
        f" max score delta {agreement['max_score_delta']:.2e}"
    )
    if agreement["disagreements"]:
        print(
            "⚠ the `mean` arm does NOT mirror production — every counterfactual"
            " arm in this run is void."
        )

    cleared = report["arms"]["mean"]["cleared_gate"]
    if cleared:
        print(
            f"\n⚠ PR-1 ACCEPTANCE FAILS: {cleared} query(ies) clear the live gate on the"
            "\n  production arm. Exemplar edits that make an intent reachable belong in"
            "\n  PR-2, with the activation — see docs/roadmap/"
            "askesis-intent-classification-activation.md."
        )
    else:
        print(
            "\n✓ PR-1 acceptance: no query clears the live gate on the production arm —"
            "\n  the exemplar set stays unreachable until PR-2 re-bases the mechanism."
        )
    if report["errors"]:
        print(f"\n⚠ {report['errors']} query(ies) errored — run is not a valid measurement.")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Intent-classification eval across aggregation strategies "
            "(roadmap § askesis-intent-classification-activation, PR-1)."
        )
    )
    parser.add_argument(
        "--queries",
        type=Path,
        default=DEFAULT_QUERY_SET,
        help=f"labelled-set YAML (default: {DEFAULT_QUERY_SET.name})",
    )
    parser.add_argument(
        "--json", action="store_true", help="emit the raw report as JSON instead of a summary"
    )
    args = parser.parse_args()

    try:
        labelled_set = load_labelled_set(args.queries)
    except (ValueError, OSError, yaml.YAMLError) as e:
        print(f"ERROR: invalid labelled set: {e}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        # Redirect the ENTIRE async lifecycle to stderr (same rationale as
        # eval_chunk_retrieval.py): logging binds sys.stdout at configure time,
        # so the JSON printed after the guard is the only stdout content.
        with contextlib.redirect_stdout(sys.stderr):
            code, report = asyncio.run(run_eval(labelled_set, as_json=True))
        if report is not None:
            print(json.dumps(report, indent=2))
        sys.exit(code)

    code, report = asyncio.run(run_eval(labelled_set, as_json=False))
    if report is not None:
        _print_human(report)
    sys.exit(code)


if __name__ == "__main__":
    main()
