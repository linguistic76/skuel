"""Tests for the intent-classification eval's pure parts: set validation and scoring.

The instrument's live half is deliberately untested here — it drives the real
classifier, which is the point of the tool. What must never be wrong silently is
the labelled-set gate and the arm arithmetic, because a mis-scored run would
masquerade as a baseline, and PR-2 re-bases aggregation AND threshold on it.

These tests deliberately do NOT read the checked-in labelled-set YAML: CI's
``py`` path filter would not re-run them on a YAML-only edit, so a green run
against the file would be stale evidence. The script validates the real file on
every invocation instead — that is the file's gate.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# scripts/ has no __init__.py, and this directory is itself named `scripts`,
# so it shadows the real package under pytest's prepend import mode.
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from eval_intent_classification import (  # type: ignore[import-not-found]
    ARMS,
    SPECIFIC_LABEL,
    ArmOutcome,
    EvalReport,
    LabelledQuery,
    LabelledSet,
    QueryRow,
    _print_human,
    aggregate,
    allowed_labels,
    fires,
    load_labelled_set,
    nearest_exemplar,
    score_arm,
    summarize,
    summarize_arm,
    sweep,
    zero_wrong_frontier,
)

VALID_SET = """
version: 1
ratified: null
queries:
  - query: how many goals do I have
    intent: aggregation
    kind: natural
    note: bare count
  - query: why does my mind keep wandering
    intent: specific
    kind: natural
