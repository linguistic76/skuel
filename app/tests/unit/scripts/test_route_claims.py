"""Pin ``scripts/health/route_claims.py`` — the route-claim scanner.

The negation grammar and the claim-shape exclusions are pinned as cases, one positive
and one negative each, because the defect they guard against is the instrument's, not
the corpus's. Two shapes in particular:

- **A line-scoped negation grammar skips nine corpus lines, and five of them are
  fiction** — a "no" or "404" elsewhere on the line reads as a statement about a span
  it has nothing to do with. The nine lines are ``NEGATION_CORPUS`` verbatim, with the
  verdict per span, both directions.
- **A near-miss relation treated as a match hides real fiction** — ``/ku`` is a
  relative suffix of ``/library/ku`` and ``POST /api/knowledge`` is a family prefix of
  ``/api/knowledge/ai/*``; neither route exists. They are printed CLASSES here, and the
  tests assert they are counted, never dropped.

Every scan runs through the real ``scan_content`` with an injected ``RouteCatalog`` —
no throwaway root ever boots the route tree; the runtime probe is pinned once, in
``test_route_catalog.py``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

# scripts/health/ has no __init__.py — add it to sys.path for import (matches
# test_dead_doc_links.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "health"))

import dead_doc_links as ddl  # type: ignore[import-not-found]
import route_catalog as rc  # type: ignore[import-not-found]
import route_claims as claims  # type: ignore[import-not-found]

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _plain(out: str) -> str:
    return ANSI_RE.sub("", out)


HISTORICAL = ddl.MARKERS_BY_NAME["historical"].spelling
PLANNED = ddl.MARKERS_BY_NAME["planned"].spelling

CATALOG = rc.RouteCatalog(
    {
        "/tasks": ["GET", "HEAD", "POST"],
        "/api/tasks/create": ["POST"],
        "/api/tasks/{uid}/status": ["POST"],
        "/api/tasks/{uid}/lateral/blocks": ["GET", "HEAD", "POST"],
        "/api/context/rich": ["GET", "HEAD", "POST"],
        "/api/knowledge/ai/summary": ["GET", "HEAD", "POST"],
        "/library/ku": ["GET", "HEAD", "POST"],
        "/profile/shared": ["GET", "HEAD", "POST"],
        "/explore/ku/{uid}": ["GET", "HEAD", "POST"],
        "/manifest.json": ["GET", "HEAD", "POST"],
    }
)


def _classes(body: str, name: str = "docs/patterns/probe.md") -> list[tuple[int, str, str]]:
    """``(lineno, label, class)`` for every claim the real scanner finds in ``body``."""
    scan = claims.scan_content(body, ddl.ROOT / name, CATALOG)
    return [(c.lineno, c.label, c.cls) for c in scan.claims]


# ============================================================================
# THE NEGATION GRAMMAR — nine corpus lines, both directions, written before the regex
# ============================================================================

# (line as it stands in the corpus on 2026-09-19, {claim path: negated?}). The first
# two are the only genuine span-adjacent negations; the other seven carry a negation
# token somewhere on the line and assert the route as live all the same.
NEGATION_CORPUS: list[tuple[str, dict[str, bool]]] = [
    ("- `/finance/expenses` → 404 (broken)", {"/finance/expenses": True}),
    ("- `/finance/budgets` → 404 (broken)", {"/finance/budgets": True}),
    ("| `/finance/expenses` | 401 (auth) | **404 (broken)** |", {"/finance/expenses": False}),
    ("| `/finance/budgets` | 401 (auth) | **404 (broken)** |", {"/finance/budgets": False}),
    (
        "`/api/activity-review/snapshot` and `/api/activity-review/submit` require "
        "`@require_admin`. The `/api/activity-review/history` route is always scoped to the "
        "calling user's own UID (no `subject_uid` override).",
        {
            "/api/activity-review/snapshot": False,
            "/api/activity-review/submit": False,
            "/api/activity-review/history": False,
        },
    ),
    (
        "| IDOR fix — `GET /api/submissions/shared-users` | Ownership failure now returns 404 "
        "(not 403) — prevents UID enumeration; matches documented pattern |",
        {"/api/submissions/shared-users": False},
    ),
    (
        "A domain like Transcription exposes only processing endpoints (`POST /api/transcribe`). "
        "There are no pages to render, so a `ui_factory` would be an empty function.",
        {"/api/transcribe": False},
    ),
]


@pytest.mark.parametrize(("line", "verdicts"), NEGATION_CORPUS, ids=range(len(NEGATION_CORPUS)))
def test_negation_is_span_adjacent_on_the_corpus_lines(
    line: str, verdicts: dict[str, bool]
) -> None:
    found = {label.split(" ")[-1]: cls for _ln, label, cls in _classes(f"# P\n\n{line}\n")}
    assert set(found) == set(verdicts), found
    for path, negated in verdicts.items():
        assert (found[path] == "negated") is negated, (path, found[path])


@pytest.mark.parametrize(
    "line",
    [
        "there is no `/ku` route",
        "not `/ku` — the hub is `/library/ku`",
        "never `/ku`",
        "`/ku` → 404",
        "`/ku` -> 404",
        "`/ku` is a 404",
        "`/ku` returns 404",
        "`/ku` does not exist",
        "`/ku` doesn't exist",
        "`/ku` no longer exists",
        "`/ku` is gone",
    ],
)
def test_span_adjacent_negation_shapes(line: str) -> None:
    (_ln, _label, cls), *_ = _classes(f"# P\n\n{line}\n")
    assert cls == "negated"


def test_past_tense_is_history_not_negation() -> None:
    """`was deleted` narrates; the history class owns it, and `history_in_code --docs`
    is the census that reads the line."""
    assert _classes("# P\n\n`/sel` was deleted in the SEL arc\n")[0][2] == "history"


@pytest.mark.parametrize(
    "line",
    [
        "the `/ku` hub (no sidebar)",
        "`/ku` lists Kus; `/library` returns 404 for guests",
        "there is no sidebar on `/ku`",
        "`/ku` (404 handling is the caller's)",
    ],
)
def test_a_negation_token_elsewhere_on_the_line_is_not_a_negation(line: str) -> None:
    (_ln, _label, cls), *_ = _classes(f"# P\n\n{line}\n")
    assert cls != "negated"


# ============================================================================
# CLAIM SHAPE — one positive and one negative per exclusion
# ============================================================================


@pytest.mark.parametrize(
    "text",
    [
        "/tasks",
        "/api/tasks/create",
        "POST /api/tasks/create",
        "/api/tasks/{uid}/status",
        "/explore/ku/{ku_uid}",
        "/tasks?uid=abc",
        "/tasks/",
        "/ku",
        "/home",  # bare: the landing route, not the mount — `/home/<user>/…` is the mount
        "/api/tasks/123",  # a numeric segment among named ones is still a path
        "/api/{domain}/create",  # a metavariable NOT in first position stays a claim
    ],
)
def test_claim_shapes_admitted(text: str) -> None:
    shape = claims.is_url_shape(text)
    assert shape is not None, text
    assert shape[1].startswith("/")


@pytest.mark.parametrize(
    ("text", "exclusion"),
    [
        ("/api tasks", "a space"),
        ("/api/`x`", "a backtick"),
        ("/api/*", "a glob"),
        ("/api/$DOMAIN", "a shell variable"),
        ("/api/(tasks|goals)", "a regex"),
        ("/api/services/Platform/x", "an Uppercase segment — another vendor's API"),
        ("/home/mike/0bsidian", "a filesystem prefix"),
        ("/opt/skuel", "a filesystem prefix"),
        ("/opt", "a bare mount"),
        ("/conf", "a bare mount"),
        ("/swapfile", "a bare mount"),
        ("/etc", "a bare mount"),
        ("/services_bootstrap", "a repo top-level directory"),
        ("/scripts/health/x", "a path under a repo top-level directory"),
        ("/static/css/output.css", "a PROJECT_PREFIX — the link checker's"),
        ("/services_bootstrap.py", "a span the link checker's path guard accepts"),
        ("/docs/patterns/foo.md", "a PROJECT_PREFIX path"),
        ("/patterns/", "a trailing-slash docs/ subdirectory"),
        ("/{domain}/list", "a metavariable first segment"),
        ("/domain/list", "a metavariable first segment"),
        ("/section/x", "a metavariable first segment"),
        ("/{uid}", "a parameter first segment — no route opens with one"),
        ("/your_route/x", "a placeholder subject (_is_placeholder)"),
        ("/api/foo", "a metasyntactic placeholder (_is_placeholder)"),
        ("/", "the bare root"),
        ("/100", "all-numeric — a column header, not a path"),
        ("/2026/09", "all-numeric segments"),
        ("//cdn.example.com/x.js", "protocol-relative"),
        ("api/tasks", "no leading slash"),
    ],
)
def test_claim_shapes_rejected(text: str, exclusion: str) -> None:
    assert claims.is_url_shape(text) is None, f"{text!r} should be rejected: {exclusion}"


def test_template_marker_half_of_the_stand_in_guard_is_deliberately_not_used() -> None:
    """`{uid}` is what every parameterised route carries; `_is_documentation_stand_in`
    rejects it and would have dropped hundreds of real claims."""
    assert ddl._is_documentation_stand_in("/api/tasks/{uid}/status")
    assert claims.is_url_shape("/api/tasks/{uid}/status") is not None


# ============================================================================
# CLASSES — every claim in exactly one; near-miss relations are classes, not skips
# ============================================================================


def test_every_class_is_assigned_from_one_fixture_doc() -> None:
    body = (
        "# P\n\n"
        "Live: `/tasks` and `POST /api/tasks/create`.\n"  # matched x2
        "Dead: `/home` is the landing.\n"  # fiction
        "Retold: `/sel` was deleted 2026-02-08.\n"  # history (date + phrase)
        "Door: `/api/context` is the family.\n"  # family-prefix
        "Relative: `/create` under the base.\n"  # relative-suffix
        "Denied: there is no `/ku` route.\n"  # negated
    )
    found = _classes(body)
    assert [cls for _ln, _label, cls in found] == [
        "matched",
        "matched",
        "fiction",
        "history",
        "family-prefix",
        "relative-suffix",
        "negated",
    ]
    assert {cls for _ln, _label, cls in found} <= set(claims.CLASSES)


def test_history_uses_the_finders_vocabulary_not_a_second_one() -> None:
    """One vocabulary: a line is `history` exactly when `history_in_code.classify`
    reports a signal on it. `was accepting` is not in that vocabulary, so a dead
    route on such a line is fiction — the sweep's, not the census's."""
    assert _classes("# P\n\n`/home` (was accepting user_uid)\n")[0][2] == "fiction"
    assert _classes("# P\n\n`/home` was removed in the chrome arc\n")[0][2] == "history"
    assert _classes("# P\n\n`/home` (#1378)\n")[0][2] == "history"
    # A pointer line (`See:`) is the finder's sanctioned form and carries no signal by
    # its rule — so a dead route cited on one is fiction, as it should be: the
    # pointer sanctions the record, not the route.
    assert _classes("# P\n\nSee: `/home` was removed\n")[0][2] == "fiction"


def test_a_claimed_verb_the_route_does_not_serve_is_fiction() -> None:
    """`/api/tasks/create` is POST-only in the fixture catalog, as
    `/api/events/{uid}/status` is in the real one — `PUT` there is a claim about a
    route that does not exist."""
    found = _classes("# P\n\n`PUT /profile/shared` and `POST /profile/shared`\n")
    assert [(label, cls) for _ln, label, cls in found] == [
        ("PUT /profile/shared", "fiction"),
        ("POST /profile/shared", "matched"),
    ]
    # The near-miss relations are verb-blind — a printed class, not a match, either way.
    assert _classes("# P\n\n`PUT /api/tasks/create`\n")[0][2] == "family-prefix"


def test_relative_suffix_is_a_class_because_it_hides_ku() -> None:
    """`/ku` ends `/library/ku` and has no handler. If this relation were a skip, the
    three-sites-agreeing `/ku` fiction the last arc found would be invisible again."""
    found = _classes("# P\n\ncurriculum access via the `/ku` hub\n")
    assert found == [(3, "/ku", "relative-suffix")]


def test_family_prefix_is_a_class_because_it_hides_api_knowledge() -> None:
    """`POST /api/knowledge` is a strict prefix of `/api/knowledge/ai/*` and does not
    exist — reported under its class, never dropped."""
    found = _classes("# P\n\ncreate with `POST /api/knowledge`\n")
    assert found == [(3, "POST /api/knowledge", "family-prefix")]


def test_frontmatter_spans_are_never_claims() -> None:
    """A backticked route in a `description:` is metadata, not the doc's voice."""
    body = "---\ntitle: X\ndescription: the `/old-route` door\n---\n\n# X\n\n`/ku`\n"
    assert _classes(body) == [(8, "/ku", "relative-suffix")]


