#!/usr/bin/env python3
"""
Dead Module Detector
====================

Finds Python source files with zero importers in production code.

For every .py file in the project (excluding tests, __init__.py, scripts/):
  - Count imports of it from other production Python files
  - Report files with zero importers as deletion candidates
  - Output: file path, line count, and a hint from the first comment/docstring

Usage:
    uv run python scripts/health/dead_modules.py
    uv run python scripts/health/dead_modules.py --verbose
"""

import re
import sys
from collections import defaultdict
from pathlib import Path

from core.utils.terminal_colors import Colors

ROOT = Path(__file__).parent.parent.parent  # /home/mike/skuel/app

# Directory parts that are never scanned (not even for imports)
NEVER_SCAN_DIR_PARTS = {
    "tests",
    "__pycache__",
    "node_modules",
    ".git",
    "htmlcov",
    ".mypy_cache",
    ".pytest_cache",
    ".claude",
    "notebooks",
    "examples",
    # The project venv lives in-tree at app/.venv (uv's default, and where CI's
    # cache step restores it) — without this, site-packages floods the dead
    # list with thousands of third-party "modules" and buries every real one.
    ".venv",
}

# Directory parts excluded from SUBJECTS (won't appear in dead list)
# but still scanned for imports so their outbound references count.
# scripts/ contains both production bootstrap (scripts/dev/) and utility scripts.
# We don't want to flag scripts as dead, but we DO want to count their imports.
SUBJECT_EXCLUDE_DIR_PARTS = NEVER_SCAN_DIR_PARTS | {"scripts"}

# Files that are valid entry points — run directly, never imported
ENTRY_POINTS = {
    "main.py",
    "services_bootstrap.py",
    "codegen.py",
    # ADR-075 user-side vault agent (agent/skuel_vault_agent.py) — PEP 723
    # uv-runnable on the user's machine; see docs/guides/VAULT_AGENT_GUIDE.md.
    "skuel_vault_agent.py",
    # Interactive credential-store CLI (core/config/credential_setup.py); its
    # CREDENTIALS catalog is mirrored by lint_skuel.py with a drift test.
    "credential_setup.py",
}

# These modules are intentionally standalone (convention-discovered, not imported)
CONVENTION_LOADED = {
    # conftest.py files are discovered by pytest, not imported
    "conftest.py",
    # Passed to vulture as a PATH argument by scripts/detect_bloat.py — data
    # for a tool, never imported (see docs/tools/BLOAT_DETECTION.md).
    "vulture_whitelist.py",
}

# Staged-but-unwired modules — the module-level twin of detect_bloat.py's
# PLANNED tiers ("abandoned ≠ staged"). Every entry names its wiring trigger;
# when the trigger closes, either the module gains an importer (drop the entry)
# or the plan died (delete the module). Root-relative path → reason.
STAGED_MODULES: dict[str, str] = {
    "adapters/outbound/firefly_client.py": (
        "Firefly III client — built + tested, wired in Phase 2 of "
        "docs/roadmap/finance-billing-migration.md (ADR-052 sidecar)"
    ),
    "core/events/exercise_events.py": (
        "ExerciseCreated is registered in detect_bloat.py PLANNED_EVENTS "
        "(campaign 17) — the event module rides that staging"
    ),
}


def _never_scan(path: Path) -> bool:
    """True if this path should be excluded from ALL processing (subjects + scanning)."""
    rel = path.relative_to(ROOT)
    return any(part in NEVER_SCAN_DIR_PARTS for part in rel.parts)


def _exclude_from_subjects(path: Path) -> bool:
    """True if this path should NOT appear in the dead-module candidate list."""
    rel = path.relative_to(ROOT)
    return any(part in SUBJECT_EXCLUDE_DIR_PARTS for part in rel.parts)


def get_production_py_files() -> tuple[list[Path], list[Path]]:
    """
    Returns:
      subjects   — files to check for dead imports (excludes scripts/, tests/, __init__.py)
      all_sources — files to scan for imports (includes scripts/ so bootstrap counts)
    """
    subjects: list[Path] = []
    all_sources: list[Path] = []
    for path in ROOT.rglob("*.py"):
        if _never_scan(path):
            continue
        all_sources.append(path)
        if path.name != "__init__.py" and not _exclude_from_subjects(path):
            subjects.append(path)
    return sorted(subjects), sorted(all_sources)


