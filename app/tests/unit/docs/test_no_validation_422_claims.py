"""No shipped markdown assigns 422 to a validation failure.

Why this exists
---------------
`ErrorCategory.VALIDATION` maps to **400**; 422 belongs to `BUSINESS`, a
well-formed request that breaks a domain rule. A status is a contract a client
integrator branches on, and one sentence is enough to teach the wrong one — so
the claim is guarded across every tracked `.md` file rather than in the one
guide that happens to describe the boundary.

How the predicate decides
-------------------------
A bare "422 near the word validation" is too crude in both directions. It
misses `Returns 422 for invalid input`, where the category word follows the
status, and it fires on `VALIDATION → 400, BUSINESS → 422`, where the status is
correctly attributed to the category beside it. Exempting any unit that merely
contains "business" is crude the other way: it clears
`Validation failures return 422, unlike business failures`.

So each 422 is read against the nearest category word on each side, and the
status is charged to whichever one it sits next to. A 422 whose closest
neighbour on either side names validation is a claim about validation.

The blind spot, stated
----------------------
A status with no category word in its own clause is invisible here, and that
covers two real shapes: the ASCII flow box, which splits the claim across rows
(`│ Validates JSON │` above, `│ - Returns 422 on failure │` below), and a
sentence that puts the category on the far side of a clause boundary. Both are
deliberate. Reaching them means widening the unit until one fragment answers for
its neighbours — which is exactly how a correct `BUSINESS -> 422, VALIDATION ->
400` starts reading as a violation, and how a deliberately non-SKUEL example
starts reading as a claim about SKUEL. A guard that cries wolf gets muted, so
this one stays narrow: a green run means the prose is clean, not that no 422
remains.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]
_CATEGORY = re.compile(r"validat\w*|pydantic|invalid|malformed|bad input|business", re.IGNORECASE)
_BUSINESS = re.compile(r"business", re.IGNORECASE)
_STATUS_422 = re.compile(r"\b422\b")


def _tracked_markdown() -> list[Path]:
    """Every markdown file the repo ships.

    Asking git rather than globbing keeps the corpus honest in both directions:
    a new doc anywhere is covered the moment it is added, and the untracked
    scratch tier (`app/plans/`) stays out without needing an exclude list.
    """
    listing = subprocess.run(
        ["git", "ls-files", "-z", "*.md"],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [_ROOT / name for name in listing.stdout.split("\0") if name]


def _units(text: str) -> list[str]:
    """Clauses outside fences; single lines inside them and in tables.

    Granularity is the whole design. A line is too narrow for prose — a sentence
    naming 422 and the category that owns it wraps across two lines. A paragraph
    is too wide — a semicolon or a comma joins one category's mapping to the
    next (`BUSINESS -> 422, VALIDATION -> 400`), and a reading that runs across
    the join charges each status to its neighbour's category. Inside a fence
    there are no blank lines to bound a paragraph, so a fence would collapse
    into a single unit and a foreign code example would answer for its
    neighbours.

    Commas inside backticks or parentheses are not boundaries: they belong to
    the code or the aside they sit in (`Errors.business(rule=..., ...)`), and
    splitting there would cut a term in half.
    """
    blocks: list[str] = []
    buffer: list[str] = []
    fenced = False

    def flush() -> None:
        if buffer:
            blocks.append(" ".join(buffer))
            buffer.clear()

    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            flush()
            fenced = not fenced
        elif fenced or line.startswith("|"):
            flush()
            if line.strip():
                blocks.append(line.strip())
        elif line.strip():
            buffer.append(line.strip())
        else:
            flush()
    flush()

    return [
        clause for block in blocks for part in _split_clauses(block) if (clause := part.strip())
    ]


def _split_clauses(block: str) -> list[str]:
    """Split on sentence ends, semicolons, and commas that separate clauses.

    A comma inside backticks or parentheses is part of a term, not a boundary,
    so those spans are masked before the split and restored after it.
    """
    masked = list(block)
    depth = 0
    in_code = False
    for index, char in enumerate(block):
        if char == "`":
            in_code = not in_code
        elif char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        if char == "," and (in_code or depth):
            masked[index] = "\x00"
    parts = re.split(r"(?<=[.!?])\s+|[;,]", "".join(masked))
    return [part.replace("\x00", ",") for part in parts]


def _charges_422_to_validation(unit: str) -> bool:
    """True when a 422 in this unit sits next to a validation word, not business."""
    for status in _STATUS_422.finditer(unit):
        before = list(_CATEGORY.finditer(unit[: status.start()]))
        after = list(_CATEGORY.finditer(unit[status.end() :]))
        if before and not _BUSINESS.search(before[-1].group()):
            return True
        if after and not _BUSINESS.search(after[0].group()):
            return True
    return False


def test_no_tracked_markdown_charges_422_to_validation() -> None:
    """A rejected input is 400 everywhere the docs describe one."""
    offenders = [
        f"{path.relative_to(_ROOT)}: {unit[:140]}"
        for path in _tracked_markdown()
        for unit in _units(path.read_text(encoding="utf-8"))
        if _charges_422_to_validation(unit)
    ]

    assert offenders == [], (
        "422 assigned to a validation failure — VALIDATION maps to 400:\n  "
        + "\n  ".join(offenders)
    )


def test_the_predicate_separates_the_two_categories() -> None:
    """A guard that cannot fail is not a guard, and one that over-fires gets muted.

    Both halves are pinned: the phrasings a reintroduced claim takes, and the
    correct sentences that name both categories in one breath. A change to
    `_units` or the predicate that blinds or coarsens the scan fails here rather
    than passing a corpus it can no longer read.
    """
    claims_validation = [
        "**If validation fails**: Pydantic returns `422 Unprocessable Entity`.",
        "Returns 422 for invalid input",
        "Validation failures return 422, unlike business failures.",
        "| Schema validation | Pydantic request model | 422 Unprocessable Entity |",
        "```python\n# Invalid values → 422: not a real status\n```",
    ]
    charges_business = [
        "maps error categories: BUSINESS → 422, VALIDATION → 400.",
        "the reverse ordering: VALIDATION → 400, 422 → BUSINESS.",
        "422 is reserved for `ErrorCategory.BUSINESS`, a well-formed request that breaks a rule.",
        "| `BUSINESS` | 422 | Domain rule violated | Duplicate journal title |",
        "maps error categories: **VALIDATION → 400**, BUSINESS → 422, NOT_FOUND → 404.",
        "invalid bodies → **400** (`ErrorCategory.VALIDATION`); 422 is `BUSINESS`, a rule violation",
        "| uniqueness as `Errors.validation` | a domain rule → `Errors.business(...)` (422, not 400) |",
        "```python\ntry:\n    pass\nexcept ValidationError as e:\n    return 422\n```",
    ]

    def flagged(text: str) -> bool:
        return any(_charges_422_to_validation(unit) for unit in _units(text))

    assert all(map(flagged, claims_validation)), "the guard went blind to a real claim"
    assert not any(map(flagged, charges_business)), "the guard fires on a correct sentence"
