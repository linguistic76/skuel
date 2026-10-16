"""Tests for PrereqSuggestionService (Discovery Analytics PR 4).

Covers:
- Candidate band selection: mid-band kept, out-of-band dropped, already-edged
  pairs excluded BOTH directions, transitively-covered pairs excluded,
  per-Ku cap + max_pairs bounds, no-embeddings fail-soft message
- Edge YAML rendering: exact authored format, colon reverse-normalization,
  rationale newline sanitization (no frontmatter injection)
- LLM judge: fenced-JSON parsing, verdict mapping (incl. skip), malformed
  batch fail-soft, all-batches-failed → integration error, CORE degrade
- ready_edge_files(): one file per way to record a pair, direction kept,
  symmetric pairs canonicalized; the queue row shows them and writes nothing
"""

from __future__ import annotations

import math
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.relationship_names import RelationshipName
from core.ports.query_types import KuEdgeRow, KuEmbeddingRow
from core.services.prereq_suggestion_service import (
    EdgeChoice,
    JudgeVerdict,
    PrereqSuggestion,
    PrereqSuggestionConfig,
    PrereqSuggestionService,
    edge_filename,
    ready_edge_files,
    render_edge_yaml,
)
from core.utils.result_simplified import Result


def _vec(theta_degrees: float) -> list[float]:
    """2D unit vector — pairwise cosine == cos(angle difference)."""
    theta = math.radians(theta_degrees)
    return [math.cos(theta), math.sin(theta)]


def _ku(uid: str, theta: float, title: str | None = None) -> KuEmbeddingRow:
    return KuEmbeddingRow(
        uid=uid, title=title or uid, summary=f"summary of {uid}", embedding=_vec(theta)
    )


def _service(
    kus: list[KuEmbeddingRow],
    edges: list[KuEdgeRow] | None = None,
    llm: MagicMock | None = None,
    config: PrereqSuggestionConfig | None = None,
) -> PrereqSuggestionService:
    backend = MagicMock()
    backend.get_kus_with_embeddings = AsyncMock(return_value=Result.ok(kus))
    backend.get_ku_ku_edges = AsyncMock(return_value=Result.ok(edges or []))
    return PrereqSuggestionService(backend=backend, llm_service=llm, config=config)


def _llm_with_response(text: str) -> MagicMock:
    llm = MagicMock()
    completion = MagicMock()
    completion.text = text
    llm.caller.complete = AsyncMock(return_value=Result.ok(completion))
    return llm


# ============================================================================
# Candidate band selection
# ============================================================================


@pytest.mark.anyio
async def test_band_keeps_mid_similarity_pair_only() -> None:
    """cos 0°Δ=1.0 (too high), 55°Δ≈0.57 (in band), 85°Δ≈0.09 (too low)."""
    kus = [_ku("ku.a.one", 0.0), _ku("ku.a.two", 55.0), _ku("ku.a.three", 140.0)]
    service = _service(kus)

    result = await service.generate_candidates()

    assert not result.is_error
    pairs = {(c.a_uid, c.b_uid) for c in result.value}
    assert pairs == {("ku.a.one", "ku.a.two")}
    assert 0.40 <= result.value[0].similarity < 0.72


@pytest.mark.anyio
async def test_already_edged_pairs_excluded_both_directions() -> None:
    """A direct edge of ANY type excludes the pair, whichever direction it points."""
    kus = [_ku("ku.a.one", 0.0), _ku("ku.a.two", 55.0), _ku("ku.a.three", 110.0)]
    # one→two authored; three→two authored (reverse of pair order two/three)
    edges = [
        KuEdgeRow(from_uid="ku.a.one", to_uid="ku.a.two", rel_type="RELATED_TO"),
        KuEdgeRow(from_uid="ku.a.three", to_uid="ku.a.two", rel_type="ENABLES"),
    ]
    service = _service(kus, edges)

    result = await service.generate_candidates()

    assert not result.is_error
    # one↔two (cos≈0.57) and two↔three (cos≈0.57) both in band but both edged;
    # one↔three (cos ~ -0.34) out of band → nothing survives.
    assert result.value == []


