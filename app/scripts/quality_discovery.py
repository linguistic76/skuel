#!/usr/bin/env python3
"""
Quality-Tooling File Discovery — shared by lint_skuel.py and audit_raw_headers.py
=================================================================================

Single source for the exclusion vocabulary the repo-walking quality scripts
use to decide which ``.py`` files are subjects. Before this module existed,
``lint_skuel.py`` carried a 15-name segment-matched set while
``audit_raw_headers.py`` hardcoded a different 5-entry substring skip list —
two vocabularies, no drift check. Following the ``cypher_vocabulary.py``
precedent: one owner, consumers import it, dependency-light (stdlib only).

**Matching semantics — whole path SEGMENTS, never substrings.** The old
substring match in lint_skuel swallowed real modules ("build" in
"query_builder.py" silently unlinted every *builder* file, 19 files total).
``is_excluded`` therefore compares against ``Path.parts``; root-relative
prefixes (a caller-specific concern, e.g. lint_skuel's
``scripts/migrations``) are matched only at the tree root.

**Scope stays per-consumer.** Callers with a deliberately narrower scope
(audit_raw_headers skips ``tests/`` and ``scripts/`` because it audits
production UI code) pass those as ``extra_dir_names`` — the shared set is
the vocabulary, not a mandate that every scanner see the same tree.

The overlap with ``[tool.ruff] exclude`` in pyproject.toml is a checked
fact, not a comment: ``tests/unit/scripts/test_quality_discovery.py`` pins
the shared entries and the documented divergences against pyproject (read
with tomllib).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

# Directory names excluded wherever they appear in the path — build/cache
# artifacts, vendored trees, and local archives that must never be lint or
# audit subjects. Overlap with pyproject's [tool.ruff] exclude is pinned by
# tests/unit/scripts/test_quality_discovery.py.
EXCLUDED_DIR_NAMES: frozenset[str] = frozenset(
    {
        ".venv",
        "venv",
        "__pycache__",
        ".git",
        "node_modules",
        "dist",
        "build",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "htmlcov",
        "backup_archive",
        "z_archives",
        "zarchives",
        ".claude",  # Claude Code config/skills (documentation only)
        # The gitignored scratch tier (CLAUDE.md § Documentation Architecture) —
        # draft scripts parked there are not lint or audit subjects. The only
        # gate walkers that reach it are this vocabulary's consumers and `mypy .`
        # (excluded in pyproject); ruff honours .gitignore and pyright has an
        # explicit include. Safe as an any-depth name: no tracked directory is
        # named plans.
        "plans",
    }
)


def is_excluded(
    rel_path: Path,
    *,
    extra_dir_names: frozenset[str] = frozenset(),
    path_prefixes: tuple[str, ...] = (),
) -> bool:
    """True if a root-relative path is outside the caller's discovery scope.

    Directory names (shared vocabulary + caller extras) match as whole path
    segments at any depth; ``path_prefixes`` match root-relative POSIX
    prefixes only (e.g. ``"scripts/migrations"`` excludes that one tree, not
    every ``migrations`` directory).
    """
    excluded_names = EXCLUDED_DIR_NAMES | extra_dir_names
    if any(part in excluded_names for part in rel_path.parts):
        return True
    return bool(path_prefixes) and rel_path.as_posix().startswith(path_prefixes)


def walk_python_files(
    root: Path, *, extra_dir_names: frozenset[str] = frozenset()
) -> Iterator[Path]:
    """Yield every ``.py`` under ``root``, never descending into an excluded directory.

    The name half of ``is_excluded`` applied at the directory, not the file: a
    file under ``.venv`` is excluded by its parts whichever way it is reached, so
    pruning the subtree changes nothing about WHICH files come out — only that
    the ~12k vendored ``.py`` files under ``.venv`` and ``node_modules`` are never
    listed, stat'd and rejected one by one. Unsorted; callers order.
    """
    excluded_names = EXCLUDED_DIR_NAMES | extra_dir_names
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in excluded_names]
        for filename in filenames:
            if filename.endswith(".py"):
                yield Path(dirpath, filename)


def iter_python_files(
    root: Path,
    *,
    extra_dir_names: frozenset[str] = frozenset(),
    path_prefixes: tuple[str, ...] = (),
) -> Iterator[Path]:
    """Yield in-scope ``.py`` files under ``root``, sorted for stable output."""
    for py_file in sorted(walk_python_files(root, extra_dir_names=extra_dir_names)):
        rel = py_file.relative_to(root)
        if is_excluded(rel, extra_dir_names=extra_dir_names, path_prefixes=path_prefixes):
            continue
        yield py_file