def test_fenced_spans_are_never_claims_and_fence_view_counts_nothing() -> None:
    body = "# P\n\n```python\n@rt('/ku')\nhx_get=\"/home\"\n```\n\nProse `/tasks`.\n"
    assert _classes(body) == [(8, "/tasks", "matched")]
    assert claims.fence_claims(body) == [(4, "/ku"), (5, "/home")]


# ============================================================================
# MARKERS — honored in scope, inert out of scope, ledger shared with the link checker
# ============================================================================


def test_historical_marker_skips_a_dead_claim_in_decisions() -> None:
    scan = claims.scan_content(
        f"# P\n\n`/home` was the landing. {HISTORICAL}\n",
        ddl.ROOT / "docs/decisions/ADR-000.md",
        CATALOG,
    )
    assert [c.cls for c in scan.claims] == [claims.marker_class("historical")]
    assert scan.marker_used == {"historical": {3}, "planned": set()}


def test_planned_marker_skips_a_not_yet_built_route_in_the_live_roadmap() -> None:
    scan = claims.scan_content(
        f"# P\n\n`/groups/{{uid}}/intelligence` — new {PLANNED}\n",
        ddl.ROOT / "docs/roadmap/plan.md",
        CATALOG,
    )
    assert [c.cls for c in scan.claims] == [claims.marker_class("planned")]
    assert scan.marker_used["planned"] == {3}


