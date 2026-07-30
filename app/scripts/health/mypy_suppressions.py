#!/usr/bin/env python3
"""
MyPy Suppression Auditor
========================

The mypy counterpart to SKUEL026. SKUEL026 flags any `# skuel-lint: disable=...`
comment that suppresses nothing; mypy had no equivalent, so its suppressions
accrued drift silently until PR #876 swept them by hand. This script makes that
sweep repeatable.

Reports two kinds of dead mypy suppression:

  1. VACUOUS `disable_error_code` entries — an (override block, error code) pair
     that currently suppresses ZERO errors. Harmless today, but a code that
     suppresses nothing does not suppress nothing forever: it silently eats the
     FIRST real violation of that code that anyone writes in its scope.

  2. UNUSED override sections — module patterns mypy itself reports under
     `unused section(s)` because they match nothing. mypy prints this as a
     *note* and exits 0, so it scrolls past every CI run unread. #876 found five
     that had been dead long enough that nobody remembered them.


MEASUREMENT
-----------
For each (block, code) pair: write a copy of pyproject.toml with that ONE code
removed from that ONE block, everything else intact, and run
`uv run mypy . --config-file <temp>`. Errors are attributed by the trailing
`[code-name]` and diffed against a baseline run of the unmodified config. Zero
new errors of that code ⇒ the entry suppresses nothing.

The text surgery is verified by re-parsing the generated config with `tomllib`
and asserting the override list matches the intended edit exactly. The edit is
never trusted on its own — the parser is the authority on what the config says.


WHY THE UNIT IS (BLOCK, CODE) AND NOT CODE
------------------------------------------
#876 measured in two steps: strip ALL codes at once and attribute by code, then
confirm each zero individually, because an aggregate run lets one error class
shadow another. That second step is necessary but it is still not sufficient,
because both steps measure a CODE while the thing you delete is a (block, code)
pair — and today `misc` is disabled in two different blocks. An aggregate that
reports `misc 32` cannot tell you whether both blocks earn it or whether all 32
errors sit in one of them and the other entry has been inert for months. Same
mistake #876 is about: scoring a suppressor on a proxy for the mechanism instead
of the mechanism.

So the per-pair run is the verdict, and the aggregate is demoted to `--census`
(off by default) — it refreshes the backlog figures quoted in pyproject.toml's
comments, and it is explicitly NOT evidence for a deletion.

Corollary on fail-safe direction: this rule under-reports rather than
over-reports. Stripping one pair can only surface errors inside that block's own
scope, so a non-zero count is conclusive proof the entry is load-bearing, while a
zero is confirmed by the one run that isolates it. There is no approximation in
the deletion path.


WHERE THIS RUNS AND WHY
-----------------------
The audit needs one baseline run plus one run per (block, code) pair. A cold mypy
run over this tree is ~30s, but the runs share a dedicated cache, so the rest cost
~8s each: measured end to end at 65-81s for today's five pairs plus `--census`
(seven runs). That cost decides the wiring three ways:

  * NOT in `./dev health`. That target is pure file-scanning and finishes in
    seconds; an ~80s tail is how a health target stops being run at all. A
    suppression audit nobody runs is precisely the drift this script exists to
    prevent, so making the fast target slow would be self-defeating.

  * YES as `./dev health-mypy`, matching the existing per-check targets
    (`health-modules`, `health-links`, `health-names`, `health-xref`). This is
    the local entry point — run it when touching pyproject.toml's mypy config.

  * YES in CI, but on a SCHEDULE, not the PR path. Path-scoping a PR job to
    pyproject.toml would only catch the entry-added-and-never-earned case. The
    dangerous case is the other one: source gets fixed, the last error of a code
    disappears, and an entry that was load-bearing yesterday is now a silent trap
    — with pyproject.toml untouched, so no path filter fires. That needs a run
    not gated on the config file. Drift here accrues over months (#876's finds
    were long dead), so a weekly scheduled run catches it with zero added latency
    on every PR.

Usage:
    uv run python scripts/health/mypy_suppressions.py
    uv run python scripts/health/mypy_suppressions.py --verbose
    uv run python scripts/health/mypy_suppressions.py --census
"""

import argparse
import ast
import json
import re
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from core.utils.terminal_colors import Colors

ROOT = Path(__file__).parent.parent.parent  # /home/mike/skuel/app
PYPROJECT = ROOT / "pyproject.toml"

# The generated config lives in ROOT so that every relative path in it
# (files, exclude regexes, explicit_package_bases) resolves exactly as it does
# for the real pyproject.toml. mypy is always invoked with cwd=ROOT for the
# same reason.
TEMP_CONFIG = ROOT / ".mypy_suppressions_audit.toml"

