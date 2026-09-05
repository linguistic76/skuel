"""Pin every documented "Supported rules:" list to ``SkuelLinter.SUPPRESSIBLE_RULES``.

Why this exists
---------------
``TestSuppressibleRulesDrift`` pins the *set* to the checkers' suppression-helper
call sites — code to code. Nothing pinned the docs' transcription of that set, and
``docs/patterns/linter_rules.md`` said so about itself: SKUEL033 was absent from its
list for a month after becoming suppressible (#868), while the same line claimed the
list was "drift-guarded". The guard's subject was the set, not the copy.

The corpus is discovered, not enumerated
----------------------------------------
A hard-coded pair of doc paths has the failure mode it is meant to prevent: a third
copy lands and nothing looks at it. That is not hypothetical — when this module was
written, ``docs/guides/LINTER_GUIDE.md`` already carried a third copy, stale by four
rules, that neither the registration nor the fix-up had seen. So this module globs
first-party docs and picks up every ``**Supported rules:**`` enumeration wherever it
sits. A new copy is covered on arrival.

One canonical form
------------------
A list is a comma-separated run of explicit ``SKUELnnn`` ids, terminated by an em
dash, a parenthesis, a period, or the end of the line. Range notation
(``SKUEL011-SKUEL015``, hyphen or en dash) is refused rather than expanded: expanding it would make the
parser a second place where "which ids does this span cover" is decided, and a range
silently absorbs a later-deleted id. The terminator matters for the other reason —
the sentence after the list in ``linter_rules.md`` names SKUEL026 and SKUEL033 in
prose, and a whole-line ``SKUEL\\d{3}`` grab reports one of them as a phantom extra
member (the census in ``docs/roadmap/catalog-copies-in-code.md`` § 9 did exactly
that).

Not an enumeration, not checked
-------------------------------
``CLAUDE.md`` deliberately carries a *pointer* ("Supported: exactly
``SkuelLinter.SUPPRESSIBLE_RULES``") and no list. The marker here is the bold
``**Supported rules:**`` label, so a pointer is invisible to this module by design.

The bold label is reserved for enumerations. The regex is deliberately NOT anchored
to line start — the sibling ``test_alpine_docs_registry.py`` records why: an anchor
silently drops a real copy, while an unanchored match on a prose *mention* of the
bold label fails loudly and the author rewrites the sentence (measured: the first
draft of this pin's own roadmap note tripped it). Prose that names the marker writes
it unbolded, as ``linter_rules.md`` does.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parents[3]

# scripts/ is not a package — the sibling import resolves at runtime via the
# sys.path insert below, but not for MyPy (same ignore as test_alpine_docs_registry.py).
sys.path.insert(0, str(APP_ROOT / "scripts"))

from lint_skuel import SkuelLinter  # type: ignore[import-not-found]  # noqa: E402

# The bold label is the marker; the body runs to the first terminator. Anything the
# body holds that is not `SKUELnnn` separated by commas is a form violation, reported
# by name below — a range dash is the case this was written against.
_SUPPORTED_RULES_RE = re.compile(r"\*\*Supported rules:\*\*\s*(?P<body>[^—(.\n]*)")
_RULE_ID_RE = re.compile(r"SKUEL\d{3}")

# The two copies known when this module was written. `test_lists_are_discovered`
# asserts both are still found, so a regex regression cannot pass vacuously.
KNOWN_COPIES = frozenset(
    {
        "docs/patterns/linter_rules.md",
        "docs/guides/LINTER_GUIDE.md",
    }
)


def _doc_files() -> list[Path]:
    files = [APP_ROOT / "CLAUDE.md", *sorted((APP_ROOT / "docs").rglob("*.md"))]
    files += sorted((APP_ROOT / ".claude" / "skills").rglob("*.md"))
    return [f for f in files if f.is_file()]


def _supported_rules_lists() -> list[tuple[Path, int, str]]:
    """Every ``**Supported rules:**`` enumeration as (path, 1-based line, raw body)."""
    found: list[tuple[Path, int, str]] = []
    for path in _doc_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            match = _SUPPORTED_RULES_RE.search(line)
            if match is not None:
                found.append((path, lineno, match.group("body").strip()))
    return found


def _parse_list(body: str) -> list[str]:
    """Split a body into rule ids, refusing any token that is not one explicit id."""
    tokens = [t.strip() for t in body.split(",")]
    malformed = [t for t in tokens if _RULE_ID_RE.fullmatch(t) is None]
    assert not malformed, (
        f"a Supported rules list must be explicit, comma-separated SKUELnnn ids — "
        f"not {malformed}. Range notation is refused on purpose: write every member."
    )
    return tokens


def _list_id(value: object) -> str:
    if isinstance(value, Path):
        return value.relative_to(APP_ROOT).as_posix()
    if isinstance(value, int):
        return f"L{value}"
    return ""


def test_lists_are_discovered() -> None:
    """Guard the guard: a discovery bug would make the parametrized check vacuous."""
    names = {p.relative_to(APP_ROOT).as_posix() for p, _, _ in _supported_rules_lists()}
    assert names >= KNOWN_COPIES, (
        f"expected the known Supported rules lists to be discovered, found {sorted(names)}"
    )


def test_the_terminator_stops_before_prose() -> None:
    """The over-capture trap, pinned: ids named in the sentence AFTER the list are prose."""
    line = (
        "**Supported rules:** SKUEL005, SKUEL011 — the set. A comment naming any other "
        "rule is flagged by SKUEL026; SKUEL033 was once missing here."
    )
    match = _SUPPORTED_RULES_RE.search(line)
    assert match is not None
    assert _parse_list(match.group("body").strip()) == ["SKUEL005", "SKUEL011"]


@pytest.mark.parametrize("dash", ["\u2013", "-"], ids=["en-dash", "hyphen"])
def test_range_notation_is_refused(dash: str) -> None:
    """A range is not an enumeration — the parser must say so, not silently truncate.

    The en dash is the form ``LINTER_GUIDE.md`` actually carried when this pin
    landed; the hyphen is the form a keyboard produces.
    """
    with pytest.raises(AssertionError, match="Range notation is refused"):
        _parse_list(f"SKUEL005, SKUEL011{dash}SKUEL015, SKUEL017")


@pytest.mark.parametrize(("path", "lineno", "body"), _supported_rules_lists(), ids=_list_id)
def test_supported_rules_list_equals_the_set(path: Path, lineno: int, body: str) -> None:
    """Each documented list must equal ``SUPPRESSIBLE_RULES`` — both directions."""
    where = f"{path.relative_to(APP_ROOT).as_posix()}:{lineno}"
    listed = _parse_list(body)
    duplicates = sorted({r for r in listed if listed.count(r) > 1})
    assert not duplicates, f"{where} lists {duplicates} more than once"
    assert listed == sorted(listed), f"{where} is not in ascending rule-id order"

    expected = set(SkuelLinter.SUPPRESSIBLE_RULES)
    missing = sorted(expected - set(listed))
    extra = sorted(set(listed) - expected)
    assert not missing and not extra, (
        f"{where} disagrees with SkuelLinter.SUPPRESSIBLE_RULES — "
        f"missing: {missing or 'none'}; listed but not suppressible: {extra or 'none'}"
    )
