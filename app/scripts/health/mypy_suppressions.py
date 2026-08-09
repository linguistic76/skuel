#!/usr/bin/env python3
"""
MyPy Suppression Auditor
========================

The mypy counterpart to SKUEL026. SKUEL026 flags any `# skuel-lint: disable=...`
comment that suppresses nothing; mypy had no equivalent, so its suppressions
accrued drift silently until PR #876 swept them by hand. This script makes that
sweep repeatable.

Reports two kinds of dead mypy suppression:

  1. VACUOUS `disable_error_code` entries — a (scope, error code) pair that
     currently suppresses ZERO errors. A scope is either the global `[tool.mypy]`
     table or one `[[tool.mypy.overrides]]` block; both are audited, because the
     global table is the WIDEST suppression there is and auditing only the
     overrides would leave it permanently invisible behind a clean report.
     Harmless today, but a code that suppresses nothing does not suppress nothing
     forever: it silently eats the FIRST real violation written in its scope.

  2. UNUSED override sections — module patterns mypy itself reports under
     `unused section(s)` because they match nothing. mypy prints this as a
     *note* and exits 0, so it scrolls past every CI run unread. #876 found five
     that had been dead long enough that nobody remembered them.


MEASUREMENT
-----------
For each (scope, code) pair: write a copy of pyproject.toml with that ONE code
removed from that ONE scope, everything else intact, and run
`uv run mypy . --config-file <temp>`. Errors are attributed by the trailing
`[code-name]` and diffed against a baseline run of the unmodified config. Zero
new errors of that code ⇒ the entry suppresses nothing.

For each multi-pattern pair that measures load-bearing, one further run per
module pattern: append an enable-only override for that single pattern to the
otherwise-unmodified config (see PER-PATTERN VERDICTS below) and diff the same
way. Zero new errors of the code ⇒ that pattern's membership suppresses nothing.
Single-pattern scopes need no extra run — the pair run already isolates them —
and a vacuous pair is already the stronger finding.

The text surgery is verified by re-parsing the generated config with `tomllib`
and asserting the scope list matches the intended edit exactly. The edit is
never trusted on its own — the parser is the authority on what the config says.


WHY THE UNIT IS (SCOPE, CODE) AND NOT CODE
------------------------------------------
#876 measured in two steps: strip ALL codes at once and attribute by code, then
confirm each zero individually, because an aggregate run lets one error class
shadow another. That second step is necessary but it is still not sufficient,
because both steps measure a CODE while the thing you delete is a (scope, code)
pair — and today `misc` is disabled in two different scopes. An aggregate that
reports `misc 32` cannot tell you whether both earn it or whether all 32 errors
sit in one of them and the other entry has been inert for months. Measured, they
split 24/8. Same mistake #876 is about: scoring a suppressor on a proxy for the
mechanism instead of the mechanism.

So the per-pair run is the verdict, and the aggregate is demoted to `--census`
(off by default) — it refreshes the backlog figures quoted in pyproject.toml's
comments, and it is explicitly NOT evidence for a deletion.

Corollary on fail-safe direction: this rule under-reports rather than
over-reports. Stripping one pair can only surface errors inside that scope's own
files, so a non-zero count is conclusive proof the entry is load-bearing, while a
zero is confirmed by the one run that isolates it.

That holds only for runs that COMPLETED, which is why `run_mypy` aborts the whole
audit on any run it cannot prove finished. A crashed mypy prints no `error:`
lines, and an empty error set is bit-identical to a clean one — so without that
guard the deletion path had exactly the silent-failure shape this script exists
to find (Codex #883). An aborted audit reports nothing; it never reports zero.


WHERE THIS RUNS AND WHY
-----------------------
The audit needs one baseline run, one run per (scope, code) pair, and one run per
module pattern of each multi-pattern load-bearing pair. A cold mypy run over this
tree is ~30s, but the runs share a dedicated cache, so the rest cost ~7s each:
measured end to end at 79s for today's eight pairs plus two pattern probes
(eleven runs; `--census` adds one more). Probe cost scales with multi-pattern
blocks — the pre-narrowing config (five pairs, nineteen probed memberships)
measured 189s, and resolving its findings brought the steady state back down.
That cost decides the wiring three ways:

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

PER-PATTERN VERDICTS (the former known limit, closed 2026-08-09)
----------------------------------------------------------------
A scope may list several module patterns while only some of them actually produce
the code. Through #1000 the verdict stopped at the block, so the backends override
— then seven patterns, with all 8 `misc` errors coming from two — stayed green
while a first violation in the other five would have been eaten (Codex #883 r5).

Each pattern of a multi-pattern, load-bearing pair is now measured on its own:
append an override containing ONLY `module = [<pattern>]` and
`enable_error_code = [<code>]` to an otherwise-unmodified config, and diff
against the same baseline. mypy itself resolves what the pattern matches, so
there is no hand-rolled path-to-pattern mapping to get wrong. A pattern earning
0 is a FINDING: its membership suppresses nothing today, which means it only
stands to eat that pattern's first real violation. Split it out or delete it.

Why the appended override works — measured on this repo's mypy (2.3.0) with a
[misc]-emitting probe file and option-flip match-controls, not read off the
docs: a LATER config-level `enable_error_code` lifts an EARLIER block's
per-module disable in every shape this config uses (concrete pattern over
wildcard, identical wildcard over itself, concrete over concrete). The probe
block must stay enable-only: repeating a SCALAR option for an identical pattern
draws mypy's "conflicting values" warning and the earlier value wins.

Dropping the pattern from the module list and re-measuring would NOT have
worked: for a block that also sets other options — `tests.*` sets five besides
`disable_error_code` — removing a pattern changes all of them for that module
and floods the run with unrelated errors. The appended enable touches nothing
but the one code. The CLI spelling (`mypy --enable-error-code X`) does not work
and never can: command-line enables sit BELOW per-module config sections in
mypy's precedence, so they cannot lift a per-module disable. Measured
2026-08-08: the flag over the tests scope printed `Success: no issues found in
758 source files` while editing the config surfaced 26 errors. Probe by editing
config — by preference, by running this script — never with the flag.

Attribution is reconciled per pair: if the per-pattern counts sum BELOW the
block-level count, some suppressed error belongs to no probe and a pattern zero
cannot be trusted, so the audit aborts. Summing ABOVE it only warns, because
both known causes leave zeros conclusive. Overlapping patterns double-attribute
an error. And a probe's EXPLICIT enable can surface errors the block entry
never suppressed: sub-code inheritance means a file-level comment disabling a
PARENT code (e.g. `assignment`, whose sub-code is `method-assign`) eats an
error under the plain strip, while an explicit enable of the sub-code pierces
it. Measured live: two facade-test files inline-disable `assignment` and their
18 method-assign errors appear only under the probe. Either way, a pattern
reading zero surfaced nothing even under maximal enabling.

The report still prints the FILES behind each load-bearing verdict, verbatim
from mypy — they remain the fastest way to eyeball a verdict against the
rationale comment sitting above the entry in pyproject.toml.


EXIT CODES
----------
    0 — clean
    1 — CONFIRMED findings, and nothing else
    2 — the instrument could not measure, for any reason

Exit 1 is load-bearing: the scheduled workflow opens an issue on it asserting
that dead suppressions were found, so anything that is not a confirmed finding
must not use it. See `run_cli`.

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
import traceback
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
GLOBAL_TABLE_HEADER = "[tool.mypy]"

# The global `[tool.mypy]` table is a suppression scope too — the widest one.
# It gets a sentinel index so it can share the Override machinery.
GLOBAL_SCOPE_INDEX = -1

# `path:line:col: error: message  [code]` under --no-pretty --no-color-output.
ERROR_RE = re.compile(
    r"^(?P<path>.+?):(?P<line>\d+):(?:(?P<col>\d+):)?\s+error:\s+"
    r"(?P<msg>.*?)(?:\s+\[(?P<code>[\w-]+)\])?$"
)
UNUSED_RE = re.compile(r"note:\s*unused section\(s\):\s*module\s*=\s*(?P<mods>\[.*\])")

# Evidence that mypy actually finished, rather than dying silently. See run_mypy.
MYPY_SUMMARY_RE = re.compile(r"^(?:Success: no issues found|Found \d+ error)", re.MULTILINE)
COMPLETED_EXIT_CODES = frozenset({0, 1})

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


@dataclass
class PatternVerdict:
    """One module pattern's own share of a multi-pattern (scope, code) pair."""

    override: Override
    code: str
    pattern: str
    new_errors: list[MypyError] = field(default_factory=list)

    @property
    def is_unearned(self) -> bool:
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