# A dedicated cache dir keeps the audit's config churn from invalidating the
# real .mypy_cache that ./dev quality and CI depend on.
AUDIT_CACHE = ROOT / ".mypy_cache_suppression_audit"

TABLE_HEADER_RE = re.compile(r"^\[\[?[^\[\]]+\]\]?\s*(?:#.*)?$")
OVERRIDE_HEADER = "[[tool.mypy.overrides]]"

# `path:line:col: error: message  [code]` under --no-pretty --no-color-output.
ERROR_RE = re.compile(
    r"^(?P<path>.+?):(?P<line>\d+):(?:(?P<col>\d+):)?\s+error:\s+"
    r"(?P<msg>.*?)(?:\s+\[(?P<code>[\w-]+)\])?$"
)
UNUSED_RE = re.compile(r"note:\s*unused section\(s\):\s*module\s*=\s*(?P<mods>\[.*\])")

DEC_ASSIGN_RE = re.compile(r"^(?P<indent>\s*)disable_error_code\s*=")


@dataclass(frozen=True)
class MypyError:
    path: str
    line: str
    col: str
    code: str
    msg: str


@dataclass
class Override:
    """One `[[tool.mypy.overrides]]` block, as parsed AND as located in the text."""

    index: int
    header_line: int  # 1-based line of the [[tool.mypy.overrides]] header
    modules: list[str]
    codes: list[str]  # its disable_error_code list ([] when absent)


@dataclass
class PairVerdict:
    override: Override
    code: str
    new_errors: list[MypyError] = field(default_factory=list)

    @property
    def is_vacuous(self) -> bool:
        return not self.new_errors


class AuditError(RuntimeError):
    """The instrument could not establish what it measures — never a finding."""


# ---------------------------------------------------------------------------
# Parsing pyproject.toml
# ---------------------------------------------------------------------------


def _as_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value]
    return []


def parse_overrides(text: str) -> list[Override]:
    """
    Parse every `[[tool.mypy.overrides]]` block, pairing tomllib's parse with the
    header line each block occupies in the text.

    TOML preserves array-of-table order, so the Nth header in the text is the Nth
    entry in the parsed list. That correspondence is asserted, not assumed — if
    the counts disagree the file uses a shape this script cannot edit safely and
    the audit aborts rather than guessing.
    """
    data = tomllib.loads(text)
    parsed = data.get("tool", {}).get("mypy", {}).get("overrides", [])

    lines = text.splitlines()
    header_lines = [i + 1 for i, line in enumerate(lines) if line.strip() == OVERRIDE_HEADER]

    if len(header_lines) != len(parsed):
        raise AuditError(
            f"Found {len(header_lines)} '{OVERRIDE_HEADER}' header lines but tomllib "
            f"parsed {len(parsed)} override blocks. The header must sit alone on its "
            f"own line for this script to locate blocks in the text."
        )

    return [
        Override(
            index=i,
            header_line=header_lines[i],
            modules=_as_list(block.get("module")),
            codes=_as_list(block.get("disable_error_code")),
        )
        for i, block in enumerate(parsed)
    ]


def _block_span(lines: list[str], overrides: list[Override], index: int) -> tuple[int, int]:
    """0-based [start, end) line span of override `index`, ending at the next table header."""
    start = overrides[index].header_line - 1
    for j in range(start + 1, len(lines)):
        if TABLE_HEADER_RE.match(lines[j]):
            return start, j
    return start, len(lines)


def _find_dec_span(lines: list[str], start: int, end: int) -> tuple[int, int] | None:
    """0-based inclusive line span of the block's `disable_error_code = [...]` assignment."""
    for j in range(start, end):
        if not DEC_ASSIGN_RE.match(lines[j]):
            continue
        depth = 0
        for k in range(j, end):
            depth += lines[k].count("[") - lines[k].count("]")
            if depth <= 0:
                return j, k
        raise AuditError(
            f"Unbalanced brackets in the disable_error_code assignment at line {j + 1}."
        )
    return None


