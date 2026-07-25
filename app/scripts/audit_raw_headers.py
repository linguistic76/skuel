#!/usr/bin/env python3
"""
Raw Header Audit
================

Advisory scan for two classes of UI anti-pattern:

1. **Raw H1 / H2 as page structure** — ``H1(`` or ``H2(`` outside the files
   that are permitted to construct page-level headings or full HTML documents.
   Flagged files should migrate to ``PageHeader()`` or ``SectionHeader()``
   from ``ui/patterns/``.

2. **Custom full-document construction** — ``Html(Head(`` outside
   ``ui/layouts/base_page.py``. All pages must flow through ``BasePage()`` or
   ``AuthPage()``; hand-built ``Html/Head/Body`` bypasses the PWA shell,
   ARIA regions, and shared vendor includes.

**Advisory, not blocking.** This script exits 0 even when violations are
found so CI is not blocked by intentional exceptions. Violations are printed
as a completion backlog; mark deliberate exceptions in the ``ALLOWED_*``
sets below rather than suppressing the whole check.

Usage:
    uv run python scripts/audit_raw_headers.py           # advisory report
    uv run python scripts/audit_raw_headers.py --strict  # exit 1 on any finding

Exit codes: 0 = always (advisory), 1 = only with --strict and findings present.
"""

import argparse
import ast
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Approved files — H1/H2 allowed (intentional styling, branding, or layout)
# ---------------------------------------------------------------------------

# Files allowed to use raw H1() — either branded pages, intentional custom
# sizing, or component-internal sub-headings that cannot use PageHeader.
ALLOWED_H1: frozenset[str] = frozenset(
    [
        "ui/patterns/page_header.py",  # defines PageHeader itself
        "ui/patterns/section_header.py",  # defines SectionHeader itself
        "ui/system/landing.py",  # hero H1 — intentionally branded (5xl)
        "ui/auth/components.py",  # "SKUEL" brand mark — intentionally styled
        "adapters/inbound/auth_api.py",  # admin debug pages — not user-facing
        "ui/today/page.py",  # 44px planning board headline — intentionally
        # larger than PageHeader for dense layout
        "ui/explore/ps_detail.py",  # 30px extrabold PS hero — intentional detail-page
        # typography (not a standard page header)
    ]
)

# Files allowed to use raw H2() — typically component-internal sub-headings
# where SectionHeader's mb-6 / text-xl would be wrong (e.g. drawer titles,
# ribbon labels, empty-state messages, HTMX fragment card sub-titles).
ALLOWED_H2: frozenset[str] = frozenset(
    [
        "ui/patterns/section_header.py",  # defines SectionHeader itself
        "ui/system/landing.py",  # hero — intentionally branded
        "ui/auth/components.py",  # branded auth flows
        "ui/today/page.py",  # dense planning board: 22px empty-state,
        # 15px ribbon label, 22px drawer title —
        # all intentionally custom (not section nav)
        "ui/explore/ps_detail.py",  # "The idea" / "Tasks from this step" —
        # styled as section_label (text-xs uppercase),
        # not SectionHeader; serves ARIA aria-labelledby
        "adapters/inbound/auth_api.py",
        "ui/calendar/components.py",  # modal dialog title — semantic H2 required
        # for ARIA aria-labelledby on AlpineModal;
        # SectionHeader adds page-level margin/sizing
        "ui/explore/reading_plan.py",  # responsive hero (clamp 24–30px) — intentionally
        # custom sizing for reading plan hero section
    ]
)

# Files allowed to build full Html(Head(...), Body(...)) documents.
ALLOWED_HTML_DOCUMENT: frozenset[str] = frozenset(
    [
        "ui/layouts/base_page.py",  # BasePage and AuthPage — the only two entry points
    ]
)


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _contains_h1_or_h2(source: str) -> tuple[list[int], list[int]]:
    """Return (h1_lines, h2_lines) where H1()/H2() are called."""
    h1_lines: list[int] = []
    h2_lines: list[int] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return h1_lines, h2_lines

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = None
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        if name == "H1":
            h1_lines.append(node.lineno)
        elif name == "H2":
            h2_lines.append(node.lineno)
    return h1_lines, h2_lines


def _contains_html_head_document(source: str) -> list[int]:
    """Return lines where Html(Head(...)) full-document construction occurs."""
    lines: list[int] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return lines

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = None
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        if name != "Html":
            continue
        # Check first positional arg is a Head() call
        if node.args and isinstance(node.args[0], ast.Call):
            first_func = node.args[0].func
            first_name = None
            if isinstance(first_func, ast.Name):
                first_name = first_func.id
            elif isinstance(first_func, ast.Attribute):
                first_name = first_func.attr
            if first_name == "Head":
                lines.append(node.lineno)
    return lines


def audit(root: Path, strict: bool) -> int:
    h1_findings: list[tuple[str, list[int]]] = []
    h2_findings: list[tuple[str, list[int]]] = []
    html_findings: list[tuple[str, list[int]]] = []

    for path in sorted(root.rglob("*.py")):
        rel = _relative(path, root)
        if any(
            seg in rel for seg in ("__pycache__", ".venv", "scripts/", "tests/", "node_modules")
        ):
            continue

        source = path.read_text(encoding="utf-8", errors="replace")

        # Only scan files that import H1/H2/Html to keep it fast
        if "H1" not in source and "H2" not in source and "Html" not in source:
            continue

        h1_lines, h2_lines = _contains_h1_or_h2(source)
        html_lines = _contains_html_head_document(source)

        if h1_lines and rel not in ALLOWED_H1:
            h1_findings.append((rel, h1_lines))
        if h2_lines and rel not in ALLOWED_H2:
            h2_findings.append((rel, h2_lines))
        if html_lines and rel not in ALLOWED_HTML_DOCUMENT:
            html_findings.append((rel, html_lines))

    total = len(h1_findings) + len(h2_findings) + len(html_findings)

    if html_findings:
        print("\n🔴 Custom Html(Head(...)) documents outside base_page.py:")
        for rel, lines in html_findings:
            print(f"  {rel}: lines {lines}")
        print("  → Migrate to BasePage(PageType.CUSTOM) or AuthPage()")

    if h1_findings:
        print("\n⚠️  Raw H1() outside approved files (migrate to PageHeader):")
        for rel, lines in h1_findings:
            print(f"  {rel}: lines {lines}")

    if h2_findings:
        print("\n⚠️  Raw H2() outside approved files (migrate to SectionHeader):")
        for rel, lines in h2_findings:
            print(f"  {rel}: lines {lines}")

    if total == 0:
        print("✅ Raw headers audit: no violations found")
        return 0

    print(f"\n  {total} file(s) with raw heading usage.")
    print(
        "  This is advisory — add intentional exceptions to ALLOWED_H1/ALLOWED_H2 in\n"
        "  scripts/audit_raw_headers.py with a comment explaining the deliberate choice.\n"
        "  Html(Head()) violations are errors: migrate to BasePage/AuthPage."
    )

    # Html(Head()) is never advisory — always an error
    if html_findings or (strict and total > 0):
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit raw H1/H2/Html(Head) usage in UI code")
    parser.add_argument(
        "--strict", action="store_true", help="Exit 1 on any finding (default: advisory/exit 0)"
    )
    args = parser.parse_args()

    root = Path(__file__).parent.parent
    sys.exit(audit(root, strict=args.strict))


if __name__ == "__main__":
    main()