def path_to_module(path: Path) -> str:
    """Convert /home/mike/skuel/app/core/services/tasks.py → core.services.tasks"""
    rel = path.relative_to(ROOT)
    parts = list(rel.parts)
    parts[-1] = parts[-1][:-3]  # strip .py
    return ".".join(parts)


def _resolve_relative_import(dots: str, module_suffix: str, source_file: Path) -> str:
    """
    Resolve a relative import to its absolute dotted module path.

    dots:          the leading dots (e.g. "." or "..")
    module_suffix: the part after the dots (e.g. "ls_core_service" or "")
    source_file:   the file containing the import
    """
    rel = source_file.relative_to(ROOT)
    parts = list(rel.parts)

    if source_file.name == "__init__.py":
        # __init__.py IS the package — remove the __init__.py part entirely
        # so parts represents the package directory, not a sub-module
        package_parts = parts[:-1]  # drop "__init__.py"
    else:
        # Regular module — strip .py from filename
        parts[-1] = parts[-1][:-3]
        package_parts = parts[:-1]  # parent directory = package

    # Each additional dot (beyond the first) goes one level further up
    level = len(dots)
    anchor = package_parts[: len(package_parts) - (level - 1)]

    if module_suffix:
        anchor = [*list(anchor), module_suffix]

    return ".".join(anchor)


def _parse_names(raw: str) -> list[str]:
    """Extract identifier names from a comma-separated import list (may contain comments)."""
    names = []
    for token in raw.split(","):
        # Strip inline comments
        if "#" in token:
            token = token[: token.index("#")]
        name = token.split(" as ")[0].strip()
        if name and re.match(r"^[A-Za-z_]\w*$", name):
            names.append(name)
    return names


def _resolve_module(from_module: str, source_file: Path) -> str:
    """Resolve a from-module string (absolute or relative) to its absolute dotted path."""
    rel_match = re.match(r"^(\.+)([\w.]*)", from_module)
    if rel_match:
        return _resolve_relative_import(rel_match.group(1), rel_match.group(2), source_file)
    return from_module


def collect_imports(py_files: list[Path]) -> tuple[set[str], dict[str, set[str]]]:
    """
    Scan all files and collect import references.

    Returns:
        direct_imports: set of module paths from `import X.Y.Z`
        from_imports: dict mapping from-module → set of imported names

    Handles:
      - Single-line:      from core.services.foo import Bar, Baz
      - Multi-line paren: from core.services.foo import (\\n    Bar,\\n)
        (with correct bracket matching — comments with parens handled)
      - Relative:         from .ls_core_service import PsCoreService
    """
    direct_imports: set[str] = set()
    from_imports: dict[str, set[str]] = defaultdict(set)

    for path in py_files:
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        lines = content.splitlines()

        for match in re.finditer(r"^\s*import\s+([\w.]+)", content, re.MULTILINE):
            direct_imports.add(match.group(1))

        # Process from-imports line by line to handle multi-line parens correctly
        i = 0
        while i < len(lines):
            line = lines[i]
            # Match: from X import ...
            m = re.match(r"^\s*from\s+([\w.]+)\s+import\s+(.*)", line)
            if not m:
                i += 1
                continue

            from_module = _resolve_module(m.group(1), path)
            rest = m.group(2).strip()

            if rest.startswith("("):
                # Multi-line: accumulate until closing )
                # Count parens to handle nested ones (e.g. in comments)
                # We strip inline comments from each line before counting
                accumulated = rest[1:]  # skip opening (
                i += 1
                while i < len(lines):
                    cur = lines[i]
                    # Strip inline comment for paren counting only
                    clean = cur.split("#")[0]
                    if ")" in clean:
                        # Take everything up to the first ) in the clean version
                        close_pos = clean.index(")")
                        accumulated += "\n" + cur[:close_pos]
                        break
                    accumulated += "\n" + cur
                    i += 1
                for name in _parse_names(accumulated):
                    from_imports[from_module].add(name)
            else:
                # Single-line (may have trailing comment)
                for name in _parse_names(rest):
                    from_imports[from_module].add(name)

            i += 1

    return direct_imports, from_imports


def module_is_imported(
    module: str,
    direct_imports: set[str],
    from_imports: dict[str, set[str]],
) -> bool:
    """
    Check whether this module is referenced by any import statement.

    Handles three patterns:
      1. `import core.services.tasks_service`
      2. `from core.services.tasks_service import X`
      3. `from core.services import tasks_service`
    """
    # Pattern 1: import core.services.tasks_service
    if module in direct_imports:
        return True

    # Pattern 2: from core.services.tasks_service import X
    if module in from_imports:
        return True

    # Pattern 3: from parent import leaf  (e.g. from core.services import tasks_service)
    if "." in module:
        parent, leaf = module.rsplit(".", 1)
        if leaf in from_imports.get(parent, set()):
            return True

    return False