def render_stripped(text: str, removals: dict[int, set[str]]) -> str:
    """Return `text` with the given codes removed from the given override blocks."""
    overrides = parse_overrides(text)
    lines = text.splitlines()

    # Edit from the bottom up so earlier spans keep their indices.
    for index in sorted(removals, reverse=True):
        drop = removals[index]
        if not drop:
            continue
        start, end = _block_span(lines, overrides, index)
        span = _find_dec_span(lines, start, end)
        if span is None:
            raise AuditError(
                f"Override block {index} has no disable_error_code assignment to strip."
            )
        first, last = span
        kept = [c for c in overrides[index].codes if c not in drop]
        indent = DEC_ASSIGN_RE.match(lines[first]).group("indent")  # type: ignore[union-attr]
        rendered = ", ".join(json.dumps(c) for c in kept)
        lines[first : last + 1] = [f"{indent}disable_error_code = [{rendered}]"]

    return "\n".join(lines) + "\n"


def write_stripped_config(text: str, removals: dict[int, set[str]], path: Path) -> None:
    """
    Write the stripped config, then VERIFY it by re-parsing.

    The text surgery above is a means; `tomllib` is the authority on what the
    written file actually says. If the parse does not match the intended edit
    exactly — same block count, same modules, same remaining codes — the audit
    aborts. A wrong config would otherwise produce a confident wrong verdict.
    """
    original = parse_overrides(text)
    path.write_text(render_stripped(text, removals), encoding="utf-8")
    written = parse_overrides(path.read_text(encoding="utf-8"))

    if len(written) != len(original):
        raise AuditError(
            f"Stripped config has {len(written)} override blocks, expected {len(original)}."
        )
    for before, after in zip(original, written, strict=True):
        if before.modules != after.modules:
            raise AuditError(
                f"Stripped config changed block {before.index} modules: "
                f"{before.modules} -> {after.modules}"
            )
        expected = [c for c in before.codes if c not in removals.get(before.index, set())]
        if after.codes != expected:
            raise AuditError(
                f"Stripped config block {before.index} has codes {after.codes}, "
                f"expected {expected}."
            )


# ---------------------------------------------------------------------------
# Running mypy
# ---------------------------------------------------------------------------