def parse_global_scope(text: str) -> Override | None:
    """
    Parse a `disable_error_code` on the global `[tool.mypy]` table, if present.

    A global suppression is the widest scope there is — it silences a code across
    every checked file — and auditing only `[[tool.mypy.overrides]]` would leave it
    permanently invisible, with the report still printing a clean bill of health
    (Codex #883 r2). This repo has carried a global entry before; the note at the
    top of the `[tool.mypy]` table records its deletion.

    Returned as an `Override` at index GLOBAL_SCOPE_INDEX with no modules, since
    "no module filter" is exactly what global scope means.
    """
    data = tomllib.loads(text)
    mypy_table = data.get("tool", {}).get("mypy", {})
    # Keyed on PRESENCE, not truthiness: stripping a single-code global scope
    # leaves `disable_error_code = []`, and a scope that vanished from the parse
    # would trip write_stripped_config's own count check as if the edit had gone
    # wrong. An empty list is still a scope; a missing key is not.
    if "disable_error_code" not in mypy_table:
        return None
    codes = _as_list(mypy_table["disable_error_code"])

    lines = text.splitlines()
    header_lines = [i + 1 for i, line in enumerate(lines) if line.strip() == GLOBAL_TABLE_HEADER]
    if len(header_lines) != 1:
        raise AuditError(
            f"Expected exactly one '{GLOBAL_TABLE_HEADER}' header line, found "
            f"{len(header_lines)}. Cannot locate the global scope in the text."
        )

    return Override(index=GLOBAL_SCOPE_INDEX, header_line=header_lines[0], modules=[], codes=codes)