@pytest.mark.parametrize(
    ("marker", "path"),
    [
        (HISTORICAL, "docs/roadmap/plan.md"),
        (PLANNED, "docs/decisions/ADR-000.md"),
        (HISTORICAL, "docs/patterns/x.md"),
    ],
)
def test_marker_outside_its_tier_is_inert(marker: str, path: str) -> None:
    scan = claims.scan_content(f"# P\n\n`/home` {marker}\n", ddl.ROOT / path, CATALOG)
    assert [c.cls for c in scan.claims] == ["fiction"]
    assert scan.marker_used == {"historical": set(), "planned": set()}


def test_marker_never_covers_a_live_route() -> None:
    """A marker skips a DEAD claim and nothing else — so it is unused over a live
    route, which is what lets the link checker's ledger report it stale."""
    scan = claims.scan_content(
        f"# P\n\n`/tasks` {HISTORICAL}\n", ddl.ROOT / "docs/decisions/ADR-000.md", CATALOG
    )
    assert [c.cls for c in scan.claims] == ["matched"]
    assert scan.marker_used["historical"] == set()


# ============================================================================
# THE CLI — through main() with the runtime catalog stubbed
# ============================================================================


@pytest.fixture
def stubbed_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(claims, "runtime_catalog", _catalog_stub)


