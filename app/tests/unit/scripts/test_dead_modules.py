"""Pin the orphan-package pass in ``scripts/health/dead_modules.py``.

Why this file exists
--------------------
``core/services/search`` sat in the tree for the repo's entire history — 357
lines, three files, never imported by anything — and ``./dev health`` reported
exactly one dead file in it. The module pass excludes ``__init__.py`` from its
subjects but still counts it as an *importer*, so a self-contained package
clears itself: its ``__init__`` imports its modules, and every module in it
therefore has an importer. Only ``core_types.py``, the one file that
``__init__`` forgot to re-export, was ever flagged.

The four cases below are the whole contract, and each is load-bearing:

1. **Imported from outside** — the ordinary case, must not be flagged.
2. **Imported only by its own ``__init__``** — the bug above. This is the cell
   the pass exists for.
3. **Only ``__init__.py``** — skipped. An empty namespace directory has no
   module that could be dead; that is a different question with a different
   fix, and conflating them makes the signal noisy (``ui/curriculum`` and
   ``ui/study`` are real examples in this tree).
4. **Imported only by a test** — must NOT be flagged. This is the cell that
   keeps the pass honest: ignoring tests condemns ``agent/`` (an ADR-075 entry
   point) and ``core/models/vectors`` (test-covered), neither of which is dead.
   Deleting on that signal would be the exact failure the bloat scanner's
   known test-reference gap produces.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# scripts/ has no __init__.py — add it to sys.path for import (matches test_dead_doc_links.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "health"))

import dead_modules as dm  # type: ignore[import-not-found]


def _write(path: Path, body: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


@pytest.fixture
def fake_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A miniature project root, with dead_modules pointed at it."""
    monkeypatch.setattr(dm, "ROOT", tmp_path)
    _write(tmp_path / "main.py", "")
    return tmp_path


def _orphans(root: Path) -> set[str]:
    sources = dm.get_import_sources_including_tests()
    refs = dm.collect_references_by_file(sources)
    return {
        pkg.relative_to(root).as_posix()
        for pkg, _files, _lines in dm.find_orphan_packages([], refs)
    }


class TestOrphanPackages:
    def test_package_imported_from_outside_is_not_flagged(self, fake_tree: Path) -> None:
        _write(fake_tree / "pkg" / "__init__.py", "from pkg.thing import Thing\n")
        _write(fake_tree / "pkg" / "thing.py", "class Thing: ...\n")
        _write(fake_tree / "app.py", "from pkg.thing import Thing\n")

        assert _orphans(fake_tree) == set()

    def test_package_imported_only_by_its_own_init_is_flagged(self, fake_tree: Path) -> None:
        """The core/services/search shape: alive from the inside, reachable by nobody."""
        _write(fake_tree / "lonely" / "__init__.py", "from lonely.config import CONFIG\n")
        _write(fake_tree / "lonely" / "config.py", "CONFIG = {}\n")
        _write(fake_tree / "app.py", "x = 1\n")

        assert _orphans(fake_tree) == {"lonely"}

    def test_package_with_only_an_init_is_skipped(self, fake_tree: Path) -> None:
        """An empty namespace directory has no module that could be dead."""
        _write(fake_tree / "empty_ns" / "__init__.py", '"""Namespace."""\n')

        assert _orphans(fake_tree) == set()

    def test_package_imported_only_by_a_test_is_not_flagged(self, fake_tree: Path) -> None:
        """Test-only consumers mean exercised, not abandoned."""
        _write(fake_tree / "tested" / "__init__.py", "from tested.core import run\n")
        _write(fake_tree / "tested" / "core.py", "def run(): ...\n")
        _write(fake_tree / "tests" / "test_it.py", "from tested.core import run\n")

        assert _orphans(fake_tree) == set()

    def test_submodule_import_counts_as_reaching_the_package(self, fake_tree: Path) -> None:
        """`import deep.nested.mod` reaches `deep`, not only `deep.nested.mod`."""
        _write(fake_tree / "deep" / "__init__.py", "")
        _write(fake_tree / "deep" / "nested" / "__init__.py", "")
        _write(fake_tree / "deep" / "nested" / "mod.py", "VALUE = 1\n")
        _write(fake_tree / "app.py", "import deep.nested.mod\n")

        assert _orphans(fake_tree) == set()

    def test_from_parent_import_leaf_counts(self, fake_tree: Path) -> None:
        """`from core import notification` must reach the core.notification package."""
        _write(fake_tree / "core" / "__init__.py", "")
        _write(fake_tree / "core" / "leaf" / "__init__.py", "from core.leaf.thing import T\n")
        _write(fake_tree / "core" / "leaf" / "thing.py", "class T: ...\n")
        _write(fake_tree / "app.py", "from core import leaf\n")

        assert _orphans(fake_tree) == set()
