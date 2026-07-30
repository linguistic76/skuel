"""Pin the code-segment extraction in ``scripts/health/stale_names.py``.

Why this file exists
--------------------
``extract_code_segments`` had no test at all, and carried two defects that a total-count
check could not see — the report said "121 stale references" before and after the fix.

  1. Its closing test was ``stripped.startswith(fence_char)``, so any inner fence line
     closed the outer block. Six such lines exist across four live documents (e.g.
     a ```` ```markwhen ```` sample inside a ```` ```markdown ```` block), and each one
     INVERTED the scanner's fence state for the rest of the document.
  2. It keyed each block by its *opening delimiter*, and ``scan_file`` walked
     ``block_start + j``. So every fenced finding was reported one line early — 47 of
     121 — the opening delimiter was scanned as if it were content, and each block's
     real last line was never scanned at all.

Both are silent: wrong coordinates and unscanned content still produce a plausible
report. The coordinate property below is the guard a count cannot provide.
"""

from __future__ import annotations

import sys
from pathlib import Path

# scripts/ has no __init__.py — add it to sys.path for import (matches test_lint_skuel.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "health"))

import stale_names as sn  # type: ignore[import-not-found]

# A tracked rename, read from the live table so this file cannot drift from it.
RENAMED_KEY = "KuType"


def test_renamed_key_is_still_tracked() -> None:
    """Guard the fixture: every case below is vacuous if this key leaves the table."""
    assert RENAMED_KEY in sn.RENAMED


# ============================================================================
# COORDINATES
# ============================================================================


def test_fenced_block_is_keyed_by_its_first_content_line() -> None:
    """Not by the opening delimiter. `scan_file` walks `first_line + j`, so keying by
    the delimiter reports every fenced hit one line early."""
    assert sn.extract_code_segments("intro\n```python\nx = 1\ny = 2\n```\n") == [
        (3, "x = 1\ny = 2")
    ]


def test_scan_file_reports_the_line_that_holds_the_identifier(tmp_path: Path) -> None:
    """The end-to-end coordinate check: an identifier on line 3 is reported at line 3."""
    doc = tmp_path / "probe.md"
    doc.write_text(f"intro\n```python\nx: {RENAMED_KEY} = 1\n```\n", encoding="utf-8")
    assert [(n, old) for n, old, _new, _kind in sn.scan_file(doc)] == [(3, RENAMED_KEY)]


def test_last_content_line_of_a_block_is_scanned(tmp_path: Path) -> None:
    """The off-by-one's quietest consequence: the old walk ran off the end one line
    short, so the final line of every fenced block was never examined."""
    doc = tmp_path / "probe.md"
    doc.write_text(f"```python\na = 1\nb: {RENAMED_KEY} = 2\n```\n", encoding="utf-8")
    assert [(n, old) for n, old, _new, _kind in sn.scan_file(doc)] == [(3, RENAMED_KEY)]


# ============================================================================
# NESTING — the reported bug, and the shape that actually occurs
# ============================================================================


def test_identifier_inside_a_wrapped_example_is_found(tmp_path: Path) -> None:
    """A ```` ````markdown ```` wrapper holding a ```` ```python ```` sample: the old
    scanner closed on the inner fence, so the wrapper's body went unscanned."""
    doc = tmp_path / "probe.md"
    doc.write_text(f"````markdown\n```python\nx: {RENAMED_KEY} = 1\n```\n````\n", encoding="utf-8")
    assert [(n, old) for n, old, _new, _kind in sn.scan_file(doc)] == [(3, RENAMED_KEY)]


def test_inner_fence_with_info_string_does_not_end_the_block(tmp_path: Path) -> None:
    """The live shape (6 occurrences, 4 documents). The identifier sits AFTER the inner
    fence, where the old scanner's state had already inverted."""
    doc = tmp_path / "probe.md"
    doc.write_text(
        f"```markdown\nintro\n```markwhen\nx: {RENAMED_KEY} = 1\n```\nprose\n", encoding="utf-8"
    )
    assert [(n, old) for n, old, _new, _kind in sn.scan_file(doc)] == [(4, RENAMED_KEY)]


# ============================================================================
# THE TWO PASSES DO NOT OVERLAP
# ============================================================================


def test_delimiter_lines_are_scanned_by_neither_pass(tmp_path: Path) -> None:
    """An info string is not content and not prose. Scanning it as an inline span would
    read ```` ```KuType ```` as a citation of the identifier."""
    doc = tmp_path / "probe.md"
    doc.write_text(f"```{RENAMED_KEY}\nx = 1\n```\n", encoding="utf-8")
    assert sn.scan_file(doc) == []


def test_inline_spans_inside_a_fence_are_not_double_counted(tmp_path: Path) -> None:
    """A backtick span on a fenced line is block content, counted once."""
    doc = tmp_path / "probe.md"
    doc.write_text(f"```python\nsee `{RENAMED_KEY}` here\n```\n", encoding="utf-8")
    assert [(n, old) for n, old, _new, _kind in sn.scan_file(doc)] == [(2, RENAMED_KEY)]


def test_inline_spans_outside_a_fence_are_still_scanned(tmp_path: Path) -> None:
    doc = tmp_path / "probe.md"
    doc.write_text(f"prose with `{RENAMED_KEY}` inline\n", encoding="utf-8")
    assert [(n, old) for n, old, _new, _kind in sn.scan_file(doc)] == [(1, RENAMED_KEY)]


# ============================================================================
# CORPUS PROPERTY — every reported coordinate holds its identifier
# ============================================================================


def test_every_reported_line_actually_contains_its_identifier() -> None:
    """The guard the total count cannot give.

    Both defects above left the total at 121 while moving 47 findings off their real
    line. This asserts the property over the live tree — and, separately, that the
    property is being *exercised*: an invariant that holds over an empty corpus is
    vacuous, which is how the first version of this check passed against the bug.
    """
    checked = 0
    mislocated: list[str] = []

    for doc in sn.get_scan_targets():
        lines = doc.read_text(encoding="utf-8", errors="ignore").splitlines()
        for lineno, old, _new, _kind in sn.scan_file(doc):
            checked += 1
            actual = lines[lineno - 1] if 0 < lineno <= len(lines) else "<OUT-OF-BOUNDS>"
            if old not in actual:
                mislocated.append(f"{doc.relative_to(sn.ROOT)}:{lineno} claims {old!r}")

    assert checked > 50, f"only {checked} findings checked — the property is vacuous"
    assert mislocated == [], f"findings reported on the wrong line: {mislocated[:10]}"
