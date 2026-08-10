"""
Knowledge-Health Service
========================

The Horizon-1 structural-health gauge over the knowledge subgraph (ADR-080).

A ``BaseAnalyticsService`` (no AI, CORE-tier safe): it consumes the raw structural
facts the ``KnowledgeHealthBackend`` measures and derives coverage ratios, a
composite GDS-readiness score, and human-readable authoring-guidance flags.

It serves two audiences from one report:
- **Authoring today** — flags the orphan Kus, the near-empty prerequisite DAG,
  the missing ORGANIZES/MOC hierarchy, and under-composed / un-practised content
  as concrete gaps to fill.
- **GDS-readiness for Horizon 2** — the composite score is the density signal
  ADR-080's "when to revisit" gate reads: GDS (centrality / shortest-path /
  community detection) says nothing useful until the graph is dense enough.

See: /docs/decisions/ADR-080-auradb-three-horizon-strategy.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.constants import KnowledgeHealth
from core.models.ku.ku import Ku
from core.ports.knowledge_health_protocols import KnowledgeHealthOperations
from core.services.base_analytics_service import BaseAnalyticsService
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.ports.query_types import (
        KnowledgeCoverageMetric,
        KnowledgeHealthRaw,
        KnowledgeHealthReport,
    )


def _ratio(numerator: int, denominator: int) -> float:
    """Safe fraction — 0.0 when the denominator is zero (empty corpus)."""
    return numerator / denominator if denominator else 0.0


class KnowledgeHealthService(BaseAnalyticsService[KnowledgeHealthOperations, Ku]):
    """Corpus-level structural-health analytics for the knowledge subgraph.

    Pure graph analytics — no LLM/embedding dependency (ADR-043 CORE tier). The
    single public method fetches the raw measurement from the backend and folds
    it into a :class:`KnowledgeHealthReport`; all scoring is deterministic Python.
    """

    _service_name = "knowledge_health"

    async def analyze_knowledge_subgraph_health(self) -> Result[KnowledgeHealthReport]:
        """Produce the consolidated structural-health report.

        Backend: ``KnowledgeHealthBackend.measure_knowledge_subgraph`` (one
        round-trip corpus query). This layer interprets the raw facts — coverage
        ratios, the composite readiness score, and authoring flags.
        """
        raw_result = await self.backend.measure_knowledge_subgraph()
        if raw_result.is_error:
            return Result.fail(raw_result)
        return Result.ok(self._build_report(raw_result.value))

    # ------------------------------------------------------------------
    # PURE COMPUTATION (sync — no I/O, SKUEL029)
    # ------------------------------------------------------------------

    @staticmethod
    def _coverage(
        edge_count: int, participating_kus: int, total_kus: int
    ) -> KnowledgeCoverageMetric:
        """One structural coverage slice — edges, participating Kus, coverage ratio."""
        return {
            "edge_count": edge_count,
            "participating_kus": participating_kus,
            "coverage": _ratio(participating_kus, total_kus),
        }

    @classmethod
    def _gds_readiness_score(
        cls,
        *,
        avg_ku_degree: float,
        non_orphan_fraction: float,
        dag_coverage: float,
        organizes_coverage: float,
        lateral_density: float,
    ) -> float:
        """Blend five normalized structural signals into a 0.0-1.0 readiness score.

        Each signal saturates at 1.0; the weights (from ``KnowledgeHealth``) sum
        to 1.0. Connectivity and a real prerequisite DAG lead; ORGANIZES/MOC and
        lateral density refine; orphans penalize. ``non_orphan_fraction`` is the
        share of Kus that are connected (0.0 for an empty corpus, so a graph with
        no Kus scores 0.0 — it does not earn "no orphans" credit for being empty).
        This is the density gate ADR-080's Horizon-2 trigger reads.
        """
        connectivity = min(avg_ku_degree / KnowledgeHealth.TARGET_AVG_DEGREE, 1.0)
        lateral_norm = min(lateral_density / KnowledgeHealth.TARGET_LATERAL_DENSITY, 1.0)

        score = (
            KnowledgeHealth.WEIGHT_CONNECTIVITY * connectivity
            + KnowledgeHealth.WEIGHT_NON_ORPHAN * non_orphan_fraction
            + KnowledgeHealth.WEIGHT_DAG_COVERAGE * dag_coverage
            + KnowledgeHealth.WEIGHT_ORGANIZES_COVERAGE * organizes_coverage
            + KnowledgeHealth.WEIGHT_LATERAL_DENSITY * lateral_norm
        )
        return round(max(0.0, min(score, 1.0)), 4)

    @staticmethod
    def _authoring_flags(
        raw: KnowledgeHealthRaw,
        *,
        orphan_fraction: float,
        composition_coverage: float,
        dag_coverage: float,
        practice_coverage: float,
        gds_ready: bool,
    ) -> list[str]:
        """Human-readable content-gap guidance for the curriculum author.

        Silent when a signal is healthy; a graph clearing every bar gets a single
        positive line so the panel is never blank.
        """
        total_kus = raw["total_kus"]
        if total_kus == 0:
            return ["No Kus in the knowledge subgraph yet — ingest curriculum to begin."]

        flags: list[str] = []

        if orphan_fraction > KnowledgeHealth.ORPHAN_FLAG_FRACTION:
            flags.append(
                f"{raw['orphan_ku_count']} orphan Kus ({orphan_fraction:.0%}) — compose them "
                "into PathSteps or add prerequisite / lateral links."
            )
        if dag_coverage < KnowledgeHealth.MIN_HEALTHY_DAG_COVERAGE:
            flags.append(
                f"Prerequisite DAG is thin: {raw['prerequisite_edge_count']} edges spanning "
                f"{raw['dag_ku_count']}/{total_kus} Kus — author more prerequisites."
            )
        if raw["organizes_edge_count"] == 0:
            flags.append(
                "No ORGANIZES / MOC hierarchy — author Maps of Content to cluster related Kus."
            )
        if composition_coverage < KnowledgeHealth.MIN_HEALTHY_COMPOSITION_COVERAGE:
            flags.append(
                f"Only {raw['composed_ku_count']}/{total_kus} Kus are composed into a PathStep — "
                "weave isolated concepts into curriculum content."
            )
        if (
            raw["total_path_steps"] > 0
            and practice_coverage < KnowledgeHealth.MIN_HEALTHY_PRACTICE_COVERAGE
        ):
            flags.append(
                f"{raw['path_steps_with_exercise']}/{raw['total_path_steps']} PathSteps anchor an "
                "exercise — add exercises to close the learning loop."
            )

        if not flags:
            flags.append(
                "Knowledge subgraph is structurally healthy"
                + (" and GDS-ready." if gds_ready else ".")
            )
        return flags

    @classmethod
    def _build_report(cls, raw: KnowledgeHealthRaw) -> KnowledgeHealthReport:
        """Fold the raw structural facts into the consolidated report."""
        total_kus = raw["total_kus"]
        total_path_steps = raw["total_path_steps"]

        orphan_fraction = _ratio(raw["orphan_ku_count"], total_kus)
        # Share of Kus that ARE connected — a ratio, so an empty corpus is 0.0
        # (no "no orphans" credit for having no Kus at all).
        non_orphan_fraction = _ratio(total_kus - raw["orphan_ku_count"], total_kus)
        composition_coverage = _ratio(raw["composed_ku_count"], total_kus)
        dag_coverage = _ratio(raw["dag_ku_count"], total_kus)
        organizes_coverage = _ratio(raw["organized_ku_count"], total_kus)
        lateral_density = _ratio(raw["lateral_edge_count"], total_kus)
        practice_coverage = _ratio(raw["path_steps_with_exercise"], total_path_steps)

        score = cls._gds_readiness_score(
            avg_ku_degree=raw["avg_ku_degree"],
            non_orphan_fraction=non_orphan_fraction,
            dag_coverage=dag_coverage,
            organizes_coverage=organizes_coverage,
            lateral_density=lateral_density,
        )
        gds_ready = score >= KnowledgeHealth.GDS_READY_THRESHOLD

        flags = cls._authoring_flags(
            raw,
            orphan_fraction=orphan_fraction,
            composition_coverage=composition_coverage,
            dag_coverage=dag_coverage,
            practice_coverage=practice_coverage,
            gds_ready=gds_ready,
        )

        return {
            "total_kus": total_kus,
            "total_path_steps": total_path_steps,
            "total_learning_paths": raw["total_learning_paths"],
            "total_exercises": raw["total_exercises"],
            "avg_ku_degree": raw["avg_ku_degree"],
            "max_ku_degree": raw["max_ku_degree"],
            "orphan_ku_count": raw["orphan_ku_count"],
            "orphan_fraction": round(orphan_fraction, 4),
            "orphan_kus": raw["orphan_kus"],
            "composition": cls._coverage(
                raw["composition_edge_count"], raw["composed_ku_count"], total_kus
            ),
            "prerequisite_dag": cls._coverage(
                raw["prerequisite_edge_count"], raw["dag_ku_count"], total_kus
            ),
            "dag_max_depth": raw["dag_max_depth"],
            "organizes": cls._coverage(
                raw["organizes_edge_count"], raw["organized_ku_count"], total_kus
            ),
            "lateral_edge_count": raw["lateral_edge_count"],
            "lateral_density": round(lateral_density, 4),
            "enablement_edge_count": raw["enablement_edge_count"],
            "exercise_count": raw["total_exercises"],
            "path_steps_with_exercise": raw["path_steps_with_exercise"],
            "practice_coverage": round(practice_coverage, 4),
            # Curriculum marked ``publication_state: draft`` — INCLUDED in the
            # totals above, reported separately. This gauge is authoring
            # guidance, so unfinished work is exactly what its author needs to
            # see; learner-facing surfaces withhold it instead.
            "draft_curriculum_count": raw["draft_curriculum_count"],
            "gds_readiness_score": score,
            "gds_ready": gds_ready,
            "flags": flags,
        }
