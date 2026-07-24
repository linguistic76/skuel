"""
Tests for SURFACE_CONNECTION relationship evidence.

Covers the real Ku↔Ku lateral-edge pipeline end to end at the unit level:
- ContextRetriever._fetch_ku_lateral_edges — shape, dedupe, failure guards
- ResponseGenerator._build_exploratory_prompt — titled-pair rendering with
  authored evidence, evidence-less edges, and the empty fallback
- IntentClassifier edge-connected check — matches BOTH endpoints of an edge
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.askesis.pedagogical_intent import PedagogicalIntent
from core.models.enums import GuidanceMode
from core.services.askesis.context_retriever import ContextRetriever
from core.services.askesis.intent_classifier import GuidanceDetermination, IntentClassifier
from core.services.askesis.response_generator import ResponseGenerator
from core.utils.result_simplified import Errors, Result

# ============================================================================
# HELPERS
# ============================================================================


def _make_retriever(edge_records: list[dict[str, Any]] | None = None) -> ContextRetriever:
    """ContextRetriever whose ps_backend returns the given lateral-edge records."""
    ps_backend = MagicMock()
    ps_backend.get_ku_lateral_edges = AsyncMock(return_value=Result.ok(edge_records or []))
    ps_backend.get_cited_resources = AsyncMock(return_value=Result.ok([]))
    return ContextRetriever(
        graph_intel=MagicMock(),
        embeddings_service=MagicMock(),
        ps_backend=ps_backend,
    )


def _edge_record(
    source_uid: str = "ku.mindfulness.anchor",
    source_title: str = "Anchor",
    target_uid: str = "ku.mindfulness.breath",
    target_title: str = "Breath",
    relationship_type: str = "RELATED_TO",
    evidence: str | None = "The breath is the most common anchor.",
) -> dict[str, Any]:
    return {
        "source_uid": source_uid,
        "source_title": source_title,
        "target_uid": target_uid,
        "target_title": target_title,
        "relationship_type": relationship_type,
        "evidence": evidence,
    }


def _connection_guidance(target_ku_uids: list[str]) -> GuidanceDetermination:
    return GuidanceDetermination(
        mode=GuidanceMode.EXPLORATORY,
        pedagogical_detail=PedagogicalIntent.SURFACE_CONNECTION,
        target_ku_uids=target_ku_uids,
        zone_evidence={},
    )


def _bundle_with_edges(edges: list[dict[str, Any]]) -> MagicMock:
    bundle = MagicMock()
    bundle.edges = tuple(edges)
    return bundle


# ============================================================================
# TESTS: ContextRetriever._fetch_ku_lateral_edges
# ============================================================================


class TestFetchKuLateralEdges:
    """Real lateral edges come back shaped for the prompt, deduped."""

    @pytest.mark.anyio
    async def test_edge_shape_carries_endpoints_type_and_evidence(self) -> None:
        retriever = _make_retriever([_edge_record()])

        edges = await retriever._fetch_ku_lateral_edges(["ku.mindfulness.breath"])

        assert edges == [
            {
                "source_uid": "ku.mindfulness.anchor",
                "source_title": "Anchor",
                "target_uid": "ku.mindfulness.breath",
                "target_title": "Breath",
                "relationship_type": "RELATED_TO",
                "evidence": "The breath is the most common anchor.",
            }
        ]

    @pytest.mark.anyio
    async def test_null_evidence_becomes_empty_string(self) -> None:
        retriever = _make_retriever([_edge_record(evidence=None)])

        edges = await retriever._fetch_ku_lateral_edges(["ku.mindfulness.breath"])

        assert edges[0]["evidence"] == ""

    @pytest.mark.anyio
    async def test_symmetric_duplicate_collapses_preferring_evidence(self) -> None:
        """a RELATED_TO b stored both ways is ONE fact — keep the evidenced copy."""
        retriever = _make_retriever(
            [
                _edge_record(evidence=None),
                _edge_record(
                    source_uid="ku.mindfulness.breath",
                    source_title="Breath",
                    target_uid="ku.mindfulness.anchor",
                    target_title="Anchor",
                    evidence="Authored evidence.",
                ),
            ]
        )

        edges = await retriever._fetch_ku_lateral_edges(["ku.mindfulness.breath"])

        assert len(edges) == 1
        assert edges[0]["evidence"] == "Authored evidence."

    @pytest.mark.anyio
    async def test_asymmetric_inverse_pair_collapses(self) -> None:
        """A BLOCKS B + B BLOCKED_BY A is one fact."""
        retriever = _make_retriever(
            [
                _edge_record(relationship_type="BLOCKS", evidence="A gates B."),
                _edge_record(
                    source_uid="ku.mindfulness.breath",
                    source_title="Breath",
                    target_uid="ku.mindfulness.anchor",
                    target_title="Anchor",
                    relationship_type="BLOCKED_BY",
                    evidence=None,
                ),
            ]
        )

        edges = await retriever._fetch_ku_lateral_edges(["ku.mindfulness.breath"])

        assert len(edges) == 1
        assert edges[0]["evidence"] == "A gates B."

    @pytest.mark.anyio
    async def test_malformed_records_are_skipped(self) -> None:
        retriever = _make_retriever(
            [
                {"source_uid": None, "target_uid": "ku.x", "relationship_type": "RELATED_TO"},
                {"source_uid": "ku.x", "target_uid": "ku.y", "relationship_type": None},
                _edge_record(),
            ]
        )

        edges = await retriever._fetch_ku_lateral_edges(["ku.mindfulness.breath"])

        assert len(edges) == 1

    @pytest.mark.anyio
    async def test_empty_ku_uids_short_circuits_without_backend_call(self) -> None:
        ps_backend = MagicMock()
        ps_backend.get_ku_lateral_edges = AsyncMock(return_value=Result.ok([_edge_record()]))
        retriever = ContextRetriever(
            graph_intel=MagicMock(), embeddings_service=MagicMock(), ps_backend=ps_backend
        )

        edges = await retriever._fetch_ku_lateral_edges([])

        assert edges == []
        ps_backend.get_ku_lateral_edges.assert_not_awaited()

    @pytest.mark.anyio
    async def test_no_backend_returns_empty(self) -> None:
        retriever = ContextRetriever(
            graph_intel=MagicMock(), embeddings_service=MagicMock(), ps_backend=None
        )

        assert await retriever._fetch_ku_lateral_edges(["ku.x"]) == []

    @pytest.mark.anyio
    async def test_backend_error_returns_empty(self) -> None:
        ps_backend = MagicMock()
        ps_backend.get_ku_lateral_edges = AsyncMock(
            return_value=Result.fail(Errors.database("lateral edges", "boom"))
        )
        retriever = ContextRetriever(
            graph_intel=MagicMock(), embeddings_service=MagicMock(), ps_backend=ps_backend
        )

        assert await retriever._fetch_ku_lateral_edges(["ku.x"]) == []


# ============================================================================
# TESTS: ResponseGenerator SURFACE_CONNECTION rendering
# ============================================================================


class TestSurfaceConnectionRendering:
    """Prompt lines name both concepts and quote the authored evidence."""

    def test_evidence_edge_renders_titled_pair_with_evidence(self) -> None:
        generator = ResponseGenerator()
        guidance = _connection_guidance(["ku.mindfulness.breath", "ku.mindfulness.attention"])
        bundle = _bundle_with_edges([_edge_record()])

        prompt = generator._build_exploratory_prompt(guidance, bundle)

        assert "- Anchor —related to— Breath: The breath is the most common anchor." in prompt
        assert "No specific evidence available." not in prompt

    def test_evidence_less_edge_renders_pair_without_dangling_colon(self) -> None:
        generator = ResponseGenerator()
        guidance = _connection_guidance(["ku.mindfulness.breath", "ku.mindfulness.attention"])
        bundle = _bundle_with_edges([{**_edge_record(), "evidence": ""}])

        prompt = generator._build_exploratory_prompt(guidance, bundle)

        assert "- Anchor —related to— Breath" in prompt
        assert "Breath:" not in prompt

    def test_edge_without_nameable_endpoints_is_skipped(self) -> None:
        """A pairless line grounds nothing — fall back instead of '- related to: '."""
        generator = ResponseGenerator()
        guidance = _connection_guidance(["ku.mindfulness.breath", "ku.mindfulness.attention"])
        bundle = _bundle_with_edges(
            [
                {
                    "source_uid": "",
                    "source_title": "",
                    "target_uid": "ku.mindfulness.breath",
                    "target_title": "Breath",
                    "relationship_type": "RELATED_TO",
                    "evidence": "",
                }
            ]
        )

        prompt = generator._build_exploratory_prompt(guidance, bundle)

        assert "- related to" not in prompt
        assert "No specific evidence available." in prompt

    def test_no_relevant_edges_keeps_fallback(self) -> None:
        generator = ResponseGenerator()
        guidance = _connection_guidance(["ku.mindfulness.breath", "ku.mindfulness.attention"])
        bundle = _bundle_with_edges([])

        prompt = generator._build_exploratory_prompt(guidance, bundle)

        assert "No specific evidence available." in prompt

    def test_edge_touching_neither_target_is_excluded(self) -> None:
        generator = ResponseGenerator()
        guidance = _connection_guidance(["ku.mindfulness.breath", "ku.mindfulness.attention"])
        bundle = _bundle_with_edges(
            [
                _edge_record(
                    source_uid="ku.other.a",
                    source_title="Other A",
                    target_uid="ku.other.b",
                    target_title="Other B",
                )
            ]
        )

        prompt = generator._build_exploratory_prompt(guidance, bundle)

        assert "Other A" not in prompt
        assert "No specific evidence available." in prompt

    def test_source_endpoint_match_is_included(self) -> None:
        """Edges pointing OUT of a target KU render too."""
        generator = ResponseGenerator()
        guidance = _connection_guidance(["ku.mindfulness.anchor", "ku.mindfulness.attention"])
        bundle = _bundle_with_edges([_edge_record()])

        prompt = generator._build_exploratory_prompt(guidance, bundle)

        assert "- Anchor —related to— Breath" in prompt


# ============================================================================
# TESTS: IntentClassifier edge-connected check
# ============================================================================


class TestEdgeConnectedCheck:
    """SURFACE_CONNECTION fires when a real edge touches a target KU — either end."""

    def _classify(self, edges: list[dict[str, Any]], target_ku_uids: list[str]):
        classifier = IntentClassifier(embeddings_service=MagicMock())
        bundle = MagicMock()
        bundle.edges = tuple(edges)
        return classifier.classify_pedagogical_intent(
            question="How do these relate?",
            ps_bundle=bundle,
            zone_evidence={},
            target_ku_uids=target_ku_uids,
        )

    def test_target_ku_as_edge_source_fires_surface_connection(self) -> None:
        intent = self._classify(
            [_edge_record()],
            ["ku.mindfulness.anchor", "ku.mindfulness.attention"],
        )
        assert intent is PedagogicalIntent.SURFACE_CONNECTION

    def test_target_ku_as_edge_target_fires_surface_connection(self) -> None:
        intent = self._classify(
            [_edge_record()],
            ["ku.mindfulness.breath", "ku.mindfulness.attention"],
        )
        assert intent is PedagogicalIntent.SURFACE_CONNECTION

    def test_unconnected_targets_do_not_fire(self) -> None:
        intent = self._classify(
            [_edge_record()],
            ["ku.other.a", "ku.other.b"],
        )
        assert intent is not PedagogicalIntent.SURFACE_CONNECTION
