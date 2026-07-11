"""Tests for PrereqSuggestionService (Discovery Analytics PR 4).

Covers:
- Candidate band selection: mid-band kept, out-of-band dropped, already-edged
  pairs excluded BOTH directions, transitively-covered pairs excluded,
  per-Ku cap + max_pairs bounds, no-embeddings fail-soft message
- Edge YAML rendering: exact authored format, colon reverse-normalization,
  rationale newline sanitization (no frontmatter injection)
- LLM judge: fenced-JSON parsing, verdict mapping (incl. skip), malformed
  batch fail-soft, all-batches-failed → integration error, CORE degrade
- approve(): relationship allowlist, existence check, writer invocation
"""

from __future__ import annotations

import math
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.relationship_names import RelationshipName
from core.ports.query_types import KuEdgeRow, KuEmbeddingRow
from core.services.prereq_suggestion_service import (
    APPROVABLE_RELATIONSHIPS,
    JudgeVerdict,
    PrereqSuggestionConfig,
    PrereqSuggestionService,
    denormalize_uid,
    edge_filename,
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
    writer: MagicMock | None = None,
) -> PrereqSuggestionService:
    backend = MagicMock()
    backend.get_kus_with_embeddings = AsyncMock(return_value=Result.ok(kus))
    backend.get_ku_ku_edges = AsyncMock(return_value=Result.ok(edges or []))
    backend.get_ku_titles = AsyncMock(
        return_value=Result.ok({ku["uid"]: ku["title"] for ku in kus})
    )
    edge_writer = writer or MagicMock()
    if writer is None:
        edge_writer.write_edge_file = AsyncMock(return_value=Result.ok("/vault/edges/x.md"))
    return PrereqSuggestionService(
        backend=backend, edge_writer=edge_writer, llm_service=llm, config=config
    )


def _llm_with_response(text: str) -> MagicMock:
    llm = MagicMock()
    completion = MagicMock()
    completion.text = text
    llm.chat_port.complete = AsyncMock(return_value=Result.ok(completion))
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
    content = render_edge_yaml(
        "ku.mindfulness.attention",
        "ku.mindfulness.labeling",
        RelationshipName.PREREQUISITE_FOR,
        rationale="Labeling requires attentional stability.",
    )
    assert content == (
        "---\n"
        "# Edge: ku:mindfulness:attention -> PREREQUISITE_FOR -> ku:mindfulness:labeling\n"
        "# Labeling requires attentional stability.\n"
        "type: Edge\n"
        "\n"
        "from: ku:mindfulness:attention\n"
        "to: ku:mindfulness:labeling\n"
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
        rationale="evil\nfrom: ku:x:y\nto: ku:z:w",
    )
    # The injected lines are collapsed into the single comment line — the only
    # line-start (parseable) from:/to: keys are the legitimate ones.
    assert "\nfrom: ku:x:y" not in content
    assert "\nfrom: ku:a:one\n" in content
    assert [ln for ln in content.splitlines() if ln.startswith("from:")] == ["from: ku:a:one"]
    assert [ln for ln in content.splitlines() if ln.startswith("to:")] == ["to: ku:a:two"]
    assert "# evil from: ku:x:y to: ku:z:w" in content