def parse_scopes(text: str) -> list[Override]:
    """Every scope that can carry `disable_error_code`: global first, then overrides."""
    global_scope = parse_global_scope(text)
    overrides = parse_overrides(text)
    return [global_scope, *overrides] if global_scope else overrides


def _scope_span(lines: list[str], scope: Override) -> tuple[int, int]:
    """0-based [start, end) line span of `scope`, ending at the next table header."""
    start = scope.header_line - 1
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
    """Return `text` with the given codes removed from the given scopes."""
    scopes = {scope.index: scope for scope in parse_scopes(text)}
    lines = text.splitlines()

    # Edit by descending header line so earlier spans keep their indices. Sorting
    # on the line, not the index, keeps the global scope (index -1, but the FIRST
    # table in the file) in its true textual position.
    for index in sorted(removals, key=lambda i: -scopes[i].header_line):
        drop = removals[index]
        if not drop:
            continue
        scope = scopes[index]
        start, end = _scope_span(lines, scope)
        span = _find_dec_span(lines, start, end)
        if span is None:
            raise AuditError(f"Scope {_scope_name(scope)} has no disable_error_code to strip.")
        first, last = span
        kept = [c for c in scope.codes if c not in drop]
        indent = DEC_ASSIGN_RE.match(lines[first]).group("indent")  # type: ignore[union-attr]
        rendered = ", ".join(json.dumps(c) for c in kept)
        lines[first : last + 1] = [f"{indent}disable_error_code = [{rendered}]"]

    return "\n".join(lines) + "\n"


