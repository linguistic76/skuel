"""Pin ``scripts/history_in_code.py`` — the advisory history-in-code census.

Every probe runs through the real functions (``scan_source`` → ``prose_lines`` +
``classify``; ``main`` for the CLI). No mocked walker: a change to what is read
(comments and docstrings only) or to how a line is counted fails here, and the
two deliberate reporting decisions — the date-typed-field false positive stays
reported, a bad path is a usage error — are pinned so they remain decisions.
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

# scripts/ has no __init__.py — add it to sys.path for import (matches test_detect_bloat.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import history_in_code as hic  # type: ignore[import-not-found]


def _hits(source: str) -> list[hic.Hit]:
    return list(hic.scan_source(textwrap.dedent(source), "probe.py").hits)


# ============================================================================
# WHAT IS READ — comments and docstrings, nothing else
# ============================================================================


def test_docstring_used_to_is_a_phrase_hit() -> None:
    hits = _hits(
        '''
        def f():
            """Create a task.

            This method used to reach backend.create directly.
            """
        '''
    )
    assert [(h.lineno, h.kind, h.categories) for h in hits] == [(5, "docstring", ("phrase",))]


def test_comment_pr_number_is_a_pr_ref_hit() -> None:
    hits = _hits("x = 1  # admission guard (#965)\n")
    assert [(h.lineno, h.kind, h.categories) for h in hits] == [(1, "comment", ("pr_ref",))]


def test_strings_fstrings_and_log_messages_are_not_read() -> None:
    hits = _hits(
        """
        STAMP = "2026-08-06"

        def f(x):
            logger.info(f"fixed {x} on 2026-08-06 (#965)")
            return "used to be a dict; was deleted in PR-4"
        """
    )
    assert hits == []


def test_docstring_hits_carry_their_source_line() -> None:
    """Uncleaned docstrings: a leading newline is a line, so offsets stay exact."""
    hits = _hits(
        '''
        def f():
            """
            Summary line.

            The colon alias was deleted 2026-08-14.
            """
        '''
    )
    assert [(h.lineno, h.categories) for h in hits] == [(6, ("date", "phrase"))]


# ============================================================================
# WHAT IS NOT A HIT — the sanctioned pointer form and the grammar rulings
# ============================================================================


def test_pointer_lines_and_record_citations_are_not_hits() -> None:
    hits = _hits(
        '''
        # See: /docs/decisions/ADR-074-post-persist-embedding-events.md
        # Backend: KuBackend.get_path_steps_using (ADR-069 § 1.1 amendment 2026-09-03)

        def f():
            """Publish post-persist (ADR-074; docs/roadmap/done/ownership-bundle.md).

            See: docs/roadmap/done/update-intents.md § Census (#1054)
            """
        '''
    )
    assert hits == []


def test_utilized_idiom_and_runtime_sense_are_not_phrase_hits() -> None:
    hits = _hits(
        '''
        class Weights:
            """Used to weight semantic relationships when boosting scores."""

        def unsubscribe(handler):
            """Remove a previously-registered handler; the page cannot be used to probe it."""
        '''
    )
    assert hits == []


def test_history_sense_of_used_to_and_previously_are_hits() -> None:
    hits = _hits(
        '''
        def f():
            """The registry holds class references. It used to hold module names.

            Previously: the route handler coerced this itself.
            """
        '''
    )
    assert [(h.lineno, h.categories) for h in hits] == [(3, ("phrase",)), (5, ("phrase",))]


# ============================================================================
# COUNTING — every category a line carries, dominant first; the pinned false positive
# ============================================================================


def test_a_line_carries_every_category_it_matches_dominant_first() -> None:
    hits = _hits("# the dict door was deleted 2026-08-06 (#1054, ADR-087 PR-4)\n")
    assert len(hits) == 1
    assert hits[0].categories == ("pr_tag", "pr_ref", "date", "phrase")
    assert hits[0].dominant == "pr_tag"


def test_date_typed_field_docstring_is_reported_by_design() -> None:
    """The known false positive is listed, not special-cased — no exemption syntax."""
    hits = _hits(
        '''
        class Task:
            """A task.

            completion_date: ISO date, ``YYYY-MM-DD`` — e.g. ``2026-08-06``.
            """
        '''
    )
    assert [(h.lineno, h.categories) for h in hits] == [(5, ("date",))]


def test_default_scope_excludes_tests_and_scripts() -> None:
    assert hic.DEFAULT_SCOPE == ("core", "adapters", "ui", "services_bootstrap")


# ============================================================================
# THE CLI — hits order with density tiebreak, exit 0, clean JSON, skipped files listed
# ============================================================================

# hits / source lines: wide 3/40 · dense 2/4 · sparse 2/60 → order wide, dense, sparse.
WIDE = "# fixed 2026-08-06\n# was deleted (#963)\n# used to be a dict\n" + "Z = 0\n" * 37
DENSE = "# shelved 2026-03-28\nX = 1\n# renamed per #1054\nY = 2\n"
SPARSE = "# shelved 2026-03-28\n" + "W = 0\n" * 58 + "# renamed per #1054\n"


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    (tmp_path / "wide.py").write_text(WIDE)
    (tmp_path / "dense.py").write_text(DENSE)
    (tmp_path / "sparse.py").write_text(SPARSE)
    (tmp_path / "clean.py").write_text("V = 1  # See: ADR-074 (amended 2026-09-03)\n")
    return tmp_path


def test_top_orders_by_hits_then_density_and_exits_zero(
    tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert hic.main(["--top", "2", str(tree)]) == 0
    out = capsys.readouterr().out
    rows = [line for line in out.splitlines() if line.endswith(".py")]
    assert [row.rsplit("/", 1)[-1] for row in rows] == ["wide.py", "dense.py"]
    assert "sparse.py" not in out  # same hits as dense, lower density — cut by --top 2
    assert "Total: 7 lines in 3 files (showing 2); 4 files scanned" in out


def test_json_is_clean_on_stdout_and_parses(tree: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert hic.main(["--json", str(tree)]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["advisory"] is True
    assert (doc["files_scanned"], doc["files_with_hits"], doc["total_hits"]) == (4, 3, 7)
    # `fixed 2026-08-06` is a date AND a phrase — a line counts once per category it carries.
    assert doc["by_category"] == {"pr_tag": 0, "pr_ref": 3, "date": 3, "phrase": 3}
    assert [f["path"].rsplit("/", 1)[-1] for f in doc["files"]] == [
        "wide.py",
        "dense.py",
        "sparse.py",
    ]
    first = doc["files"][0]["lines"][0]
    assert first == {
        "lineno": 1,
        "kind": "comment",
        "dominant": "date",
        "categories": ["date", "phrase"],
        "text": "fixed 2026-08-06",
    }


def test_unparseable_file_is_listed_as_skipped_never_dropped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "bad.py").write_text("def (:\n")
    assert hic.main([str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "Skipped (not parseable as Python)" in out
    assert "bad.py" in out


def test_missing_path_is_a_usage_error_not_a_clean_run() -> None:
    """The one non-zero exit: a typo'd path must not read as 'no history here'."""
    with pytest.raises(SystemExit) as exc:
        hic.main(["--json", "/nonexistent/zzz-history-in-code"])
    assert exc.value.code == 2


# ============================================================================
# --docs — the same census over Markdown prose: fences and frontmatter unread
# ============================================================================

DOC = (
    "---\n"
    "title: Probe\n"
    "updated: 2026-09-18\n"
    "---\n"
    "\n"
    "# Probe\n"
    "\n"
    "The `/api/moc/organize` family was deleted in #241.\n"
    "\n"
    "```python\n"
    "# fixed 2026-08-06, was removed (#965)\n"
    "```\n"
    "\n"
    "See: docs/roadmap/done/x.md (2026-09-01)\n"
)


def test_markdown_reader_skips_frontmatter_and_fences_and_counts_prose() -> None:
    """Three pinned lines: the frontmatter date is a stamp (ignored), the fenced line
    is an example (ignored), the prose retelling is counted with every category it
    carries — and the pointer line stays sanctioned in prose as in code."""
    report = hic.scan_markdown(DOC, "probe.md")
    assert [(h.lineno, h.kind, h.categories) for h in report.hits] == [
        (8, "prose", ("pr_ref", "phrase"))
    ]
    assert report.source_lines == 14


def test_explicit_md_path_takes_the_markdown_reader_without_the_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    doc = tmp_path / "probe.md"
    doc.write_text(DOC, encoding="utf-8")
    assert hic.main(["--json", str(doc)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["total_hits"] == 1
    assert payload["files"][0]["lines"][0]["kind"] == "prose"
    # ...and the table names what it read.
    assert hic.main([str(doc)]) == 0
    out = capsys.readouterr().out
    assert "Markdown prose outside fences" in out
    assert "--docs --top 20 --verbose" in out


def test_docs_flag_scans_the_md_files_under_a_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "a.md").write_text(DOC, encoding="utf-8")
    (tmp_path / "b.py").write_text("# was deleted 2026-01-01\n", encoding="utf-8")
    assert hic.main(["--docs", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "Markdown prose outside fences" in out
    assert "a.md" in out
    assert "b.py" not in out  # a .py under --docs is not in scope
    assert "Sweep queue: ./dev history-in-code --docs --top 20 --verbose" in out


def test_docs_default_scope_is_the_link_checkers_corpus() -> None:
    """Carve-outs inherited: the history directories are out by construction."""
    paths, scope = hic.resolve_paths(hic.build_parser(), [], docs=True)
    assert scope == ["docs", ".claude/skills"]
    assert len(paths) > 100
    rels = {p.relative_to(hic.ROOT).as_posix() for p in paths}
    assert all(p.endswith(".md") for p in rels)
    assert not any(p.startswith("docs/roadmap/done/") for p in rels)
    assert "docs/tools/HISTORY_IN_CODE.md" in rels