@pytest.mark.anyio
async def test_transitively_covered_pair_excluded() -> None:
    """An authored directed path a→c→b covers the a↔b pair (Phase A ruling)."""
    kus = [_ku("ku.a.one", 0.0), _ku("ku.a.two", 55.0), _ku("ku.a.mid", 150.0)]
    edges = [
        KuEdgeRow(from_uid="ku.a.one", to_uid="ku.a.mid", rel_type="PREREQUISITE_FOR"),
        KuEdgeRow(from_uid="ku.a.mid", to_uid="ku.a.two", rel_type="PREREQUISITE_FOR"),
    ]
    service = _service(kus, edges)

    result = await service.generate_candidates()

    assert not result.is_error
    assert result.value == []


@pytest.mark.anyio
async def test_max_pairs_and_per_ku_cap_bound_output() -> None:
    """The global max_pairs cap truncates, keeping the highest-similarity pairs."""
    # Five Kus spread so consecutive pairs are in band
    kus = [_ku(f"ku.a.k{i}", i * 50.0) for i in range(5)]
    config = PrereqSuggestionConfig(per_ku_cap=1, max_pairs=2)
    service = _service(kus, config=config)

    result = await service.generate_candidates()

    assert not result.is_error
    assert 0 < len(result.value) <= 2


@pytest.mark.anyio
async def test_no_embeddings_fails_soft_with_clear_message() -> None:
    service = _service(kus=[])

    result = await service.generate_candidates()

    assert result.is_error
    assert "No Ku embeddings" in result.expect_error().message


# ============================================================================
# Edge YAML rendering
# ============================================================================


def test_render_edge_yaml_exact_authored_format() -> None:
    """Edge YAMLs author the STORED dot form directly (authored = stored;
    colon spelling retired 2026-08-14 — denormalize_uid deleted with it)."""
    content = render_edge_yaml(
        "ku.mindfulness.attention",
        "ku.mindfulness.labeling",
        RelationshipName.PREREQUISITE_FOR,
        rationale="Labeling requires attentional stability.",
    )
    assert content == (
        "---\n"
        "# Edge: ku.mindfulness.attention -> PREREQUISITE_FOR -> ku.mindfulness.labeling\n"
        "# Labeling requires attentional stability.\n"
        "type: Edge\n"
        "\n"
        "from: ku.mindfulness.attention\n"
        "to: ku.mindfulness.labeling\n"
        "relationship: PREREQUISITE_FOR\n"
        "\n"
        "source: inferred-approved\n"
        "\n"
        "---\n"
    )


def test_rationale_newlines_cannot_inject_frontmatter() -> None:
    content = render_edge_yaml(
        "ku.a.one",
        "ku.a.two",
        RelationshipName.RELATED_TO,
        rationale="evil\nfrom: ku.x.y\nto: ku.z.w",
    )
    # The injected lines are collapsed into the single comment line — the only
    # line-start (parseable) from:/to: keys are the legitimate ones.
    assert "\nfrom: ku.x.y" not in content
    assert "\nfrom: ku.a.one\n" in content
    assert [ln for ln in content.splitlines() if ln.startswith("from:")] == ["from: ku.a.one"]
    assert [ln for ln in content.splitlines() if ln.startswith("to:")] == ["to: ku.a.two"]
    assert "# evil from: ku.x.y to: ku.z.w" in content


def test_edge_filename_slugs() -> None:
    assert (
        edge_filename("ku.mind.attention", "ku.mind.labeling", RelationshipName.PREREQUISITE_FOR)
        == "edge_attention-prereq-labeling.md"
    )
    assert (
        edge_filename("ku.a.one", "ku.b.two", RelationshipName.COMPLEMENTARY_TO)
        == "edge_one-complements-two.md"
    )


# ============================================================================
# LLM judge
# ============================================================================

_TWO_KUS = [_ku("ku.a.one", 0.0, title="One"), _ku("ku.a.two", 55.0, title="Two")]


@pytest.mark.anyio
async def test_judge_maps_verdicts_and_parses_fenced_json() -> None:
    llm = _llm_with_response(
        '```json\n[{"index": 1, "verdict": "prereq_b_to_a", "rationale": "Two grounds One"}]\n```'
    )
    service = _service(_TWO_KUS, llm=llm)

    result = await service.generate_suggestions()

    assert not result.is_error
    run = result.value
    assert run.judged is True
    assert run.candidate_count == 1
    assert len(run.suggestions) == 1
    suggestion = run.suggestions[0]
    assert suggestion.verdict is JudgeVerdict.PREREQ_B_TO_A
    assert suggestion.rationale == "Two grounds One"


