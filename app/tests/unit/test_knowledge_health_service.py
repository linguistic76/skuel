"""Unit tests for the knowledge-health structural gauge (ADR-080 Horizon-1).

Covers the pure scoring/flagging logic of ``KnowledgeHealthService`` (mocked
backend) and the ``AnalyticsService`` facade delegation. The corpus Cypher itself
is exercised against a real graph in
``tests/integration/test_knowledge_health_instrument.py``.
"""

from __future__ import annotations

import pytest

from core.constants import KnowledgeHealth
from core.ports.query_types import KnowledgeHealthRaw
from core.services.analytics.knowledge_health_service import KnowledgeHealthService
from core.utils.result_simplified import Errors, Result

# Raw measurement of the live dev graph on 2026-07-22 — the numbers ADR-080
# records. Degree excludes learner-state telemetry (Codex #770 P2), so avg is
# 2.157 rather than the all-incident 2.1653; still ≈ the ADR's "~2.17", 17 orphans.
LIVE_RAW: KnowledgeHealthRaw = {
    "total_kus": 121,
    "total_path_steps": 14,
    "total_learning_paths": 2,
    "total_exercises": 15,
    "avg_ku_degree": 2.157,
    "max_ku_degree": 12,
    "orphan_ku_count": 17,
    "orphan_kus": [{"uid": "ku.yoga.prana", "title": "Prana"}],
    "composition_edge_count": 53,
    "composed_ku_count": 47,
    "prerequisite_edge_count": 13,  # 9 PREREQUISITE_FOR (Ku) + 4 REQUIRES_STEP (PathStep)
    "dag_ku_count": 12,
    "dag_max_depth": 2,
    "organizes_edge_count": 0,
    "organized_ku_count": 0,
    "lateral_edge_count": 33,
    "enablement_edge_count": 32,
    "path_steps_with_exercise": 10,
}


def _empty_raw() -> KnowledgeHealthRaw:
    return {
        "total_kus": 0,
        "total_path_steps": 0,
        "total_learning_paths": 0,
        "total_exercises": 0,
        "avg_ku_degree": 0.0,
        "max_ku_degree": 0,
        "orphan_ku_count": 0,
        "orphan_kus": [],
        "composition_edge_count": 0,
        "composed_ku_count": 0,
        "prerequisite_edge_count": 0,
        "dag_ku_count": 0,
        "dag_max_depth": 0,
        "organizes_edge_count": 0,
        "organized_ku_count": 0,
        "lateral_edge_count": 0,
        "enablement_edge_count": 0,
        "path_steps_with_exercise": 0,
    }


def _healthy_raw() -> KnowledgeHealthRaw:
    """A dense, GDS-ready corpus: high degree, no orphans, full coverage."""
    return {
        "total_kus": 100,
        "total_path_steps": 20,
        "total_learning_paths": 5,
        "total_exercises": 40,
        "avg_ku_degree": 7.0,  # > TARGET_AVG_DEGREE
        "max_ku_degree": 20,
        "orphan_ku_count": 0,
        "orphan_kus": [],
        "composition_edge_count": 200,
        "composed_ku_count": 95,
        "prerequisite_edge_count": 180,
        "dag_ku_count": 90,
        "dag_max_depth": 8,
        "organizes_edge_count": 60,
        "organized_ku_count": 80,
        "lateral_edge_count": 150,  # > 1/Ku density
        "enablement_edge_count": 40,
        "path_steps_with_exercise": 19,
    }


class TestBuildReport:
    """The pure fold from raw structural facts to the consolidated report."""

    def test_reproduces_live_adr_numbers(self) -> None:
        report = KnowledgeHealthService._build_report(LIVE_RAW)

        # Node counts + degree pass through verbatim.
        assert report["total_kus"] == 121
        assert report["total_path_steps"] == 14
        assert report["total_learning_paths"] == 2
        assert report["total_exercises"] == 15
        assert report["avg_ku_degree"] == 2.157
        assert report["max_ku_degree"] == 12
        assert report["orphan_ku_count"] == 17

        # Derived ratios.
        assert report["orphan_fraction"] == pytest.approx(0.1405, abs=1e-4)
        assert report["composition"]["coverage"] == pytest.approx(47 / 121)
        assert report["composition"]["edge_count"] == 53
        assert report["composition"]["participating_kus"] == 47
        assert report["prerequisite_dag"]["coverage"] == pytest.approx(12 / 121)
        assert report["prerequisite_dag"]["edge_count"] == 13
        assert report["dag_max_depth"] == 2
        assert report["organizes"]["coverage"] == 0.0
        assert report["lateral_edge_count"] == 33
        assert report["lateral_density"] == pytest.approx(33 / 121, abs=1e-4)
        assert report["enablement_edge_count"] == 32
        assert report["practice_coverage"] == pytest.approx(10 / 14, abs=1e-4)

        # The sparse dev graph is not GDS-ready.
        assert report["gds_ready"] is False
        assert 0.0 < report["gds_readiness_score"] < KnowledgeHealth.GDS_READY_THRESHOLD

    def test_orphan_list_passes_through(self) -> None:
        report = KnowledgeHealthService._build_report(LIVE_RAW)
        assert report["orphan_kus"] == [{"uid": "ku.yoga.prana", "title": "Prana"}]

    def test_score_matches_weighted_formula(self) -> None:
        """The composite is the documented weighted blend of the five signals."""
        report = KnowledgeHealthService._build_report(LIVE_RAW)
        connectivity = min(2.157 / KnowledgeHealth.TARGET_AVG_DEGREE, 1.0)
        non_orphan = 1.0 - 17 / 121
        dag_coverage = 12 / 121
        organizes_coverage = 0.0
        lateral_density = min((33 / 121) / KnowledgeHealth.TARGET_LATERAL_DENSITY, 1.0)
        expected = round(
            KnowledgeHealth.WEIGHT_CONNECTIVITY * connectivity
            + KnowledgeHealth.WEIGHT_NON_ORPHAN * non_orphan
            + KnowledgeHealth.WEIGHT_DAG_COVERAGE * dag_coverage
            + KnowledgeHealth.WEIGHT_ORGANIZES_COVERAGE * organizes_coverage
            + KnowledgeHealth.WEIGHT_LATERAL_DENSITY * lateral_density,
            4,
        )
        assert report["gds_readiness_score"] == expected

    def test_live_flags_surface_the_gaps(self) -> None:
        flags = KnowledgeHealthService._build_report(LIVE_RAW)["flags"]
        joined = " ".join(flags)
        assert "17 orphan Kus" in joined
        assert "Prerequisite DAG is thin" in joined
        assert "No ORGANIZES" in joined
        assert "composed into a PathStep" in joined
        # Practice coverage is 71% (> 50%) → no practice flag.
        assert "close the learning loop" not in joined