"""

THRESHOLD = 0.65


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "queries.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def _row(label: str, arms: dict[str, ArmOutcome], error: str | None = None) -> QueryRow:
    return QueryRow(query="q", label=label, kind="natural", arms=arms, error=error)


def _outcome(scores: dict[str, float], label: str) -> dict[str, ArmOutcome]:
    """Same per-intent scores on every arm — arm arithmetic is tested separately."""
    return {arm: score_arm(scores, label, THRESHOLD) for arm in ARMS}


class TestAllowedLabels:
    def test_derived_from_exemplars_plus_the_catch_all(self) -> None:
        from core.services.askesis.intent_classifier import INTENT_EXEMPLARS

        assert allowed_labels() == frozenset(
            {intent.value for intent in INTENT_EXEMPLARS} | {SPECIFIC_LABEL}
        )

    def test_an_intent_with_no_exemplars_is_not_labelable(self) -> None:
        """`goal_achievement` is a real QueryIntent the classifier can never return.

        Labelling a query with it would claim an outcome no aggregation can
        produce — the set would score an unreachable expectation as a finding.
        """
        assert "goal_achievement" not in allowed_labels()


class TestLoadLabelledSet:
    def test_valid_set_parses(self, tmp_path: Path) -> None:
        labelled = load_labelled_set(_write(tmp_path, VALID_SET))
        assert labelled.version == 1
        assert labelled.ratified is None
        assert len(labelled.queries) == 2
        assert labelled.queries[0].label == "aggregation"
        assert labelled.queries[1].note == ""  # note is optional

    def test_ratified_date_becomes_string(self, tmp_path: Path) -> None:
        content = VALID_SET.replace("ratified: null", "ratified: 2026-09-01")
        assert load_labelled_set(_write(tmp_path, content)).ratified == "2026-09-01"

    @pytest.mark.parametrize("value", ["yes", "true", "'not-a-date'", "[2026-09-01]"])
    def test_ratified_rejects_non_dates(self, tmp_path: Path, value: str) -> None:
        """A typo must not promote a draft run to the baseline."""
        content = VALID_SET.replace("ratified: null", f"ratified: {value}")
        with pytest.raises(ValueError, match="'ratified' must be null or an ISO date"):
            load_labelled_set(_write(tmp_path, content))

    @pytest.mark.parametrize(
        ("mutation", "fragment"),
        [
            (("version: 1", "version: '1'"), "'version' must be an integer"),
            (("version: 1", "version: true"), "'version' must be an integer"),
            (("intent: aggregation", "intent: vibes"), "'intent' must be one of"),
            (("intent: aggregation", "intent: goal_achievement"), "'intent' must be one of"),
            (("kind: natural\n    note: bare count", "kind: vibes\n    note: x"), "'kind' must be"),
            (("note: bare count", "note: [a list]"), "'note' must be a string"),
            (("queries:", "queries: []\nunused:"), "'queries' must be a non-empty list"),
        ],
    )
    def test_defects_raise_loudly(
        self, tmp_path: Path, mutation: tuple[str, str], fragment: str
    ) -> None:
        content = VALID_SET.replace(*mutation)
        with pytest.raises(ValueError, match=fragment):
            load_labelled_set(_write(tmp_path, content))

    def test_duplicate_query_text_raises(self, tmp_path: Path) -> None:
        content = VALID_SET.replace("why does my mind keep wandering", "how many goals do I have")
        with pytest.raises(ValueError, match="duplicate query text"):
            load_labelled_set(_write(tmp_path, content))


class TestAggregate:
    def test_mean_is_productions_arithmetic(self) -> None:
        assert aggregate([0.2, 0.4, 0.6], "mean") == pytest.approx(0.4)

    def test_max_takes_the_single_best_exemplar(self) -> None:
        assert aggregate([0.2, 0.9, 0.4], "max") == pytest.approx(0.9)

    def test_top3_mean_averages_the_three_best(self) -> None:
        assert aggregate([0.1, 0.2, 0.9, 0.8, 0.7], "top3_mean") == pytest.approx(0.8)

    def test_top3_mean_of_a_shorter_set_averages_what_there_is(self) -> None:
        assert aggregate([0.4, 0.6], "top3_mean") == pytest.approx(0.5)

    def test_empty_scores_zero_rather_than_dividing_by_zero(self) -> None:
        assert aggregate([], "mean") == 0.0

    def test_unknown_strategy_is_loud(self) -> None:
        with pytest.raises(ValueError, match="unknown aggregation strategy"):
            aggregate([0.5], "median")


class TestScoreArm:
    def test_below_the_gate_the_verdict_is_the_catch_all(self) -> None:
        outcome = score_arm({"practice": 0.4, "aggregation": 0.3}, "specific", THRESHOLD)
        assert outcome.best_intent == "practice"  # the argmax is still reported
        assert outcome.predicted == SPECIFIC_LABEL
        assert outcome.cleared_gate is False
        assert outcome.correct is True  # SPECIFIC was the right answer

    def test_clearing_the_gate_fires_the_intent(self) -> None:
        outcome = score_arm({"practice": 0.7, "aggregation": 0.3}, "practice", THRESHOLD)
        assert outcome.predicted == "practice"
        assert outcome.cleared_gate is True
        assert outcome.correct is True

    def test_a_wrong_intent_that_fires_is_incorrect(self) -> None:
        outcome = score_arm({"aggregation": 0.7, "practice": 0.3}, "specific", THRESHOLD)
        assert outcome.predicted == "aggregation"
        assert outcome.correct is False

    def test_margin_is_over_the_runner_up(self) -> None:
        outcome = score_arm({"a": 0.5, "b": 0.2, "c": 0.4}, "a", THRESHOLD)
        assert outcome.runner_up == "c"
        assert outcome.margin == pytest.approx(0.1)

    def test_a_tie_goes_to_the_first_declared_intent(self) -> None:
        """Production uses strict `>` over INTENT_EXEMPLARS order; so does this."""
        outcome = score_arm({"first": 0.5, "second": 0.5}, "first", THRESHOLD)
        assert outcome.best_intent == "first"

    def test_exactly_at_the_gate_fires(self) -> None:
        """`>=`, matching `_score_against_exemplars`."""
        assert score_arm({"practice": THRESHOLD}, "practice", THRESHOLD).cleared_gate is True


class TestNearestExemplar:
    def test_picks_the_globally_closest_exemplar_text(self) -> None:
        similarities = {"practice": [0.2, 0.9], "aggregation": [0.5]}
        texts = {"practice": ["p one", "p two"], "aggregation": ["a one"]}
        assert nearest_exemplar(similarities, texts) == "p two"

    def test_no_similarities_yields_nothing(self) -> None:
        assert nearest_exemplar({}, {}) is None


class TestSummarizeArm:
    def test_ranking_accuracy_ignores_the_gate_and_specific_rows(self) -> None:
        """SPECIFIC has no exemplars, so it can never BE the argmax.

        Counting those rows in a "gate-blind" number would measure the gate
        again under a name that promises not to.
        """
        rows = [
            _row("practice", _outcome({"practice": 0.4, "aggregation": 0.1}, "practice")),
            _row("specific", _outcome({"practice": 0.2}, "specific")),
        ]
        report = summarize_arm(rows, "mean", THRESHOLD)

        assert report["ranking_scored"] == 1
        assert report["ranking_correct"] == 1
        assert report["cleared_gate"] == 0
        # The practice row missed (below gate); the specific row is correct.
        assert report["missed_activations"] == 1
        assert report["correct"] == 1

    def test_a_wrong_firing_is_counted_apart_from_a_miss(self) -> None:
        rows = [
            _row("specific", _outcome({"aggregation": 0.9}, "specific")),
            _row("practice", _outcome({"practice": 0.2}, "practice")),
        ]
        report = summarize_arm(rows, "mean", THRESHOLD)

        assert report["wrong_activations"] == 1
        assert report["missed_activations"] == 1
        assert report["accuracy"] == 0.0

    def test_errored_rows_are_excluded_from_every_number(self) -> None:
        rows = [
            _row("practice", _outcome({"practice": 0.9}, "practice")),
            _row("specific", {}, error="embedding failed"),
        ]
        report = summarize_arm(rows, "mean", THRESHOLD)

        assert report["scored"] == 1
        assert report["accuracy"] == 1.0
        assert report["by_label"] == {
            "practice": {"queries": 1, "correct": 1, "accuracy": 1.0, "cleared_gate": 1}
        }


class TestSweep:
    def test_a_lower_gate_fires_more_and_can_be_wrong_more(self) -> None:
        rows = [
            _row("specific", _outcome({"aggregation": 0.5}, "specific")),
            _row("practice", _outcome({"practice": 0.5}, "practice")),
        ]
        points = {p["threshold"]: p for p in sweep(rows, "mean")}

        # At 0.65 nothing fires: the specific row is right, the practice row missed.
        assert points[0.65]["cleared_gate"] == 0
        assert points[0.65]["accuracy"] == pytest.approx(0.5)
        # At 0.45 both fire: practice becomes right, the specific row wrong.
        assert points[0.45]["cleared_gate"] == 2
        assert points[0.45]["wrong_activations"] == 1
        assert points[0.45]["accuracy"] == pytest.approx(0.5)


class TestFiresIsOneDefinition:
    """An empty winner is not an activation, and every consumer must agree.

    `score_arm` leaves `best_intent` empty when nothing scores above zero —
    cosine can be zero or negative — and production returns SPECIFIC there. The
    condition lived in three copies until a fourth was written without this
    check and counted a correctly classified SPECIFIC row as a mis-route
    (Codex, #1206).
    """

    def test_an_empty_winner_never_fires_however_low_the_gate(self) -> None:
        assert fires("", 0.0, 0.0) is False
        assert fires("practice", 0.0, 0.0) is True

    def test_a_nonpositive_row_is_not_a_misroute_at_any_cutoff(self) -> None:
        """The bug: at cutoff 0 this row was 'firing' with intent "" != 'specific'."""
        rows = [
            _row("specific", _outcome({"practice": -0.1, "aggregation": -0.2}, "specific")),
            _row("practice", _outcome({"practice": 0.5}, "practice")),
        ]
        frontier = zero_wrong_frontier(rows, "mean")

        assert frontier["forced_by_query"] is None, "a row that cannot fire cannot mis-route"
        assert frontier["threshold"] is not None, (
            "before the fix every cutoff 'admitted a mis-route' and the frontier collapsed to None"
        )
        assert frontier["cleared_gate"] == 1

    def test_the_frontier_and_the_sweep_agree_on_who_fires(self) -> None:
        """Two readings of one condition must not drift apart again."""
        rows = [
            _row("specific", _outcome({"practice": -0.3}, "specific")),
            _row("aggregation", _outcome({"aggregation": 0.45}, "aggregation")),
        ]
        at_zero = next(p for p in sweep(rows, "mean") if p["threshold"] == 0.30)

        assert at_zero["cleared_gate"] == 1, "the nonpositive row must not count as firing"
        assert zero_wrong_frontier(rows, "mean")["cleared_gate"] == 1


class TestZeroWrongFrontier:
    """The number PR-2 picks a gate from — and the one a 0.05 ladder gets wrong."""

    def test_frontier_sits_at_an_observed_score_not_a_grid_step(self) -> None:
        """A mis-route at 0.527 must yield a frontier just above IT, not 0.55.

        Rounding up to the ladder step drops every query scoring between, which
        undercounts the arm and can invert which aggregation looks best.
        """
        rows = [
            _row("practice", _outcome({"hierarchical": 0.527}, "practice")),  # mis-route
            _row("hierarchical", _outcome({"hierarchical": 0.540}, "hierarchical")),
            _row("practice", _outcome({"practice": 0.530}, "practice")),
        ]
        frontier = zero_wrong_frontier(rows, "mean")

        assert frontier["threshold"] == pytest.approx(0.530)
        assert frontier["cleared_gate"] == 2, "0.55 would have credited only one"
        assert frontier["forced_by_score"] == pytest.approx(0.527)

    def test_it_names_the_query_that_pins_the_gate(self) -> None:
        rows = [
            _row("specific", _outcome({"aggregation": 0.40}, "specific")),
            _row("practice", _outcome({"practice": 0.50}, "practice")),
        ]
        frontier = zero_wrong_frontier(rows, "mean")

        assert frontier["forced_by_query"] == "q"
        assert frontier["threshold"] == pytest.approx(0.50)
        assert frontier["cleared_gate"] == 1

    def test_no_mis_routes_at_all_means_the_lowest_score_is_clean(self) -> None:
        rows = [
            _row("practice", _outcome({"practice": 0.20}, "practice")),
            _row("aggregation", _outcome({"aggregation": 0.60}, "aggregation")),
        ]
        frontier = zero_wrong_frontier(rows, "mean")

        assert frontier["threshold"] == pytest.approx(0.20)
        assert frontier["cleared_gate"] == 2
        assert frontier["forced_by_score"] is None

    def test_a_top_scoring_mis_route_leaves_no_clean_gate(self) -> None:
        """When the highest score is itself wrong, only an empty gate is clean."""
        rows = [
            _row("specific", _outcome({"aggregation": 0.90}, "specific")),
            _row("practice", _outcome({"practice": 0.50}, "practice")),
        ]
        frontier = zero_wrong_frontier(rows, "mean")

        assert frontier["threshold"] is None
        assert frontier["cleared_gate"] == 0

    def test_errored_rows_are_excluded(self) -> None:
        rows = [
            _row("practice", _outcome({"practice": 0.50}, "practice")),
            _row("specific", {}, error="embedding failed"),
        ]
        assert zero_wrong_frontier(rows, "mean")["cleared_gate"] == 1


class TestSummarize:
    def test_production_agreement_is_the_reports_premise(self) -> None:
        agreeing = _row("practice", _outcome({"practice": 0.4}, "practice"))
        agreeing.production_intent = SPECIFIC_LABEL
        agreeing.production_score = 0.4
        agreeing.agrees_with_production = True

        disagreeing = _row("practice", _outcome({"practice": 0.4}, "practice"))
        disagreeing.production_intent = "aggregation"
        disagreeing.production_score = 0.51
        disagreeing.agrees_with_production = False

        report = summarize(
            [agreeing, disagreeing],
            LabelledSet(version=1, ratified=None, queries=()),
            THRESHOLD,
        )

        assert report["production_agreement"]["checked"] == 2
        assert report["production_agreement"]["disagreements"] == 1
        assert report["production_agreement"]["max_score_delta"] == pytest.approx(0.11)

    def test_label_counts_and_errors_are_over_every_row(self) -> None:
        rows = [
            _row("practice", _outcome({"practice": 0.4}, "practice")),
            _row("specific", {}, error="embedding failed"),
        ]
        report = summarize(rows, LabelledSet(version=2, ratified="2026-09-01", queries=()), 0.65)

        assert report["query_set_version"] == 2
        assert report["ratified"] == "2026-09-01"
        assert report["errors"] == 1
        assert report["label_counts"] == {"practice": 1, "specific": 1}
        assert set(report["arms"]) == set(ARMS)


class TestPrintHuman:
    """The DEFAULT output path, and it was untested — which is how a `None`
    format slipped in (Kody, #1206).

    Every field the renderer formats numerically that CAN be None is a crash
    waiting for the run that produces it. These exercise each shape rather than
    asserting exact prose, so they survive wording changes but not a TypeError.
    """

    @staticmethod
    def _report(rows: list[QueryRow]) -> EvalReport:
        return summarize(rows, LabelledSet(version=1, ratified=None, queries=()), THRESHOLD)

    def test_an_arm_with_no_misroutes_anywhere_renders(self, capsys) -> None:
        """The reported crash: no mis-route means no pinning query, and
        `forced_by_score` is None — which `:.3f` cannot format."""
        rows = [
            _row("practice", _outcome({"practice": 0.9}, "practice")),
            _row("aggregation", _outcome({"aggregation": 0.8}, "aggregation")),
        ]

        _print_human(self._report(rows))

        assert "no mis-routes at any gate" in capsys.readouterr().out

    def test_a_pinned_frontier_names_the_query_that_sets_it(self, capsys) -> None:
        rows = [
            _row("specific", _outcome({"aggregation": 0.40}, "specific")),
            _row("practice", _outcome({"practice": 0.90}, "practice")),
        ]

        _print_human(self._report(rows))

        assert "pinned by" in capsys.readouterr().out

    def test_no_clean_gate_renders_its_own_line(self, capsys) -> None:
        """The top-scoring row is itself a mis-route, so only an empty gate is clean."""
        rows = [_row("specific", _outcome({"aggregation": 0.95}, "specific"))]

        _print_human(self._report(rows))

        assert "every cutoff admits a mis-route" in capsys.readouterr().out

    def test_an_errored_row_renders_instead_of_indexing_empty_arms(self, capsys) -> None:
        """An errored row carries NO arms; the renderer must take its error branch."""
        rows = [
            _row("practice", _outcome({"practice": 0.5}, "practice")),
            _row("specific", {}, error="embedding failed"),
        ]

        _print_human(self._report(rows))

        assert "ERROR" in capsys.readouterr().out

    def test_a_draft_set_is_announced_as_not_a_baseline(self, capsys) -> None:
        _print_human(self._report([_row("practice", _outcome({"practice": 0.5}, "practice"))]))

        assert "DRAFT" in capsys.readouterr().out


class TestLabelledQueryShape:
    def test_is_frozen(self) -> None:
        query = LabelledQuery(query="q", label="specific", kind="natural", note="")
        with pytest.raises(AttributeError):
            query.label = "practice"  # type: ignore[misc]