def count_lines(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8", errors="ignore").splitlines())
    except OSError:
        return 0


def get_hint(path: Path) -> str:
    """Return the first meaningful comment or docstring line."""
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return ""

    for i, line in enumerate(lines[:15]):
        stripped = line.strip()
        if stripped.startswith("#") and len(stripped) > 2:
            return stripped[:100]
        if stripped.startswith(('"""', "'''")):
            # Single-line docstring
            inner = stripped[3:].rstrip("\"' ")
            if inner:
                return inner[:100]
            # Multi-line: peek ahead
            for j in range(i + 1, min(i + 6, len(lines))):
                nxt = lines[j].strip()
                if nxt and nxt not in ('"""', "'''"):
                    return nxt[:100]
                if nxt in ('"""', "'''"):
                    break
    return ""


def _sort_dead_modules_by_size(record: tuple[Path, str, int, str]) -> int:
    """Sort dead module records by descending line count."""
    _, _, lines, _ = record
    return -lines


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Find Python modules with zero importers")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show all modules scanned")
    args = parser.parse_args()

    print(f"{Colors.BOLD}Dead Module Detector{Colors.RESET}")
    print("=" * 60)

    subjects, all_sources = get_production_py_files()
    print(f"Scanning {len(all_sources)} production Python files ({len(subjects)} subjects)...\n")

    # Collect imports from ALL sources (including __init__.py re-exports)
    direct_imports, from_imports = collect_imports(all_sources)

    dead: list[tuple[Path, str, int, str]] = []
    entry_points_found: list[Path] = []
    staged_found: list[tuple[Path, str]] = []
    stale_staged: list[Path] = []

    for path in subjects:
        if path.name in ENTRY_POINTS or path.name in CONVENTION_LOADED:
            entry_points_found.append(path)
            continue

        rel_posix = path.relative_to(ROOT).as_posix()
        if rel_posix in STAGED_MODULES:
            if module_is_imported(path_to_module(path), direct_imports, from_imports):
                stale_staged.append(path)  # suppresses nothing — registry rot
            else:
                staged_found.append((path, STAGED_MODULES[rel_posix]))
            continue

        module = path_to_module(path)
        if not module_is_imported(module, direct_imports, from_imports):
            lines = count_lines(path)
            hint = get_hint(path)
            dead.append((path, module, lines, hint))

    if args.verbose:
        print(f"{Colors.CYAN}Entry points (excluded from analysis):{Colors.RESET}")
        for p in entry_points_found:
            print(f"  {p.relative_to(ROOT)}")
        print()

    if staged_found:
        print(
            f"{Colors.CYAN}Staged modules (registered in STAGED_MODULES, not dead):{Colors.RESET}"
        )
        for p, reason in staged_found:
            print(f"  {p.relative_to(ROOT)} — {reason}")
        print()

    if stale_staged:
        print(
            f"{Colors.YELLOW}STAGED_MODULES entries that now HAVE importers — "
            f"the module went live; remove the registry entry:{Colors.RESET}"
        )
        for p in stale_staged:
            print(f"  {p.relative_to(ROOT)}")
        print()

    if dead:
        print(
            f"{Colors.RED}{Colors.BOLD}Dead Modules — {len(dead)} files with zero importers:{Colors.RESET}"
        )
        print(f"{Colors.YELLOW}These are not imported anywhere in production code.{Colors.RESET}")
        print(
            f"{Colors.YELLOW}Review before deleting — some may be loaded by convention.{Colors.RESET}\n"
        )

        for path, module, lines, hint in sorted(dead, key=_sort_dead_modules_by_size):
            rel = path.relative_to(ROOT)
            print(
                f"  {Colors.RED}●{Colors.RESET} {Colors.BOLD}{rel}{Colors.RESET}  ({lines} lines)"
            )
            print(f"      module: {Colors.CYAN}{module}{Colors.RESET}")
            if hint:
                print(f"      hint:   {hint}")

        print(f"\n{Colors.YELLOW}Total: {len(dead)} files{Colors.RESET}")
        return 1

    if stale_staged:
        return 1
    print(f"{Colors.GREEN}✓ No dead modules found{Colors.RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