def _catalog_stub() -> rc.RouteCatalog:
    return CATALOG


def test_cli_prints_every_class_with_a_count_and_exits_zero(
    tmp_path: Path, stubbed_catalog: None, capsys: pytest.CaptureFixture[str]
) -> None:
    """Zero included: a class that goes quiet without saying so looks like a clean
    scan. And exit 0 whatever it finds — advisory by ruling."""
    doc = tmp_path / "probe.md"
    doc.write_text("# P\n\n`/home` and `/tasks`\n", encoding="utf-8")
    assert claims.main(["--file", str(doc), "--all"]) == 0
    out = _plain(capsys.readouterr().out)
    for cls in claims.ALL_CLASSES:
        assert cls in out, cls
    assert "0  history" in out
    assert "1  fiction" in out
    assert ":3  /home" in out
    assert "stale markers: reported by ./dev health-links" in out


def test_cli_class_filter_lists_that_class(
    tmp_path: Path, stubbed_catalog: None, capsys: pytest.CaptureFixture[str]
) -> None:
    doc = tmp_path / "probe.md"
    doc.write_text("# P\n\n`/api/context` door; `/home`\n", encoding="utf-8")
    assert claims.main(["--file", str(doc), "--class", "family-prefix", "--all"]) == 0
    out = _plain(capsys.readouterr().out)
    assert "family-prefix by file" in out
    assert ":3  /api/context" in out
    assert ":3  /home" not in out


def test_cli_fences_view_is_listed_but_never_counted(
    tmp_path: Path, stubbed_catalog: None, capsys: pytest.CaptureFixture[str]
) -> None:
    doc = tmp_path / "probe.md"
    doc.write_text("# P\n\n```python\n@rt('/ku')\n```\n", encoding="utf-8")
    assert claims.main(["--file", str(doc), "--fences"]) == 0
    out = _plain(capsys.readouterr().out)
    assert "(0 inline route claims)" in out
    assert "Fenced string literals not in the catalog — 1" in out
    assert ":4  /ku" in out


def test_cli_missing_file_is_a_usage_error(stubbed_catalog: None) -> None:
    with pytest.raises(SystemExit) as exc:
        claims.main(["--file", "/nonexistent/zzz.md"])
    assert exc.value.code == 2
