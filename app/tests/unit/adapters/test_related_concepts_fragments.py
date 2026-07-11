"""Tests for the "Related concepts" lens (Ku + PS detail pages).

Covers the three layers of the read-time similarity lens:
- ``render_ku_related_concepts`` / ``render_ps_related_concepts`` — chip-row
  sections that collapse to an empty div (stable id preserved) when empty.
- ``Neo4jVectorSearchService.find_related_concepts`` — applies the
  empirically derived node→node threshold + chip limit from config.
- The ``/explore/{ku,ps}/{uid}/related`` fragment handlers — fail-soft:
  CORE tier (no vector service) and lookup errors both collapse to the
  empty fragment, never an error banner.

Live-index behavior (real neighbour quality) is runtime-verified, not unit
tested — scores depend on the embedded corpus.
"""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

from fasthtml.common import to_xml

from adapters.inbound.learning_loop_routes import create_learning_loop_detail_routes
from core.config.unified_config import VectorSearchConfig
from core.services.neo4j_vector_search_service import Neo4jVectorSearchService
from core.utils.result_simplified import Errors, Result
from ui.explore.ku_detail import render_ku_related_concepts
from ui.explore.ps_detail import render_ps_related_concepts
from ui.page_contexts import RelatedConceptChip

# ============================================================================
# Section renderers — chips or complete absence
# ============================================================================


class TestRenderKuRelatedConcepts:
    def test_chips_link_to_neighbour_reading_pages(self) -> None:
        html = to_xml(
            render_ku_related_concepts(
                [
                    {"uid": "ku.discipline.atomic-habits", "title": "Atomic Habits"},
                    {"uid": "ku.sel.habits", "title": "Habits"},
                ]
            )
        )

        assert "Related concepts" in html
        assert 'href="/explore/ku/ku.discipline.atomic-habits"' in html
        assert "Atomic Habits" in html
        assert 'href="/explore/ku/ku.sel.habits"' in html

    def test_no_raw_scores_in_output(self) -> None:
        """Ordered chips suffice — similarity scores never reach the UI."""
        html = to_xml(render_ku_related_concepts([{"uid": "ku.a.b", "title": "B"}]))

        assert "0.7" not in html
        assert "score" not in html

    def test_empty_input_collapses_to_empty_div_with_stable_id(self) -> None:
        html = to_xml(render_ku_related_concepts([]))

        assert 'id="ku-related-fragment"' in html
        assert "Related concepts" not in html

    def test_items_without_uid_are_filtered(self) -> None:
        orphan = cast("RelatedConceptChip", {"title": "orphan"})  # malformed: fail-soft filter
        html = to_xml(render_ku_related_concepts([orphan]))

        assert "Related concepts" not in html
        assert "orphan" not in html

    def test_uid_fallback_when_title_missing(self) -> None:
        untitled = cast("RelatedConceptChip", {"uid": "ku.x.y"})  # missing title: uid fallback
        html = to_xml(render_ku_related_concepts([untitled]))

        assert "ku.x.y" in html

    def test_section_id_stable_for_htmx_outerhtml_swap(self) -> None:
        html = to_xml(render_ku_related_concepts([{"uid": "ku.x.y", "title": "Y"}]))

        assert 'id="ku-related-fragment"' in html


class TestRenderPsRelatedConcepts:
    def test_chips_link_to_neighbour_detail_pages(self) -> None:
        html = to_xml(
            render_ps_related_concepts(
                [{"uid": "ps.sel.knowing-yourself", "title": "Knowing Yourself"}]
            )
        )

        assert "Related concepts" in html
        assert 'href="/explore/ps/ps.sel.knowing-yourself"' in html
        assert "Knowing Yourself" in html

    def test_empty_input_collapses_to_empty_div_with_stable_id(self) -> None:
        html = to_xml(render_ps_related_concepts([]))

        assert 'id="ps-related-fragment"' in html
        assert "Related concepts" not in html


# ============================================================================
# Service path — find_related_concepts applies the config knobs
# ============================================================================


def _node(uid: str, title: str) -> dict[str, Any]:
    return {"uid": uid, "title": title}


def _service_with_backend(
    records: list[dict[str, Any]],
) -> tuple[Neo4jVectorSearchService, MagicMock]:
    """Service over a stub backend: one embedded source node + index records."""
    backend = MagicMock()
    backend.get_node_embedding = AsyncMock(return_value=Result.ok([{"embedding": [0.1] * 4}]))
    backend.query_vector_index = AsyncMock(return_value=Result.ok(records))
    return Neo4jVectorSearchService(backend=backend, config=VectorSearchConfig()), backend


async def test_find_related_concepts_uses_node_to_node_threshold_and_limit() -> None:
    config = VectorSearchConfig()
    service, backend = _service_with_backend([])

    result = await service.find_related_concepts("Ku", "ku.a.b")

    assert result.is_ok
    # limit is over-fetched by 1 (exclude_self), min_score is the node→node knob
    backend.query_vector_index.assert_awaited_once_with(
        "ku_embedding_idx",
        config.related_concepts_limit + 1,
        [0.1] * 4,
        config.ku_similar_min_score,
    )