def write_stripped_config(text: str, removals: dict[int, set[str]], path: Path) -> None:
    """
    Write the stripped config, then VERIFY it by re-parsing.

    The text surgery above is a means; `tomllib` is the authority on what the
    written file actually says. If the parse does not match the intended edit
    exactly — same scope count, same modules, same remaining codes — the audit
    aborts. A wrong config would otherwise produce a confident wrong verdict.
    """
    original = parse_scopes(text)
    path.write_text(render_stripped(text, removals), encoding="utf-8")
    written = parse_scopes(path.read_text(encoding="utf-8"))

    if len(written) != len(original):
        raise AuditError(
            f"Stripped config has {len(written)} suppression scopes, expected {len(original)}."
        )
    for before, after in zip(original, written, strict=True):
        if before.modules != after.modules:
            raise AuditError(
                f"Stripped config changed scope {_scope_name(before)} modules: "
                f"{before.modules} -> {after.modules}"
            )
        expected = [c for c in before.codes if c not in removals.get(before.index, set())]
        if after.codes != expected:
            raise AuditError(
                f"Stripped config scope {_scope_name(before)} has codes {after.codes}, "
                f"expected {expected}."
            )


def render_probe(text: str, pattern: str, code: str) -> str:
    """Return `text` with an appended enable-only override probing one pattern.

    Appending at end-of-file places the block after every existing override —
    TOML array-of-tables order is file order — which is what makes its
    `enable_error_code` win over an earlier block's disable for the same
    module (see PER-PATTERN VERDICTS in the module docstring). The block stays
    enable-only on purpose: repeating a scalar option for an identical pattern
    draws mypy's "conflicting values" warning, and the earlier value wins.
    """
    block = (
        "\n[[tool.mypy.overrides]]\n"
        "# Per-pattern probe appended by mypy_suppressions.py; never committed.\n"
        f"module = [{json.dumps(pattern)}]\n"
        f"enable_error_code = [{json.dumps(code)}]\n"
    )
    return text + ("" if text.endswith("\n") else "\n") + block


def write_probe_config(text: str, pattern: str, code: str, path: Path) -> None:
    """Write the probe config, then VERIFY it by re-parsing.

    Same discipline as write_stripped_config: the append is a means, `tomllib`
    is the authority on what the written file says. Every pre-existing scope
    must be untouched, and the last override must contain EXACTLY the probed
    module and the enable — a stray key or a mangled pattern would measure the
    wrong thing and read as a pattern earning nothing, which points at deleting
    a live pattern.
    """
    original = parse_scopes(text)
    path.write_text(render_probe(text, pattern, code), encoding="utf-8")
    written_text = path.read_text(encoding="utf-8")
    written = parse_scopes(written_text)

    if len(written) != len(original) + 1:
        raise AuditError(
            f"Probe config has {len(written)} suppression scopes, expected "
            f"{len(original) + 1} (the originals plus the probe)."
        )
    for before, after in zip(original, written[:-1], strict=True):
        if before.modules != after.modules or before.codes != after.codes:
            raise AuditError(
                f"Probe config changed pre-existing scope {_scope_name(before)}: "
                f"modules {before.modules} -> {after.modules}, "
                f"codes {before.codes} -> {after.codes}"
            )
    probe_block = tomllib.loads(written_text)["tool"]["mypy"]["overrides"][-1]
    if set(probe_block) != {"module", "enable_error_code"} or (
        _as_list(probe_block.get("module")) != [pattern]
        or _as_list(probe_block.get("enable_error_code")) != [code]
    ):
        raise AuditError(
            f"Probe block reads {probe_block!r}, expected exactly "
            f"module = [{pattern!r}] with enable_error_code = [{code!r}]."
        )