def test_denormalize_uid_and_filename() -> None:
    assert denormalize_uid("ku.mindfulness.attention") == "ku:mindfulness:attention"
    # Generated-form UIDs (dotless) pass through unchanged — round-trip holds
    assert denormalize_uid("ku_deep-work_a1b2c3") == "ku_deep-work_a1b2c3"
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
    llm.chat_port.complete = AsyncMock(
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
# approve()
# ============================================================================


@pytest.mark.anyio
async def test_approve_writes_rendered_yaml_via_writer() -> None:
    writer = MagicMock()
    writer.write_edge_file = AsyncMock(
        return_value=Result.ok("/vault/edges/edge_one-prereq-two.md")
    )
    service = _service(_TWO_KUS, writer=writer)

    result = await service.approve(
        from_uid="ku.a.one",
        to_uid="ku.a.two",
        relationship="PREREQUISITE_FOR",
        rationale="One grounds Two",
    )

    assert not result.is_error
    assert result.value == "/vault/edges/edge_one-prereq-two.md"
    writer.write_edge_file.assert_awaited_once()
    filename, content = writer.write_edge_file.await_args.args
    assert filename == "edge_one-prereq-two.md"
    assert "from: ku:a:one" in content
    assert "to: ku:a:two" in content
    assert "relationship: PREREQUISITE_FOR" in content
    assert "source: inferred-approved" in content


@pytest.mark.anyio
async def test_approve_rejects_unlisted_relationship() -> None:
    writer = MagicMock()
    writer.write_edge_file = AsyncMock()
    service = _service(_TWO_KUS, writer=writer)

    result = await service.approve(from_uid="ku.a.one", to_uid="ku.a.two", relationship="ENABLES")

    assert result.is_error
    writer.write_edge_file.assert_not_awaited()


@pytest.mark.anyio
async def test_approve_rejects_unknown_ku() -> None:
    writer = MagicMock()
    writer.write_edge_file = AsyncMock()
    service = _service(_TWO_KUS, writer=writer)

    result = await service.approve(
        from_uid="ku.a.one", to_uid="ku.a.ghost", relationship="RELATED_TO"
    )

    assert result.is_error
    assert result.expect_error().category.value == "not_found"
    writer.write_edge_file.assert_not_awaited()


@pytest.mark.anyio
async def test_approve_rejects_self_edge() -> None:
    writer = MagicMock()
    writer.write_edge_file = AsyncMock()
    service = _service(_TWO_KUS, writer=writer)

    result = await service.approve(
        from_uid="ku.a.one", to_uid="ku.a.one", relationship="RELATED_TO"
    )

    assert result.is_error
    writer.write_edge_file.assert_not_awaited()


def test_approvable_relationships_are_the_ruled_three() -> None:
    assert set(APPROVABLE_RELATIONSHIPS) == {
        "PREREQUISITE_FOR",
        "RELATED_TO",
        "COMPLEMENTARY_TO",
    }


def test_rendered_yaml_passes_sync_validation() -> None:
    """The approved file must survive content-vault sync (Codex P1 #599).

    validate_edge_data is the gate every Edge YAML passes at ingestion —
    a rendered file that fails it would silently never land in the graph.
    """
    import yaml

    from core.services.ingestion.validator import validate_edge_data

    content = render_edge_yaml(
        "ku.sel.empathy",
        "ku.sel.compassion",
        RelationshipName.PREREQUISITE_FOR,
        rationale="Compassion is empathy plus the motivation to act.",
    )
    frontmatter = content.split("---")[1]
    data = yaml.safe_load(frontmatter)

    result = validate_edge_data(data)
    assert result.is_ok, f"rendered Edge YAML failed sync validation: {result}"
    assert data["source"] == "inferred-approved"


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


@pytest.mark.anyio
async def test_symmetric_approve_canonicalizes_pair_order() -> None:
    """RELATED_TO approve must yield ONE filename regardless of A/B order (Codex P2 #599).

    Generate runs can emit the same pair in either order; without
    canonicalization the no-overwrite guard can't see a reverse duplicate.
    """
    writer = MagicMock()
    writer.write_edge_file = AsyncMock(return_value=Result.ok("/vault/edges/x.md"))
    service = _service(_TWO_KUS, writer=writer)

    await service.approve(from_uid="ku.a.two", to_uid="ku.a.one", relationship="RELATED_TO")
    reversed_call = writer.write_edge_file.await_args.args
    await service.approve(from_uid="ku.a.one", to_uid="ku.a.two", relationship="RELATED_TO")
    forward_call = writer.write_edge_file.await_args.args

    assert reversed_call == forward_call  # same (filename, content) both ways


@pytest.mark.anyio
async def test_directional_approve_preserves_order() -> None:
    """PREREQUISITE_FOR direction is meaning — canonicalization must NOT touch it."""
    writer = MagicMock()
    writer.write_edge_file = AsyncMock(return_value=Result.ok("/vault/edges/x.md"))
    service = _service(_TWO_KUS, writer=writer)

    await service.approve(from_uid="ku.a.two", to_uid="ku.a.one", relationship="PREREQUISITE_FOR")

    filename = writer.write_edge_file.await_args.args[0]
    assert "two" in filename.split("-prereq-")[0]
