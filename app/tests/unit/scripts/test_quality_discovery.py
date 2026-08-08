"""
Tests for quality_discovery — the shared file-discovery vocabulary
==================================================================

Pins three things:

1. **The ruff overlap is a checked fact.** pyproject's ``[tool.ruff] exclude``
   used to carry a prose comment ("mirrored in scripts/lint_skuel.py
   EXCLUDED_DIR_NAMES"); this file replaces that comment with an assertion.
   Every ruff exclude entry is either in the shared vocabulary or in the
   documented-divergence registry below — a new entry that is neither fails
   here and forces the deliberate call.

2. **Matching semantics.** Whole path SEGMENTS, never substrings — the old
   substring match swallowed every ``*builder*`` file via ``"build"``.
   Root-relative prefixes match at the tree root only.

3. **Both consumers stay wired.** lint_skuel's ``_is_excluded`` and
   audit_raw_headers' scope parameters are exercised against the shared
   vocabulary, so silently forking a private copy shows up as a failure.
"""

import sys
import tomllib
from pathlib import Path

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import audit_raw_headers  # type: ignore[import-not-found]
from lint_skuel import SkuelLinter  # type: ignore[import-not-found]
from quality_discovery import (  # type: ignore[import-not-found]
    EXCLUDED_DIR_NAMES,
    is_excluded,
    iter_python_files,
)

APP_ROOT = Path(__file__).resolve().parents[3]

# ============================================================================
# Ruff exclude ↔ shared vocabulary drift
# ============================================================================

# Ruff exclude entries that are DELIBERATELY not in the shared vocabulary.
# Each divergence has a reason; a new pyproject entry that is neither here
# nor in EXCLUDED_DIR_NAMES fails test_ruff_exclude_overlap_is_pinned.
RUFF_ONLY_EXCLUDES: frozenset[str] = frozenset(
    {
        # Neo4j Docker data dir (permission-denied); never contains repo .py.
        "neo4j-import",
        # Path-form entry for archived docs code; the quality scripts have no
        # docs/-specific carve-out (docs/ holds no production .py).
        "docs/archive",
        # Deliberately divergent per the pyproject comment: ruff's bare name
        # matches at any depth, while lint_skuel excludes only
        # scripts/migrations via EXCLUDED_PATH_PREFIXES.
        "migrations",
        # Glob, not a directory name.
        "*.egg-info",
        # Subsumed by the shared ".claude" segment exclusion.
        ".claude/skills",
    }
)


def _ruff_exclude() -> set[str]:
    with (APP_ROOT / "pyproject.toml").open("rb") as fh:
        config = tomllib.load(fh)
    return set(config["tool"]["ruff"]["exclude"])


def test_ruff_exclude_overlap_is_pinned() -> None:
    """Every ruff exclude entry is shared vocabulary or documented divergence."""
    unaccounted = _ruff_exclude() - RUFF_ONLY_EXCLUDES - EXCLUDED_DIR_NAMES
    assert not unaccounted, (
        f"pyproject [tool.ruff] exclude entries {sorted(unaccounted)} are neither in "
        "quality_discovery.EXCLUDED_DIR_NAMES nor registered as a documented "
        "divergence in RUFF_ONLY_EXCLUDES — decide which, deliberately."
    )


def test_divergence_registry_matches_pyproject() -> None:
    """A divergence entry that ruff no longer excludes is stale — delete it."""
    stale = RUFF_ONLY_EXCLUDES - _ruff_exclude()
    assert not stale, (
        f"RUFF_ONLY_EXCLUDES entries {sorted(stale)} are no longer in pyproject's "
        "ruff exclude list — remove them from the divergence registry."
    )


def test_claude_skills_divergence_is_subsumed() -> None:
    """The '.claude/skills' ruff entry is covered by the shared '.claude'."""
    assert ".claude" in EXCLUDED_DIR_NAMES


# ============================================================================
# Matching semantics
# ============================================================================


def test_dir_names_match_as_segments_at_any_depth() -> None:
    assert is_excluded(Path("node_modules/pkg/index.py"))
    assert is_excluded(Path("ui/build/artifact.py"))
    assert is_excluded(Path("__pycache__/mod.cpython-314.pyc.py"))


def test_dir_names_never_match_as_substrings() -> None:
    # Regression guard: "build" in "query_builder.py" is the historical bug.
    assert not is_excluded(Path("core/services/query_builder.py"))
    assert not is_excluded(Path("adapters/distributions.py"))  # "dist" substring


def test_path_prefixes_match_at_root_only() -> None:
    prefixes = ("scripts/migrations",)
    assert is_excluded(Path("scripts/migrations/m001.py"), path_prefixes=prefixes)
    assert not is_excluded(Path("tests/scripts/migrations/m001.py"), path_prefixes=prefixes)
    assert not is_excluded(Path("scripts/other.py"), path_prefixes=prefixes)


def test_extra_dir_names_extend_without_replacing() -> None:
    extra = frozenset({"tests"})
    assert is_excluded(Path("tests/unit/test_x.py"), extra_dir_names=extra)
    assert is_excluded(Path("node_modules/x.py"), extra_dir_names=extra)  # shared still applies
    assert not is_excluded(Path("core/x.py"), extra_dir_names=extra)


def test_iter_python_files_walks_sorted_and_scoped(tmp_path: Path) -> None:
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "b.py").write_text("")
    (tmp_path / "core" / "a.py").write_text("")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "vendored.py").write_text("")
    (tmp_path / "skipme").mkdir()
    (tmp_path / "skipme" / "x.py").write_text("")
    (tmp_path / "prefixed").mkdir()
    (tmp_path / "prefixed" / "y.py").write_text("")

    found = list(
        iter_python_files(
            tmp_path,
            extra_dir_names=frozenset({"skipme"}),
            path_prefixes=("prefixed",),
        )
    )
    assert found == [tmp_path / "core" / "a.py", tmp_path / "core" / "b.py"]


# ============================================================================
# Consumers stay wired to the shared vocabulary
# ============================================================================


def test_lint_skuel_uses_shared_vocabulary() -> None:
    linter = SkuelLinter(root_dir=APP_ROOT)
    assert linter._is_excluded(APP_ROOT / "node_modules" / "pkg" / "x.py")
    assert linter._is_excluded(APP_ROOT / "scripts" / "migrations" / "m001.py")  # lint prefix
    assert not linter._is_excluded(APP_ROOT / "core" / "services" / "query_builder.py")


def test_audit_raw_headers_scope_is_explicit() -> None:
    """The audit's narrower scope is modelled as parameters, not a fork."""
    assert frozenset({"scripts", "tests"}) == audit_raw_headers.EXTRA_EXCLUDED_DIR_NAMES
    # The extras extend the shared vocabulary rather than replacing it.
    assert not audit_raw_headers.EXTRA_EXCLUDED_DIR_NAMES & EXCLUDED_DIR_NAMES
