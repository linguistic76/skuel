"""
`/search` is top-N (#555 ruled DROP 2026-08-28): the results headline must describe
what is on the page without pretending to know the match-set size.

Four shapes: a full entity page ("Top N"), a full page the semantic boost grew
past the window (the extras are lesson-body hits and are named, not folded into
N — Kody, #1181), a short page (every match, counted plainly), and one result.
"""

from core.models.search_request import BODY_HIT_MATCH_REASON, SearchResponse
from ui.search.components import _results_headline


def _response(entity_rows: int, body_hits: int = 0, limit: int = 20) -> SearchResponse:
    rows: list[dict[str, object]] = [
        {"uid": f"ku.{i}", "title": f"Ku {i}"} for i in range(entity_rows)
    ]
    rows += [
        {"uid": f"ps.body.{i}", "title": f"Lesson {i}", "_match_reason": BODY_HIT_MATCH_REASON}
        for i in range(body_hits)
    ]
    return SearchResponse(results=rows, total=len(rows), limit=limit, offset=0, query_text="q")


def test_full_entity_page_is_top_n_of_the_requested_window() -> None:
    assert _results_headline(_response(20)) == "Top 20 results"


def test_boosted_page_names_the_extras_instead_of_inflating_n() -> None:
    # 20 entity rows + 3 appended lesson-body hits = 23 cards; N stays the window.
    assert _results_headline(_response(20, body_hits=3)) == "Top 20 results + 3 lesson-body hits"
    assert _results_headline(_response(20, body_hits=1)) == "Top 20 results + 1 lesson-body hit"


def test_short_page_is_every_match_counted_plainly() -> None:
    assert _results_headline(_response(12)) == "12 results"
    # body hits on a short page are still just rows on a page that shows every match
    assert _results_headline(_response(12, body_hits=3)) == "15 results"


def test_single_result_singular() -> None:
    assert _results_headline(_response(1)) == "1 result"