@pytest.mark.anyio
async def test_judge_skip_verdict_drops_pair_and_counts_it() -> None:
    llm = _llm_with_response('[{"index": 1, "verdict": "skip", "rationale": "superficial"}]')
    service = _service(_TWO_KUS, llm=llm)

    result = await service.generate_suggestions()

    assert not result.is_error
    assert result.value.suggestions == ()
    assert result.value.skipped_by_judge == 1
    assert result.value.judge_failures == 0


@pytest.mark.anyio
async def test_judge_malformed_json_fails_whole_run_when_only_batch() -> None:
    llm = _llm_with_response("I think pair 1 is a prerequisite because...")
    service = _service(_TWO_KUS, llm=llm)

    result = await service.generate_suggestions()

    assert result.is_error  # every candidate lost to judge failures


@pytest.mark.anyio
async def test_judge_invalid_verdict_counts_as_failure_not_crash() -> None:
    llm = _llm_with_response(
        '[{"index": 1, "verdict": "maybe?", "rationale": "x"},'
        ' {"index": 99, "verdict": "related", "rationale": "out of range"}]'
    )
    service = _service(_TWO_KUS, llm=llm)

    result = await service.generate_suggestions()

    assert result.is_error  # single batch, its only candidate failed


@pytest.mark.anyio
async def test_judge_one_bad_batch_does_not_sink_the_other() -> None:
    kus = [
        _ku("ku.a.one", 0.0, title="One"),
        _ku("ku.a.two", 55.0, title="Two"),
        _ku("ku.a.three", 110.0, title="Three"),
    ]
    # Pairs in band: one↔two and two↔three → batch_size=1 forces 2 batches
    llm = MagicMock()
    good = MagicMock()
    good.text = '[{"index": 1, "verdict": "related", "rationale": "linked"}]'
    llm.caller.complete = AsyncMock(
        side_effect=[Result.ok(good), Result.ok(MagicMock(text="not json"))]
    )
    config = PrereqSuggestionConfig(judge_batch_size=1, judge_concurrency=1)
    service = _service(kus, llm=llm, config=config)

    result = await service.generate_suggestions()

    assert not result.is_error
    run = result.value
    assert len(run.suggestions) == 1
    assert run.suggestions[0].verdict is JudgeVerdict.RELATED
    assert run.judge_failures == 1


@pytest.mark.anyio
async def test_core_degrade_returns_unjudged_suggestions() -> None:
    """No LLM (CORE tier) → undirected pairs, judged=False, verdict None."""
    service = _service(_TWO_KUS, llm=None)

    result = await service.generate_suggestions()

    assert not result.is_error
    run = result.value
    assert run.judged is False
    assert len(run.suggestions) == 1
    assert run.suggestions[0].verdict is None
    assert run.suggestions[0].rationale is None


# ============================================================================
# ready_edge_files()
# ============================================================================


def _suggestion(
    a_uid: str = "ku.a.one",
    b_uid: str = "ku.a.two",
    verdict: JudgeVerdict | None = None,
    rationale: str | None = "One grounds Two",
) -> PrereqSuggestion:
    return PrereqSuggestion(
        a_uid=a_uid,
        a_title=a_uid.rsplit(".", 1)[-1].title(),
        b_uid=b_uid,
        b_title=b_uid.rsplit(".", 1)[-1].title(),
        similarity=0.55,
        verdict=verdict,
        rationale=rationale,
    )


def test_one_ready_file_per_choice_each_rendered_as_authored() -> None:
    files = {f.choice: f for f in ready_edge_files(_suggestion())}

    assert list(files) == list(EdgeChoice)
    expected = {
        EdgeChoice.PREREQ_A_TO_B: ("ku.a.one", "ku.a.two", RelationshipName.PREREQUISITE_FOR),
        EdgeChoice.PREREQ_B_TO_A: ("ku.a.two", "ku.a.one", RelationshipName.PREREQUISITE_FOR),
        EdgeChoice.RELATED: ("ku.a.one", "ku.a.two", RelationshipName.RELATED_TO),
        EdgeChoice.COMPLEMENTARY: ("ku.a.one", "ku.a.two", RelationshipName.COMPLEMENTARY_TO),
    }
    for choice, (from_uid, to_uid, rel) in expected.items():
        assert files[choice].filename == edge_filename(from_uid, to_uid, rel)
        assert files[choice].content == render_edge_yaml(
            from_uid, to_uid, rel, rationale="One grounds Two"
        )