def reconcile_pattern_counts(pair: PairVerdict, patterns: list[PatternVerdict]) -> str | None:
    """Check the per-pattern counts account for every block-suppressed error.

    Summing BELOW the pair count means some suppressed error surfaced in no
    probe — the per-pattern instrument is blind somewhere, and a pattern zero
    can no longer be trusted, so the audit ABORTS (the zero is the direction
    that licenses a deletion).

    Summing ABOVE it warns and keeps going, because both known causes leave
    zeros conclusive. Overlapping patterns double-attribute an error. And the
    probe's EXPLICIT enable is stronger than the strip's mere not-disabling:
    sub-code inheritance means a file-level `# mypy: disable-error-code`
    comment naming a PARENT code (e.g. `assignment` over `method-assign`)
    still eats the error under the strip, while the probe's explicit enable of
    the sub-code pierces it and surfaces errors the block entry never
    suppressed. Either way a zero still means the probe surfaced nothing even
    under maximal enabling.
    """
    total = sum(len(p.new_errors) for p in patterns)
    if total < len(pair.new_errors):
        raise AuditError(
            f"Per-pattern probes for [{pair.code}] in {_scope_name(pair.override)} "
            f"account for {total} of {len(pair.new_errors)} suppressed errors. "
            f"An unattributed error means a pattern zero cannot be trusted."
        )
    if total > len(pair.new_errors):
        return (
            f"per-pattern counts sum to {total} against {len(pair.new_errors)} for "
            f"the pair — probes also pierce file-level parent-code suppression, and "
            f"overlapping patterns double-attribute; zeros remain valid"
        )
    return None


# ---------------------------------------------------------------------------
# Running mypy
# ---------------------------------------------------------------------------


def run_mypy(config: Path) -> str:
    """
    Run mypy over the tree with `config`, returning combined output.

    A run that did not COMPLETE must abort the audit, never return empty output.
    Silence and cleanliness are the same string here: if mypy dies to a launcher
    fault, a bad config, or an internal crash, it emits no `error:` lines, so
    `parse_errors` returns an empty set, `new_errors` is empty, and the pair reads
    as vacuous — the audit would tell a maintainer to delete a load-bearing
    suppression on the strength of a measurement that never happened. That is the
    one direction this script must not fail in (Codex #883).

    Completion is checked two ways, both of which abort on doubt:
      * exit status — mypy exits 0 (clean) or 1 (errors found) after a completed
        check; 2 is a usage/config error and anything else is a crash or signal;
      * mypy's own summary line, which is the direct evidence it finished.
    """
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
    output = proc.stdout + proc.stderr

    if proc.returncode not in COMPLETED_EXIT_CODES:
        raise AuditError(
            f"mypy exited {proc.returncode} with config {config.name} — a completed "
            f"check exits 0 or 1. No measurement was made; refusing to report on it.\n"
            f"--- last 20 lines ---\n{_tail(output)}"
        )
    if not MYPY_SUMMARY_RE.search(output):
        raise AuditError(
            f"mypy exited {proc.returncode} with config {config.name} but printed no "
            f"summary line, so the check did not complete. Refusing to treat its "
            f"silence as zero errors.\n--- last 20 lines ---\n{_tail(output)}"
        )
    return output


def _tail(output: str, lines: int = 20) -> str:
    return "\n".join(output.splitlines()[-lines:])


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


def _scope_name(scope: Override) -> str:
    return GLOBAL_TABLE_HEADER if scope.index == GLOBAL_SCOPE_INDEX else f"block {scope.index}"


def _describe(scope: Override) -> str:
    if scope.index == GLOBAL_SCOPE_INDEX:
        return f"pyproject.toml:{scope.header_line}  {GLOBAL_TABLE_HEADER} (global — every checked file)"
    modules = ", ".join(scope.modules) if scope.modules else "(no module key)"
    return f"pyproject.toml:{scope.header_line}  module = [{modules}]"


