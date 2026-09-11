"""Pin the health-check roster to its readers — ``dev``, the janitor, the docs.

The roster is the ``HEALTH_CHECKS`` array in ``app/dev``. The ``health`` block,
the ``health-*`` dispatcher and the help block read it, and ``./dev health
--list`` hands it to ``.github/workflows/weekly-janitor.yml``. This module holds
that seam shut from four directions:

1. **The array parses and the script agrees with it.** The literal is read out of
   ``dev`` AND ``./dev health --list`` is executed — a roster that parses but does
   not run is not a source.
2. **No runnable check is left off it.** Every ``scripts/health/*.py`` with a
   ``__main__`` guard is in the roster or in :data:`DELIBERATELY_UNREGISTERED`
   with a reason (and an entry there that IS in the roster is stale — the
   SKUEL026 discipline). Two traps this direction must survive:
   ``markdown_fences.py`` is a *library* with no ``__main__`` and must not be
   demanded, and ``validate_cross_references.py`` lives outside
   ``scripts/health/`` — the family is a roster, not a directory.
3. **The janitor enumerates nothing.** It must call ``./dev health --list`` and
   must not name a health-tier script itself.
4. **Documented copies equal the roster.** Discovered, not enumerated: anywhere
   under ``CLAUDE.md`` / ``docs/`` / ``.claude/skills/``, a run of two or more
   *consecutive lines* each invoking a ``./dev health-<name>`` target is a roster
   copy and is pinned to the array. Contiguity is the discriminator, not a fence:
   a copy may be a bash block or a Markdown table, while the single-target usage
   examples the guides are full of ("after file renames, run
   ``./dev health-links``") sit alone between prose lines.

Both filters, because one is not enough
---------------------------------------
``unit_tests`` runs on ci.yml's ``py`` filter, which covers directions 1-3 (the
array in ``dev``, the scripts, the janitor). Direction 4's corpus is all of
``docs/`` and ``.claude/skills/``, and a docs-only PR skips ``unit_tests``
entirely — so this module ALSO runs as a step in the ``validate_documentation``
job, which the ``docs`` filter gates. Listing the files that carry a copy in
``py`` instead would cover today's copies and miss tomorrow's.
(``docs/tools/HEALTH_CHECKS.md`` is in ``py`` as well, so a change to the pinned
copy reds both jobs rather than one.)

Docs pins usually live in ``tests/unit/docs/``; this one lives beside the roster
parser it shares.

Why the roster is one array, and what the discovery threshold is for:
``docs/roadmap/done/catalog-copies-in-code.md`` § 1.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml

APP_ROOT = Path(__file__).resolve().parents[3]
DEV = APP_ROOT / "dev"
JANITOR = APP_ROOT.parent / ".github" / "workflows" / "weekly-janitor.yml"
HEALTH_DIR = APP_ROOT / "scripts" / "health"

# Runnable checks that deliberately have no roster entry. Every entry needs a
# reason; an entry whose script IS in the roster is stale and fails below.
DELIBERATELY_UNREGISTERED: dict[str, str] = {}

# Extraction floor: a parser regression that returns a near-empty roster must fail
# loudly, not pass vacuously against an equally empty corpus.
MIN_ROSTER_ENTRIES = 7

_ARRAY_RE = re.compile(r"^HEALTH_CHECKS=\((?P<body>.*?)^\)", re.MULTILINE | re.DOTALL)
_ENTRY_RE = re.compile(r"^\s*'(?P<entry>[^']*)'\s*$", re.MULTILINE)

# `./dev health-<name>` as a shell invocation — the token a roster copy is made of.
# `--list` and bare `./dev health` are deliberately not matched: they are pointers at
# the roster, not members of it.
_TARGET_RE = re.compile(r"\./dev\s+health-([a-z][a-z0-9-]*)")


class RosterEntry:
    """One parsed ``HEALTH_CHECKS`` element."""

    __slots__ = ("help_text", "message", "name", "script", "tier")

    def __init__(self, raw: str) -> None:
        fields = raw.split("|")
        assert len(fields) == 5, (
            f"HEALTH_CHECKS entry must be name|script|tier|message|help, got {raw!r}"
        )
        self.name, self.script, self.tier, self.message, self.help_text = fields
        assert self.tier in {"health", "target"}, (
            f"unknown tier {self.tier!r} for health check {self.name!r} — "
            "'health' runs inside ./dev health, 'target' is reachable only by name"
        )
        assert self.name and self.script and self.message and self.help_text, (
            f"HEALTH_CHECKS entry {raw!r} has an empty field"
        )


def roster() -> list[RosterEntry]:
    """Every ``HEALTH_CHECKS`` element, in declaration order."""
    match = _ARRAY_RE.search(DEV.read_text(encoding="utf-8"))
    assert match is not None, "HEALTH_CHECKS array not found in app/dev"
    return [RosterEntry(m.group("entry")) for m in _ENTRY_RE.finditer(match.group("body"))]


def health_tier() -> list[RosterEntry]:
    return [entry for entry in roster() if entry.tier == "health"]


def runnable_health_scripts() -> set[str]:
    """``scripts/health/*.py`` files with a ``__main__`` guard — i.e. checks.

    The guard is the discriminator on purpose: ``markdown_fences.py`` is a shared
    library in the same directory, and a bare directory glob would demand a roster
    entry for it.
    """
    found: set[str] = set()
    for path in sorted(HEALTH_DIR.glob("*.py")):
        if '__name__ == "__main__"' in path.read_text(encoding="utf-8"):
            found.add(path.relative_to(APP_ROOT).as_posix())
    return found


def test_roster_parses_above_the_floor() -> None:
    entries = roster()
    assert len(entries) >= MIN_ROSTER_ENTRIES, (
        f"only {len(entries)} HEALTH_CHECKS entries parsed from app/dev — "
        "the extractor regressed, not the roster."
    )
    names = [entry.name for entry in entries]
    assert len(set(names)) == len(names), f"duplicate roster names: {sorted(names)}"
    assert len(health_tier()) >= 1, "no tier-'health' entries — ./dev health would run nothing"


def test_every_roster_script_exists() -> None:
    missing = [entry.script for entry in roster() if not (APP_ROOT / entry.script).is_file()]
    assert not missing, f"HEALTH_CHECKS names scripts that do not exist: {missing}"


def test_list_mode_matches_the_array() -> None:
    """The janitor's door must hand back exactly the tier-'health' entries.

    Executed, not parsed: the array is only a source if the script emits it.
    """
    completed = subprocess.run(
        ["bash", str(DEV), "health", "--list"],
        cwd=APP_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    printed = [line for line in completed.stdout.splitlines() if line.strip()]
    expected = [f"{entry.name}:{entry.script}" for entry in health_tier()]
    assert printed == expected, (
        f"`./dev health --list` printed {printed}, HEALTH_CHECKS' health tier is {expected}"
    )


def test_every_runnable_health_script_is_in_the_roster() -> None:
    registered = {entry.script for entry in roster()}
    missing = sorted(runnable_health_scripts() - registered - set(DELIBERATELY_UNREGISTERED))
    assert not missing, (
        f"runnable scripts/health checks with no HEALTH_CHECKS entry: {missing}. "
        "Add a roster entry in app/dev, or register the script in "
        "DELIBERATELY_UNREGISTERED with a reason."
    )


def test_unregistered_exemptions_are_not_stale() -> None:
    registered = {entry.script for entry in roster()}
    stale = sorted(set(DELIBERATELY_UNREGISTERED) & registered)
    assert not stale, (
        f"DELIBERATELY_UNREGISTERED entries that ARE in the roster: {stale}. "
        "Delete the exemption — an exemption that exempts nothing rots."
    )


def test_a_library_without_main_is_not_demanded() -> None:
    """The discriminator, pinned: ``markdown_fences.py`` is a library, not a check.

    A directory glob without the ``__main__`` test would report it missing from the
    roster, and the fix would be to run a module that has no entry point.
    """
    walker = HEALTH_DIR / "markdown_fences.py"
    assert walker.is_file(), "markdown_fences.py moved — re-point this guard"
    assert walker.relative_to(APP_ROOT).as_posix() not in runnable_health_scripts()


def test_a_check_outside_the_health_directory_is_still_covered() -> None:
    """The other trap: ``validate_cross_references.py`` is not under ``scripts/health/``."""
    outside = [entry.script for entry in roster() if not entry.script.startswith("scripts/health/")]
    assert outside, (
        "no roster entry outside scripts/health/ — if the xref check moved, this "
        "guard's premise (the family is a roster, not a directory) needs re-checking"
    )
    for script in outside:
        assert (APP_ROOT / script).is_file()


def test_the_janitor_consumes_the_roster_and_enumerates_nothing() -> None:
    """The weekly janitor must read ``./dev health --list``, not its own list."""
    text = JANITOR.read_text(encoding="utf-8")
    assert yaml.safe_load(text), "weekly-janitor.yml does not parse"
    assert "./dev health --list" in text, (
        "weekly-janitor.yml no longer consumes `./dev health --list` — it is "
        "enumerating the roster again, which is the drift this seam removes."
    )
    named = set(re.findall(r"scripts/health/[a-z_]+\.py", text))
    health_scripts = {entry.script for entry in health_tier()}
    leaked = sorted(named & health_scripts)
    assert not leaked, (
        f"weekly-janitor.yml names health-tier scripts directly: {leaked}. "
        "The roster arrives through `./dev health --list`; naming a member here "
        "re-creates the copy."
    )


# ---------------------------------------------------------------------------
# Documented copies — discovered, never enumerated
# ---------------------------------------------------------------------------


def _doc_files() -> list[Path]:
    files = [APP_ROOT / "CLAUDE.md", *sorted((APP_ROOT / "docs").rglob("*.md"))]
    files += sorted((APP_ROOT / ".claude" / "skills").rglob("*.md"))
    return [f for f in files if f.is_file()]


def documented_rosters() -> list[tuple[Path, int, frozenset[str]]]:
    """Runs of 2+ consecutive lines each invoking a ``./dev health-<name>`` target.

    Two consecutive lines is the threshold that tells a roster from a usage example:
    the guides show ``./dev health-links`` alone under "after file renames", between
    prose lines, and pinning that to the full roster would be nonsense. Contiguity
    also makes the shape irrelevant — the copies found in the wild were one fenced
    bash block and one Markdown table.

    ``./dev health`` and ``./dev health --list`` are pointers at the roster, not
    members of it, so they neither start a run nor break one's membership; they do
    break contiguity, which is why the pinned block puts them above the targets.
    """
    found: list[tuple[Path, int, frozenset[str]]] = []
    for path in _doc_files():
        start: int | None = None
        targets: set[str] = set()
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            hits = _TARGET_RE.findall(line)
            if hits:
                if start is None:
                    start = lineno
                targets.update(hits)
                continue
            if start is not None and lineno - start >= 2:
                found.append((path, start, frozenset(targets)))
            start = None
            targets = set()
        if start is not None and len(targets) >= 2:
            found.append((path, start, frozenset(targets)))
    return found


# The copy known when this module was written. `test_copies_are_discovered` asserts
# it is still found, so a discovery bug cannot make the pin below vacuous.
KNOWN_COPIES = frozenset({"docs/tools/HEALTH_CHECKS.md"})


def test_copies_are_discovered() -> None:
    names = {p.relative_to(APP_ROOT).as_posix() for p, _, _ in documented_rosters()}
    assert names >= KNOWN_COPIES, (
        f"expected the known documented roster(s) to be discovered, found {sorted(names)}"
    )


def _copy_id(value: object) -> str:
    if isinstance(value, Path):
        return value.relative_to(APP_ROOT).as_posix()
    if isinstance(value, int):
        return f"L{value}"
    return ""


@pytest.mark.parametrize(("path", "line", "targets"), documented_rosters(), ids=_copy_id)
def test_documented_roster_equals_the_roster(
    path: Path, line: int, targets: frozenset[str]
) -> None:
    where = f"{path.relative_to(APP_ROOT).as_posix()}:{line}"
    expected = {entry.name for entry in roster()}
    missing = sorted(expected - targets)
    extra = sorted(targets - expected)
    assert not missing and not extra, (
        f"{where} lists `./dev health-*` targets that disagree with app/dev's "
        f"HEALTH_CHECKS — missing: {missing or 'none'}; not a target: {extra or 'none'}. "
        "Either complete the block or replace it with a pointer at "
        "docs/tools/HEALTH_CHECKS.md."
    )