async def test_find_related_concepts_excludes_source_node() -> None:
    service, _ = _service_with_backend(
        [
            {"node": _node("ku.a.b", "Self"), "score": 1.0},
            {"node": _node("ku.a.c", "Neighbour"), "score": 0.8},
        ]
    )

    result = await service.find_related_concepts("Ku", "ku.a.b")

    assert result.is_ok
    assert [r["node"]["uid"] for r in result.value] == ["ku.a.c"]


async def test_find_related_concepts_pathstep_targets_pathstep_index() -> None:
    service, backend = _service_with_backend([])

    result = await service.find_related_concepts("PathStep", "ps.sel.managing-yourself")

    assert result.is_ok
    assert backend.query_vector_index.await_args.args[0] == "pathstep_embedding_idx"


async def test_find_related_concepts_missing_embedding_is_not_found() -> None:
    backend = MagicMock()
    backend.get_node_embedding = AsyncMock(return_value=Result.ok([{"embedding": None}]))
    service = Neo4jVectorSearchService(backend=backend, config=VectorSearchConfig())

    result = await service.find_related_concepts("Ku", "ku.no.embedding")

    assert result.is_error


# ============================================================================
# Fragment handlers — fail-soft at every layer
# ============================================================================


class _RouteRecorder:
    """Fake ``rt`` decorator — records path → handler for direct invocation."""

    def __init__(self) -> None:
        self.handlers: dict[str, Any] = {}

    def __call__(self, path: str, methods: list[str] | None = None) -> Any:
        def _register(handler: Any) -> Any:
            self.handlers[path] = handler
            return handler

        return _register


def _related_handlers(vector_search_service: Any) -> tuple[Any, Any]:
    """Register the detail routes and return the (ku, ps) related handlers."""
    recorder = _RouteRecorder()
    create_learning_loop_detail_routes(
        MagicMock(),
        recorder,  # type: ignore[arg-type]  # boundary: test double for RouteDecorator
        orchestrator=MagicMock(),
        vector_search_service=vector_search_service,
    )
    return (
        recorder.handlers["/explore/ku/{uid}/related"],
        recorder.handlers["/explore/ps/{uid}/related"],
    )


async def test_related_fragment_happy_path_renders_chips() -> None:
    service = MagicMock()
    service.find_related_concepts = AsyncMock(
        return_value=Result.ok(
            [
                {"node": _node("ku.discipline.investment", "Investment"), "score": 0.78},
                {"node": _node("ku.sel.habits", "Habits"), "score": 0.75},
            ]
        )
    )
    ku_handler, _ = _related_handlers(service)

    html = to_xml(await ku_handler(MagicMock(), "ku.discipline.compounding"))

    assert "Related concepts" in html
    assert 'href="/explore/ku/ku.discipline.investment"' in html
    assert "Habits" in html
    service.find_related_concepts.assert_awaited_once_with("Ku", "ku.discipline.compounding")


async def test_related_fragment_none_service_returns_empty_fragment() -> None:
    """CORE tier: no vector service → section absent, no error."""
    ku_handler, ps_handler = _related_handlers(None)

    ku_html = to_xml(await ku_handler(MagicMock(), "ku.a.b"))
    ps_html = to_xml(await ps_handler(MagicMock(), "ps.a.b"))

    assert 'id="ku-related-fragment"' in ku_html
    assert "Related concepts" not in ku_html
    assert 'id="ps-related-fragment"' in ps_html
    assert "Related concepts" not in ps_html


async def test_related_fragment_error_fails_soft() -> None:
    """Lookup failure (e.g. nonexistent uid) → empty fragment, never a banner."""
    service = MagicMock()
    service.find_related_concepts = AsyncMock(
        return_value=Result.fail(Errors.not_found(resource="Ku", identifier="ku.missing"))
    )
    ku_handler, _ = _related_handlers(service)

    html = to_xml(await ku_handler(MagicMock(), "ku.missing"))

    assert 'id="ku-related-fragment"' in html
    assert "Related concepts" not in html
    assert "error" not in html.lower()


async def test_ps_related_fragment_happy_path() -> None:
    service = MagicMock()
    service.find_related_concepts = AsyncMock(
        return_value=Result.ok(
            [{"node": _node("ps.sel.knowing-yourself", "Knowing Yourself"), "score": 0.77}]
        )
    )
    _, ps_handler = _related_handlers(service)

    html = to_xml(await ps_handler(MagicMock(), "ps.sel.managing-yourself"))

    assert 'href="/explore/ps/ps.sel.knowing-yourself"' in html
    service.find_related_concepts.assert_awaited_once_with("PathStep", "ps.sel.managing-yourself")
