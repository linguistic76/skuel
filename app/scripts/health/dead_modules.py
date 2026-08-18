#!/usr/bin/env python3
"""
Dead Module Detector
====================

Finds Python source files with zero importers in production code, and packages
with no importer outside themselves.

For every .py file in the project (excluding tests, __init__.py, scripts/):
  - Count imports of it from other production Python files
  - Report files with zero importers as deletion candidates
  - Output: file path, line count, and a hint from the first comment/docstring

Then, for every package (directory with an __init__.py):
  - Report packages nothing outside their own directory tree imports

Why the second pass exists: __init__.py is excluded from the module subjects
above but still counted as an importer, so a self-contained orphan package
looks alive from the inside — its __init__ imports its modules, and that is
enough to clear every module in it. core/services/search survived that way for
the repo's entire history (357 lines, never once imported); only the one file
its own __init__ forgot to re-export was ever flagged. Same shape as #1082's
break class — a promise outliving its implementation — pointed at packages
instead of __all__.

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


def get_import_sources_including_tests() -> list[Path]:
    """
    Every .py file that can legitimately import first-party code — tests included.

    `get_production_py_files` deliberately ignores tests: a module only tests
    import is dead *production* code. That judgement does not carry to whole
    packages, where the same rule would condemn entry points and test-only
    fixtures. See find_orphan_packages for why.
    """
    skip = NEVER_SCAN_DIR_PARTS - {"tests"}
    sources: list[Path] = []
    for path in ROOT.rglob("*.py"):
        if any(part in skip for part in path.relative_to(ROOT).parts):
            continue
        sources.append(path)
    return sorted(sources)


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


def collect_references_by_file(py_files: list[Path]) -> dict[str, set[Path]]:
    """
    Map every referenced dotted module → the files that reference it.

    The module-level pass only needs "is this imported at all"; the package
    pass needs "imported by WHOM", to tell an outside importer from the
    package importing itself. Both `from a.b import c` and `import a.b.c`
    contribute `a.b.c`, so a package is found however its members are reached.
    """
    references: dict[str, set[Path]] = defaultdict(set)

    for path in py_files:
        direct, froms = collect_imports([path])
        for module in direct:
            references[module].add(path)
        for module, names in froms.items():
            references[module].add(path)
            # `from core.models import notification` reaches core.models.notification
            for name in names:
                references[f"{module}.{name}"].add(path)

    return references


def find_orphan_packages(
    all_sources: list[Path], references: dict[str, set[Path]]
) -> list[tuple[Path, int, int]]:
    """
    Packages that nothing outside their own directory tree imports.

    Returns [(package_dir, module_count, line_count)] sorted by size.

    Three deliberate scoping choices, all load-bearing:

    1. Tests COUNT as importers here, unlike the module pass. A package whose
       only consumers are tests is exercised, not abandoned, and flagging it
       produces exactly the false positives the bloat scanner's test-reference
       gap is known for — `core/models/vectors` is test-covered and not dead,
       and would surface if tests were ignored. Deleting on that signal would
       be a mistake.
    2. Packages whose only .py file is `__init__.py` are skipped. There is no
       module in them to be dead — an empty namespace directory is a different
       question (and a different fix) from an orphaned implementation.
    3. Packages holding an ENTRY_POINTS / CONVENTION_LOADED / STAGED_MODULES
       file are skipped, mirroring the module pass. Those are reached by
       execution or registration, never by import, so "nobody imports it" says
       nothing about them — and STAGED_MODULES entries are already reported in
       their own section ("abandoned != staged" holds at package level too).
    """
    packages: list[Path] = []
    for init in ROOT.rglob("__init__.py"):
        if _never_scan(init) or _exclude_from_subjects(init):
            continue
        pkg_dir = init.parent
        if pkg_dir == ROOT:
            continue
        modules = [f for f in pkg_dir.rglob("*.py") if f.name != "__init__.py"]
        if not modules:
            continue  # nothing here can be dead
        # Reached by execution or registration rather than by import. The module
        # pass exempts these files; the package pass must too, or a live CLI
        # package is "orphaned" the moment nothing imports it. agent/ is the
        # live case — it currently escapes only because tests import
        # skuel_vault_agent, not because it is an entry point (Codex, #1087).
        if any(
            f.name in ENTRY_POINTS
            or f.name in CONVENTION_LOADED
            or f.relative_to(ROOT).as_posix() in STAGED_MODULES
            for f in modules
        ):
            continue
        packages.append(pkg_dir)

    orphans: list[tuple[Path, int, int]] = []
    for pkg_dir in sorted(packages):
        pkg_dotted = ".".join(pkg_dir.relative_to(ROOT).parts)
        importers: set[Path] = set()
        for module, files in references.items():
            if module == pkg_dotted or module.startswith(pkg_dotted + "."):
                importers |= files
        # An importer inside the package tree does not make it reachable.
        outside = {f for f in importers if pkg_dir not in f.parents}
        if outside:
            continue
        py_files = list(pkg_dir.rglob("*.py"))
        orphans.append((pkg_dir, len(py_files), sum(count_lines(f) for f in py_files)))

    return sorted(orphans, key=_sort_orphan_packages_by_size)


def _sort_orphan_packages_by_size(record: tuple[Path, int, int]) -> int:
    """Sort orphan-package records by descending line count."""
    _, _, lines = record
    return -lines


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

    # Registry rot the subjects loop cannot see: an entry whose file was DELETED
    # or renamed is never visited above (its path is gone), so it would linger
    # silently — the exact file-removal scenario the registry exists to track.
    # Audit the keys against disk so a vanished staged module fails the check
    # (the deletion twin of the now-imported rot guard). Codex, PR #986.
    vanished_staged = sorted(key for key in STAGED_MODULES if not (ROOT / key).is_file())

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

    if vanished_staged:
        print(
            f"{Colors.YELLOW}STAGED_MODULES entries whose file is GONE (deleted/renamed) — "
            f"remove the stale registry entry:{Colors.RESET}"
        )
        for key in vanished_staged:
            print(f"  {key}")
        print()

    orphan_packages = find_orphan_packages(
        all_sources, collect_references_by_file(get_import_sources_including_tests())
    )

    if orphan_packages:
        print(
            f"{Colors.RED}{Colors.BOLD}Orphan Packages — {len(orphan_packages)} packages "
            f"nothing outside themselves imports:{Colors.RESET}"
        )
        print(
            f"{Colors.YELLOW}Their own __init__.py importing their modules is not "
            f"reachability.{Colors.RESET}\n"
        )
        for pkg, n_files, lines in orphan_packages:
            rel = pkg.relative_to(ROOT)
            print(
                f"  {Colors.RED}●{Colors.RESET} {Colors.BOLD}{rel}/{Colors.RESET}  "
                f"({n_files} files, {lines} lines)"
            )
            print(f"      package: {Colors.CYAN}{'.'.join(rel.parts)}{Colors.RESET}")
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

    if orphan_packages or stale_staged or vanished_staged:
        return 1
    print(f"{Colors.GREEN}✓ No dead modules or orphan packages found{Colors.RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
