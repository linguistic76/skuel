"""No doc claims 422 for a validation failure.

Why this exists
---------------
`ErrorCategory.VALIDATION` maps to **400** and 422 belongs to `BUSINESS` — a
well-formed request that breaks a domain rule. The docs disagreed with the code
in six files at once: a rejected body, an invalid enum value and a malformed
JSON structure were all described as 422, in prose, in ASCII flow diagrams and
in code comments. A status a client integrator branches on is worth a guard, and
one wrong sentence is enough to teach the wrong contract.

What this catches, and what it does not
---------------------------------------
The predicate is narrow on purpose: a unit that names 422 *and* a validation
word, with no mention of business. That reliably catches the sentence someone
writes when reintroducing the claim ("returns 422 on validation failure") and
the code comment beside it.

It does NOT catch a 422 whose validation word lives on a different line — the
`│ - Returns 422 on failure │` cell of an ASCII box whose `│ Validates JSON │`
row sits above it. Widening the unit to cover those swallows a whole fenced
block, which then flags a deliberate non-SKUEL example as if it were a claim
about SKUEL. So the box shape is left to review, and this guard promises the
prose only. Do not read a green run as "no 422 claims remain".
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_VALIDATION = re.compile(r"validat|pydantic|invalid|malformed|bad input", re.IGNORECASE)
_BUSINESS = re.compile(r"business", re.IGNORECASE)
_STATUS_422 = re.compile(r"\b422\b")


def _scanned_files() -> list[Path]:
    """Every doc and skill this repo ships, plus the project brief."""
    return [
        *sorted((_ROOT / "docs").rglob("*.md")),
        *sorted((_ROOT / ".claude" / "skills").rglob("*.md")),
        _ROOT / "CLAUDE.md",
    ]


def _units(text: str) -> list[str]:
    """Sentences outside fences, single lines inside them and in tables.

    Granularity is the whole design here. A line is too narrow for prose — a
    sentence naming 422 and the category that owns it wraps across two lines. A
    paragraph is too wide — one approved mention of business would clear every
    other claim beside it. Inside a fence there are no blank lines to bound a
    paragraph, so a fence would collapse into one unit and a foreign code
    example would answer for its neighbours; there, a line is exactly right.
    """
    paragraphs: list[str] = []
    buffer: list[str] = []
    fenced = False

    def flush() -> None:
        if buffer:
            paragraphs.append(" ".join(buffer))
            buffer.clear()

    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            flush()
            fenced = not fenced
        elif fenced or line.startswith("|"):
            flush()
            if line.strip():
                paragraphs.append(line.strip())
        elif line.strip():
            buffer.append(line.strip())
        else:
            flush()
    flush()

    units: list[str] = []
    for paragraph in paragraphs:
        units.extend(re.split(r"(?<=[.!?])\s+", paragraph))
    return units


def test_no_doc_pairs_422_with_a_validation_failure() -> None:
    """A rejected input is 400 everywhere the docs describe one."""
    offenders = [
        f"{path.relative_to(_ROOT)}: {unit[:140]}"
        for path in _scanned_files()
        for unit in _units(path.read_text(encoding="utf-8"))
        if _STATUS_422.search(unit) and _VALIDATION.search(unit) and not _BUSINESS.search(unit)
    ]

    assert offenders == [], (
        "422 claimed for a validation failure — VALIDATION maps to 400:\n  "
        + "\n  ".join(offenders)
    )


def test_the_predicate_still_fires() -> None:
    """A guard that cannot fail is not a guard.

    Pins the three shapes the corpus scan is meant to catch, and the two it must
    leave alone, so a change to `_units` that quietly blinds the scan fails here
    rather than passing an empty corpus.
    """
    caught = "**If validation fails**: Pydantic returns `422 Unprocessable Entity`."
    caught_comment = "```python\n# Invalid values → 422: not a real status\n```"
    caught_row = "| Schema validation | Pydantic request model | 422 Unprocessable Entity |"
    allowed_business = "422 is reserved for `ErrorCategory.BUSINESS`, a well-formed request."
    allowed_foreign = "```python\ntry:\n    pass\nexcept ValidationError as e:\n    return 422\n```"

    def flagged(text: str) -> bool:
        return any(
            _STATUS_422.search(u) and _VALIDATION.search(u) and not _BUSINESS.search(u)
            for u in _units(text)
        )

    assert flagged(caught)
    assert flagged(caught_comment)
    assert flagged(caught_row)
    assert not flagged(allowed_business)
    assert not flagged(allowed_foreign), "a fence must not answer for its neighbouring lines"