class TestEdgeCases:
    def test_empty_graph_is_all_zeros(self) -> None:
        report = KnowledgeHealthService._build_report(_empty_raw())
        assert report["gds_readiness_score"] == 0.0
        assert report["gds_ready"] is False
        assert report["orphan_fraction"] == 0.0
        assert report["composition"]["coverage"] == 0.0
        assert report["practice_coverage"] == 0.0
        assert report["flags"] == [
            "No Kus in the knowledge subgraph yet — ingest curriculum to begin."
        ]

    def test_healthy_graph_is_gds_ready_with_positive_flag(self) -> None:
        report = KnowledgeHealthService._build_report(_healthy_raw())
        assert report["gds_readiness_score"] >= KnowledgeHealth.GDS_READY_THRESHOLD
        assert report["gds_ready"] is True
        assert len(report["flags"]) == 1
        assert "structurally healthy" in report["flags"][0]

    def test_score_is_bounded_0_1(self) -> None:
        # A pathological over-dense graph still clamps to <= 1.0.
        raw = _healthy_raw()
        raw["avg_ku_degree"] = 999.0
        raw["lateral_edge_count"] = 99999
        report = KnowledgeHealthService._build_report(raw)
        assert 0.0 <= report["gds_readiness_score"] <= 1.0

    def test_weights_sum_to_one(self) -> None:
        total = (
            KnowledgeHealth.WEIGHT_CONNECTIVITY
            + KnowledgeHealth.WEIGHT_NON_ORPHAN
            + KnowledgeHealth.WEIGHT_DAG_COVERAGE
            + KnowledgeHealth.WEIGHT_ORGANIZES_COVERAGE
            + KnowledgeHealth.WEIGHT_LATERAL_DENSITY
        )
        assert total == pytest.approx(1.0)


class _FakeBackend:
    """Minimal KnowledgeHealthOperations stub."""

    def __init__(self, result: Result) -> None:
        self._result = result

    async def measure_knowledge_subgraph(self) -> Result:
        return self._result


class TestServiceAsyncPath:
    @pytest.mark.asyncio
    async def test_analyze_returns_report(self) -> None:
        service = KnowledgeHealthService(backend=_FakeBackend(Result.ok(LIVE_RAW)))
        result = await service.analyze_knowledge_subgraph_health()
        assert result.is_ok
        assert result.value["total_kus"] == 121
        assert result.value["orphan_ku_count"] == 17

    @pytest.mark.asyncio
    async def test_analyze_propagates_backend_error(self) -> None:
        service = KnowledgeHealthService(
            backend=_FakeBackend(Result.fail(Errors.database(operation="measure", message="boom")))
        )
        result = await service.analyze_knowledge_subgraph_health()
        assert result.is_error


class TestFacadeDelegation:
    @pytest.mark.asyncio
    async def test_facade_delegates_when_wired(self) -> None:
        from core.services.analytics_service import AnalyticsService

        facade = AnalyticsService(knowledge_health_backend=_FakeBackend(Result.ok(LIVE_RAW)))
        result = await facade.analyze_knowledge_subgraph_health()
        assert result.is_ok
        assert result.value["total_kus"] == 121

    @pytest.mark.asyncio
    async def test_facade_errors_when_unwired(self) -> None:
        from core.services.analytics_service import AnalyticsService

        facade = AnalyticsService()  # no knowledge_health_backend
        assert facade.knowledge_health is None
        result = await facade.analyze_knowledge_subgraph_health()
        assert result.is_error