def test_a_symmetric_file_is_the_same_whichever_order_the_run_emitted() -> None:
    """A generate run can emit a pair in either order; one edge is one file."""
    forward = {
        f.choice: (f.filename, f.content)
        for f in ready_edge_files(_suggestion("ku.a.one", "ku.a.two"))
    }
    reverse = {
        f.choice: (f.filename, f.content)
        for f in ready_edge_files(_suggestion("ku.a.two", "ku.a.one"))
    }

    for choice in (EdgeChoice.RELATED, EdgeChoice.COMPLEMENTARY):
        assert forward[choice] == reverse[choice]
    # Direction is meaning: the prereq files swap with the pair.
    assert forward[EdgeChoice.PREREQ_A_TO_B] == reverse[EdgeChoice.PREREQ_B_TO_A]


def test_every_ready_file_passes_sync_validation() -> None:
    """A ready file that failed the ingestion gate would never land in the graph."""
    import yaml

    from core.services.ingestion.validator import validate_edge_data

    for ready in ready_edge_files(_suggestion()):
        data = yaml.safe_load(ready.content.split("---")[1])
        assert validate_edge_data(data).is_ok, ready.filename
        assert data["source"] == "inferred-approved"


def test_a_judged_row_shows_its_verdicts_file_and_writes_nothing() -> None:
    """The row offers the ready files and a copy button; no form posts anywhere."""
    from fasthtml.common import to_xml

    from ui.admin.prereq_views import AdminPrereqComponents

    suggestion = _suggestion(verdict=JudgeVerdict.PREREQ_B_TO_A)
    html = to_xml(AdminPrereqComponents.render_suggestion_row(suggestion, 0))

    assert "hx-post" not in html and "<form" not in html
    assert "Copy file" in html
    for ready in ready_edge_files(suggestion):
        assert f"edges/{ready.filename}" in html
        assert f"choice === &#x27;{ready.choice.value}&#x27;" in html or (
            f"choice === '{ready.choice.value}'" in html
        )
    assert 'choice: "prereq_b_to_a"' in html.replace("&quot;", '"')


@pytest.mark.anyio
async def test_stale_dimension_embeddings_dropped_not_crashed() -> None:
    """A single stale-dimension vector must not 500 generation (Codex P2 #599).

    A model/dimension change can leave one old-length embedding until the
    backfill sweeps; the strict pairwise scorer would raise on it. The
    dominant dimension survives, the stale row is dropped.
    """
    kus = [
        _ku("ku.a.one", 0.0),
        _ku("ku.a.two", 55.0),
        KuEmbeddingRow(
            uid="ku.a.stale",
            title="Stale",
            summary="old-model vector",
            embedding=[0.5, 0.5, 0.5],  # wrong dimension vs _vec()'s
        ),
    ]
    service = _service(kus)

    result = await service.generate_candidates()

    assert not result.is_error
    uids = {uid for cand in result.value for uid in (cand.a_uid, cand.b_uid)}
    assert "ku.a.stale" not in uids
    assert uids  # the two healthy Kus still produced their mid-band pair


def test_unjudged_row_renders_disabled_placeholder() -> None:
    """CORE-mode rows must not silently default to a directed prereq (Codex P2 #599)."""
    from fasthtml.common import to_xml

    from ui.admin.prereq_views import AdminPrereqComponents

    unjudged = PrereqSuggestion(
        a_uid="ku.a.one",
        a_title="One",
        b_uid="ku.a.two",
        b_title="Two",
        similarity=0.55,
        verdict=None,
        rationale=None,
    )
    html = to_xml(AdminPrereqComponents.render_suggestion_row(unjudged, 0))

    assert "Choose relation…" in html
    assert 'value=""' in html and "disabled" in html
    # No real option may carry selected — only the placeholder does
    assert html.count("selected") == 1