def _print_error_files(verdict: PairVerdict, limit: int = 3) -> None:
    """
    Show WHICH files earned the verdict, straight from mypy's own attribution.

    Multi-pattern scopes now get true per-pattern verdicts (see PER-PATTERN
    VERDICTS in the module docstring); the file list stays because it is the
    fastest way to eyeball a verdict against the rationale comment sitting
    above the entry in pyproject.toml.

    The file list is mypy's, verbatim: no path-to-module-pattern inference, since
    a wrong mapping here would point at deleting a live pattern.
    """
    counts: dict[str, int] = {}
    for error in verdict.new_errors:
        counts[error.path] = counts.get(error.path, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    shown = ", ".join(f"{path} ({n})" for path, n in ranked[:limit])
    if len(ranked) > limit:
        shown += f", and {len(ranked) - limit} more files"
    print(f"      {Colors.DIM}in: {shown}{Colors.RESET}")


def _print_pattern_counts(patterns: list[PatternVerdict]) -> None:
    """Show each pattern's own share of a multi-pattern verdict, probe-measured."""
    shown = ", ".join(f"{p.pattern} ({len(p.new_errors)})" for p in patterns)
    print(f"      {Colors.DIM}patterns: {shown}{Colors.RESET}")


def _print_error_samples(verdict: PairVerdict, limit: int = 3) -> None:
    """
    Show a few of mypy's own messages behind the verdict, verbatim.

    The audit proves an entry is EARNED, never that its stated REASON is true —
    and the rationale comment above an entry drifts: the backends block cited a
    mixin set that no longer conflicts (#883), the tests block cited a
    dependency that had left the tree (#1000). Printing the messages puts the
    evidence next to the comment so a reader can compare the two without
    re-running anything. Verbatim and deduplicated, nothing summarized: an
    inferred paraphrase here would be the kind of confident wrong signal this
    script exists to kill.
    """
    counts: dict[str, int] = {}
    for error in verdict.new_errors:
        counts[error.msg] = counts.get(error.msg, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    for msg, n in ranked[:limit]:
        shown = msg if len(msg) <= 110 else msg[:107] + "..."
        print(f'      {Colors.DIM}msg ({n}x): "{shown}"{Colors.RESET}')
    if len(ranked) > limit:
        remainder = len(ranked) - limit
        print(f"      {Colors.DIM}... and {remainder} more distinct messages{Colors.RESET}")


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
    scopes = parse_scopes(text)
    pairs = [(s, code) for s in scopes for code in s.codes]
    has_global = any(s.index == GLOBAL_SCOPE_INDEX for s in scopes)

    scope_summary = f"{len(scopes)} suppression scopes"
    if has_global:
        scope_summary += f" (incl. the global {GLOBAL_TABLE_HEADER} table)"
    print(
        f"{scope_summary}, {len(pairs)} (scope, code) pairs to verify.\n"
        f"{Colors.DIM}One mypy run per pair, per-pattern probes for multi-pattern "
        f"scopes, plus a baseline — this takes a few minutes.{Colors.RESET}\n"
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
        for scope, code in pairs:
            if args.verbose:
                print(
                    f"{Colors.DIM}  un-suppressing [{code}] in {_scope_name(scope)} "
                    f"(line {scope.header_line}){Colors.RESET}"
                )
            write_stripped_config(text, {scope.index: {code}}, TEMP_CONFIG)
            errors = parse_errors(run_mypy(TEMP_CONFIG))
            new = sorted(
                (e for e in errors - baseline_errors if e.code == code),
                key=lambda e: (e.path, int(e.line)),
            )
            verdicts.append(PairVerdict(override=scope, code=code, new_errors=new))

        # Per-pattern pass: only load-bearing multi-pattern pairs need it — a
        # vacuous pair is already the stronger finding, and a single pattern is
        # fully isolated by its pair run.
        pattern_verdicts: dict[tuple[int, str], list[PatternVerdict]] = {}
        overlap_notes: list[str] = []
        for verdict in verdicts:
            scope = verdict.override
            if verdict.is_vacuous or len(scope.modules) < 2:
                continue
            probed: list[PatternVerdict] = []
            for pattern in scope.modules:
                if args.verbose:
                    print(
                        f"{Colors.DIM}  probing [{verdict.code}] for {pattern} "
                        f"({_scope_name(scope)}){Colors.RESET}"
                    )
                write_probe_config(text, pattern, verdict.code, TEMP_CONFIG)
                errors = parse_errors(run_mypy(TEMP_CONFIG))
                new = sorted(
                    (e for e in errors - baseline_errors if e.code == verdict.code),
                    key=lambda e: (e.path, int(e.line)),
                )
                probed.append(
                    PatternVerdict(
                        override=scope, code=verdict.code, pattern=pattern, new_errors=new
                    )
                )
            note = reconcile_pattern_counts(verdict, probed)
            if note:
                overlap_notes.append(f"[{verdict.code}] {_scope_name(scope)}: {note}")
            pattern_verdicts[(scope.index, verdict.code)] = probed

        census: dict[str, int] = {}
        if args.census:
            if args.verbose:
                print(f"{Colors.DIM}  aggregate: every code stripped at once{Colors.RESET}")
            write_stripped_config(
                text, {s.index: set(s.codes) for s in scopes if s.codes}, TEMP_CONFIG
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
            _print_error_files(verdict)
            probed = pattern_verdicts.get((verdict.override.index, verdict.code), [])
            if probed:
                _print_pattern_counts(probed)
            _print_error_samples(verdict)
        print(
            f"{Colors.YELLOW}Multi-pattern scopes are verified per pattern "
            f"(probe-measured, Codex #883 r5 closed); a pattern earning 0 for its "
            f"scope's code is reported below as a finding.{Colors.RESET}\n"
        )

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

    unearned = [p for probed in pattern_verdicts.values() for p in probed if p.is_unearned]
    if unearned:
        print(
            f"{Colors.RED}{Colors.BOLD}Vacuous pattern membership — "
            f"{len(unearned)} pattern(s) earning 0 for their scope's code:{Colors.RESET}"
        )
        print(
            f"{Colors.YELLOW}The scope earns its code through OTHER patterns; this "
            f"membership only stands to eat the pattern's first violation. Split the "
            f"pattern out of the block or delete it.{Colors.RESET}\n"
        )
        for p in unearned:
            print(
                f"  {Colors.RED}●{Colors.RESET} {Colors.BOLD}{p.code}{Colors.RESET} "
                f"earns 0 for {Colors.BOLD}{p.pattern}{Colors.RESET}"
            )
            print(f"      {_describe(p.override)}")
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
            owners = [s for s in scopes if pattern in s.modules]
            location = _describe(owners[0]) if owners else "pyproject.toml"
            print(f"  {Colors.RED}●{Colors.RESET} {Colors.BOLD}{pattern}{Colors.RESET}")
            print(f"      {Colors.DIM}{location}{Colors.RESET}")
        print()

    if args.census:
        _print_census(census)
        print()

    for note in overlap_notes:
        print(f"{Colors.YELLOW}note: {note}{Colors.RESET}")

    findings = len(vacuous) + len(unearned) + len(unused_sections)
    if findings:
        print(
            f"{Colors.RED}Total: {len(vacuous)} vacuous entries, "
            f"{len(unearned)} vacuous pattern memberships, "
            f"{len(unused_sections)} unused sections{Colors.RESET}"
        )
        return 1

    probed_count = sum(len(v) for v in pattern_verdicts.values())
    print(
        f"{Colors.GREEN}✓ No dead mypy suppressions "
        f"({len(load_bearing)} entries verified load-bearing, "
        f"{probed_count} pattern memberships probed){Colors.RESET}"
    )
    return 0


def run_cli() -> int:
    """
    Translate every outcome into the audit's exit-code contract:

        0 — clean
        1 — CONFIRMED findings, and nothing else
        2 — the instrument could not measure, for any reason

    Exit 1 has to mean findings exclusively, because the scheduled workflow opens
    an issue on it asserting that dead suppressions were found. Python's default
    status for an uncaught exception is ALSO 1, so a malformed pyproject.toml
    (`TOMLDecodeError`), an unreadable file, or any parser bug would have filed
    that issue while nothing had been measured (Codex #883 r3). Catching only
    `AuditError` was not enough: it covers the failures this script anticipated,
    and the whole lesson of this PR is that those are not the dangerous ones.
    """
    try:
        return main()
    except AuditError as exc:
        print(f"{Colors.RED}Audit aborted: {exc}{Colors.RESET}", file=sys.stderr)
        return 2
    # safety-net: an unexpected failure is a non-measurement, never a finding.
    except Exception as exc:
        print(
            f"{Colors.RED}Audit aborted — unexpected {type(exc).__name__}: {exc}{Colors.RESET}",
            file=sys.stderr,
        )
        traceback.print_exc(file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(run_cli())