def run_mypy(config: Path) -> str:
    """Run mypy over the tree with `config`, returning combined output."""
    proc = subprocess.run(
        [
            "uv",
            "run",
            "mypy",
            ".",
            "--config-file",
            str(config),
            "--cache-dir",
            str(AUDIT_CACHE),
            "--no-pretty",
            "--no-color-output",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout + proc.stderr


def parse_errors(output: str) -> set[MypyError]:
    errors = set()
    for line in output.splitlines():
        match = ERROR_RE.match(line.rstrip())
        if match and match.group("code"):
            errors.add(
                MypyError(
                    path=match.group("path"),
                    line=match.group("line"),
                    col=match.group("col") or "",
                    code=match.group("code"),
                    msg=match.group("msg"),
                )
            )
    return errors


def parse_unused_sections(output: str) -> list[str]:
    """
    Extract the module patterns from mypy's own `unused section(s)` note.

    Read straight off mypy's output rather than re-deriving which patterns match
    nothing — mypy already resolved every module it checked, and a hand-rolled
    pattern matcher would be a second thing to get wrong.
    """
    for line in output.splitlines():
        match = UNUSED_RE.search(line)
        if match:
            try:
                return [str(m) for m in ast.literal_eval(match.group("mods"))]
            except ValueError, SyntaxError:
                return []
    return []


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _describe(override: Override) -> str:
    modules = ", ".join(override.modules) if override.modules else "(no module key)"
    return f"pyproject.toml:{override.header_line}  module = [{modules}]"


def _print_census(census: dict[str, int]) -> None:
    print(f"\n{Colors.BOLD}Aggregate census (--census){Colors.RESET}")
    print(
        f"{Colors.YELLOW}Every code stripped from every block at once. These are the "
        f"backlog figures quoted in pyproject.toml's comments.{Colors.RESET}"
    )
    print(
        f"{Colors.YELLOW}NOT evidence for a deletion — one error class can shadow "
        f"another, and this cannot tell two blocks sharing a code apart.{Colors.RESET}\n"
    )
    if not census:
        print("  (no errors surfaced)")
        return
    for code, count in sorted(census.items(), key=lambda kv: -kv[1]):
        print(f"  {Colors.CYAN}{code:<20}{Colors.RESET} {count}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Find mypy suppressions that suppress nothing (the SKUEL026 analogue)"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Show each mypy run")
    parser.add_argument(
        "--census",
        action="store_true",
        help="Also run the aggregate all-codes-stripped run for backlog figures",
    )
    args = parser.parse_args()

    print(f"{Colors.BOLD}MyPy Suppression Auditor{Colors.RESET}")
    print("=" * 60)

    text = PYPROJECT.read_text(encoding="utf-8")
    overrides = parse_overrides(text)
    pairs = [(o, code) for o in overrides for code in o.codes]

    print(
        f"{len(overrides)} override blocks, {len(pairs)} (block, code) pairs to verify.\n"
        f"{Colors.DIM}One mypy run each plus a baseline — this takes a few minutes.{Colors.RESET}\n"
    )

    try:
        # Baseline: the config exactly as committed. Establishes both the
        # already-visible error set to diff against and mypy's unused-section note.
        if args.verbose:
            print(f"{Colors.DIM}  baseline: pyproject.toml as committed{Colors.RESET}")
        baseline_output = run_mypy(PYPROJECT)
        baseline_errors = parse_errors(baseline_output)
        unused_sections = parse_unused_sections(baseline_output)

        verdicts: list[PairVerdict] = []
        for override, code in pairs:
            if args.verbose:
                print(
                    f"{Colors.DIM}  un-suppressing [{code}] in block "
                    f"{override.index} (line {override.header_line}){Colors.RESET}"
                )
            write_stripped_config(text, {override.index: {code}}, TEMP_CONFIG)
            errors = parse_errors(run_mypy(TEMP_CONFIG))
            new = sorted(
                (e for e in errors - baseline_errors if e.code == code),
                key=lambda e: (e.path, int(e.line)),
            )
            verdicts.append(PairVerdict(override=override, code=code, new_errors=new))

        census: dict[str, int] = {}
        if args.census:
            if args.verbose:
                print(f"{Colors.DIM}  aggregate: every code stripped at once{Colors.RESET}")
            write_stripped_config(
                text, {o.index: set(o.codes) for o in overrides if o.codes}, TEMP_CONFIG
            )
            for error in parse_errors(run_mypy(TEMP_CONFIG)) - baseline_errors:
                census[error.code] = census.get(error.code, 0) + 1
    finally:
        TEMP_CONFIG.unlink(missing_ok=True)
        shutil.rmtree(AUDIT_CACHE, ignore_errors=True)

    vacuous = [v for v in verdicts if v.is_vacuous]
    load_bearing = [v for v in verdicts if not v.is_vacuous]

    if load_bearing:
        print(f"{Colors.GREEN}Load-bearing disable_error_code entries:{Colors.RESET}")
        for verdict in sorted(load_bearing, key=lambda v: -len(v.new_errors)):
            print(
                f"  {Colors.GREEN}●{Colors.RESET} {Colors.CYAN}{verdict.code}{Colors.RESET} "
                f"suppresses {Colors.BOLD}{len(verdict.new_errors)}{Colors.RESET} errors"
            )
            print(f"      {Colors.DIM}{_describe(verdict.override)}{Colors.RESET}")
        print()

    if vacuous:
        print(
            f"{Colors.RED}{Colors.BOLD}Vacuous disable_error_code entries — "
            f"{len(vacuous)} suppressing 0 errors:{Colors.RESET}"
        )
        print(
            f"{Colors.YELLOW}Each will silently eat the FIRST real violation of that "
            f"code in its scope. Delete them.{Colors.RESET}\n"
        )
        for verdict in vacuous:
            print(f"  {Colors.RED}●{Colors.RESET} {Colors.BOLD}{verdict.code}{Colors.RESET}")
            print(f"      {_describe(verdict.override)}")
        print()

    if unused_sections:
        print(
            f"{Colors.RED}{Colors.BOLD}Unused override sections — "
            f"{len(unused_sections)} matching no module:{Colors.RESET}"
        )
        print(
            f"{Colors.YELLOW}Reported by mypy itself as a note, which exits 0 and "
            f"scrolls past unread. Delete the patterns.{Colors.RESET}\n"
        )
        for pattern in unused_sections:
            owners = [o for o in overrides if pattern in o.modules]
            location = _describe(owners[0]) if owners else "pyproject.toml"
            print(f"  {Colors.RED}●{Colors.RESET} {Colors.BOLD}{pattern}{Colors.RESET}")
            print(f"      {Colors.DIM}{location}{Colors.RESET}")
        print()

    if args.census:
        _print_census(census)
        print()

    findings = len(vacuous) + len(unused_sections)
    if findings:
        print(
            f"{Colors.RED}Total: {len(vacuous)} vacuous entries, "
            f"{len(unused_sections)} unused sections{Colors.RESET}"
        )
        return 1

    print(
        f"{Colors.GREEN}✓ No dead mypy suppressions "
        f"({len(load_bearing)} entries verified load-bearing){Colors.RESET}"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AuditError as exc:
        print(f"{Colors.RED}Audit aborted: {exc}{Colors.RESET}", file=sys.stderr)
        sys.exit(2)
