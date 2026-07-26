#!/usr/bin/env python3
"""
Cypher scan diagnostics — what the vocabulary scanner admitted but could not read
================================================================================

SKUEL030 and CYP011 exist because Neo4j fails silently: a typo'd label or edge
name matches zero rows forever and reports nothing. Their shared scanner
(``cypher_vocabulary.scan_names``) reproduces that fault one layer down —
every one of ITS failure modes is silent too. An item that does not full-match
is dropped; a pattern body whose parts all fail the name regex yields nothing;
a fragment the gate refuses returns ``[]``. Nothing says "I looked at this and
could not read it".

The cost is measured: #831 took 19 Codex rounds without converging, because the
only way to find a gap was for a reviewer to IMAGINE an input — and ~16 of its
~27 findings were valid Cypher forms with ZERO instances in this tree. This
script replaces imagination with measurement. It runs both rules' REAL code
paths with ``recording_scan_diagnostics`` switched on and reports every span
the scanner dropped.

**This is a diagnostic, not a rule.** It is not wired into ``./dev quality``,
it has no baseline, and it never exits nonzero on findings (only on its own
failure). Most drops are CORRECT — a property-only ``SET n.title = $t`` has no
label to miss, a ``$(labelExpr)`` operand has no static name to check. Reading
the list is the point; promoting any category to a violation class is a
separate, deliberate decision.

Usage::

    uv run python scripts/cypher_scan_diagnostics.py            # summary
    uv run python scripts/cypher_scan_diagnostics.py --verbose  # every span
    uv run python scripts/cypher_scan_diagnostics.py --issue unreadable-pattern-body
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from cypher_linter import CypherLinter  # type: ignore[import-not-found]
from cypher_vocabulary import (  # type: ignore[import-not-found]
    ScanDiagnostic,
    ScanIssue,
    app_root,
    recording_scan_diagnostics,
    scan_names,
)
from lint_skuel import SkuelLinter  # type: ignore[import-not-found]

# One report row: which rule's path found it, in which file, and what it was.
Finding = tuple[str, Path, ScanDiagnostic]

# SKUEL030's scope, verbatim from lint_skuel's `is_persistence` gate.
PERSISTENCE_TREE = "adapters/persistence"

_MAX_SPAN = 120


def _skuel030_findings(root: Path) -> list[Finding]:
    """Run SKUEL030 over `adapters/persistence/**/*.py`, one file at a time.

    Through ``SkuelLinter`` itself rather than a hand-rolled AST walk: the rule's
    docstring-awareness, f-string flattening and suppression handling all decide
    what reaches the scanner, and a re-implementation would measure a scanner
    the rules do not actually run. ``changed_files`` is the linter's own
    per-file entry point, which is what buys per-file attribution.
    """
    findings: list[Finding] = []
    for path in sorted((root / PERSISTENCE_TREE).rglob("*.py")):
        linter = SkuelLinter(root_dir=root, rules_filter=["SKUEL030"], changed_files=[path])
        with recording_scan_diagnostics() as sink:
            linter.lint()
        findings.extend(("SKUEL030", path, diag) for diag in sink)
    return findings


def _cyp011_findings(root: Path) -> tuple[list[Finding], list[Path]]:
    """Run CYP011 over every `.cypher` file in the tree, one at a time.

    Returns the findings plus the migration files CYP011 declines to scan — the
    rule returns before the scanner ever sees them (a rename migration's job is
    to name the vocabulary it is renaming away), so they contribute nothing and
    the caller reports them as a stated gap rather than silently omitting them.
    """
    linter = CypherLinter()
    findings: list[Finding] = []
    skipped: list[Path] = []
    for path in sorted(root.rglob("*.cypher")):
        if "node_modules" in path.parts:
            continue
        if "migrations" in path.parts:
            skipped.append(path)
            continue
        with recording_scan_diagnostics() as sink:
            linter.lint_file(path)
        findings.extend(("CYP011", path, diag) for diag in sink)
    return findings, skipped


def _migration_findings(root: Path, skipped: list[Path]) -> list[Finding]:
    """The same scan over the migration files CYP011 declines to check.

    The rule's scope decision is about which files deserve a VIOLATION; the
    scanner's blind spots are a property of the scanner. Reusing the linter's
    own statement splitter keeps this on the real extraction path — only the
    scope gate is stepped around.
    """
    linter = CypherLinter()
    findings: list[Finding] = []
    for path in skipped:
        with recording_scan_diagnostics() as sink:
            # Private on purpose: it is the linter's OWN splitter, and a
            # hand-written equivalent would measure a scanner the rule does not run.
            for statement, _ in linter._extract_cypher_statements(path.read_text()):
                scan_names(statement, declared_cypher=True)
        findings.extend(("CYP011(migration)", path, diag) for diag in sink)
    return findings


def _span(text: str) -> str:
    """One line of the offending span, clipped."""
    flat = " ".join(text.split())
    return flat if len(flat) <= _MAX_SPAN else flat[: _MAX_SPAN - 1] + "…"


def _report(findings: list[Finding], root: Path, *, verbose: bool) -> None:
    by_rule_issue: Counter[tuple[str, str]] = Counter()
    by_issue: defaultdict[str, list[Finding]] = defaultdict(list)
    for rule, path, diag in findings:
        by_rule_issue[(rule, diag.issue.value)] += 1
        by_issue[diag.issue.value].append((rule, path, diag))

    print("=" * 78)
    print("Cypher scan diagnostics — spans admitted but not parsed")
    print("=" * 78)
    if not findings:
        print("\nNo drops recorded.\n")
        return

    print("\nCounts (rule × issue):")
    for (rule, issue), count in sorted(by_rule_issue.items()):
        print(f"  {rule:<20} {issue:<34} {count}")

    for issue in ScanIssue:
        rows = by_issue.get(issue.value, [])
        if not rows:
            continue
        print(f"\n{'-' * 78}\n{issue.value}  ({len(rows)})\n{'-' * 78}")
        shown = rows if verbose else rows[:20]
        for rule, path, diag in shown:
            rel = path.relative_to(root)
            print(f"  [{rule}] {rel}  (+{diag.line_offset} lines)")
            print(f"      {_span(diag.text)}")
        if len(rows) > len(shown):
            print(f"  … {len(rows) - len(shown)} more (use --verbose)")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--verbose", action="store_true", help="Print every span, not the first 20")
    parser.add_argument(
        "--issue",
        choices=[i.value for i in ScanIssue],
        help="Report only this issue kind",
    )
    args = parser.parse_args()

    root = app_root()
    findings = _skuel030_findings(root)
    cyp_findings, skipped = _cyp011_findings(root)
    findings.extend(cyp_findings)
    findings.extend(_migration_findings(root, skipped))

    if args.issue:
        findings = [f for f in findings if f[2].issue.value == args.issue]

    _report(findings, root, verbose=args.verbose)
    # Never a gate: a drop is not a violation. Only a crash is a failure here.
    return 0


if __name__ == "__main__":
    sys.exit(main())
