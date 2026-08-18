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


def _dead_modules(root: Path) -> set[str]:
    """The module pass: subjects with no importer at all."""
    subjects, all_sources = dm.get_production_py_files()
    direct, froms = dm.collect_imports(all_sources)
    return {
        dm.path_to_module(p)
        for p in subjects
        if not dm.module_is_imported(dm.path_to_module(p), direct, froms)
    }


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

    def test_docstring_only_package_is_skipped(self, fake_tree: Path) -> None:
        """A namespace directory has no code that could be dead."""
        _write(fake_tree / "empty_ns" / "__init__.py", '"""Namespace."""\n')

        assert _orphans(fake_tree) == set()

    def test_package_implemented_entirely_in_its_init_is_checked(self, fake_tree: Path) -> None:
        """
        The case Codex caught on #1087: __init__.py can BE the implementation.

        core/services/templates is 230 lines defining seven service classes with
        no module beside it. Skipping every __init__-only package would make it
        permanently invisible — its two outside imports could vanish and the
        check would stay green.
        """
        _write(
            fake_tree / "impl_pkg" / "__init__.py",
            '"""Real code, no modules."""\n\n\nclass Service:\n    pass\n',
        )

        assert _orphans(fake_tree) == {"impl_pkg"}

    def test_reexport_only_package_is_checked(self, fake_tree: Path) -> None:
        """A facade nothing imports is the shape this pass exists to surface."""
        _write(
            fake_tree / "facade" / "__init__.py", "from other.thing import T\n\n__all__ = ['T']\n"
        )
        _write(fake_tree / "other" / "__init__.py", "")
        _write(fake_tree / "other" / "thing.py", "class T: ...\n")
        _write(fake_tree / "app.py", "from other.thing import T\n")

        assert _orphans(fake_tree) == {"facade"}

    def test_future_import_does_not_make_a_namespace_substantive(self, fake_tree: Path) -> None:
        """`from __future__ import annotations` is boilerplate, not code."""
        _write(
            fake_tree / "ns" / "__init__.py",
            '"""Namespace."""\n\nfrom __future__ import annotations\n',
        )

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

    def test_package_holding_an_entry_point_is_not_flagged(self, fake_tree: Path) -> None:
        """
        The case Codex caught on #1087: an entry point is reached by execution.

        `agent/` passed before this only because tests happen to import
        skuel_vault_agent — delete those tests and a live ADR-075 CLI package
        would have been reported orphaned, failing the weekly janitor.
        """
        _write(fake_tree / "cli" / "__init__.py", "")
        _write(fake_tree / "cli" / "main.py", "def run(): ...\n")

        assert _orphans(fake_tree) == set()

    def test_package_holding_a_convention_loaded_file_is_not_flagged(self, fake_tree: Path) -> None:
        """conftest.py is discovered by pytest, never imported."""
        _write(fake_tree / "fixtures_pkg" / "__init__.py", "")
        _write(fake_tree / "fixtures_pkg" / "conftest.py", "import pytest\n")

        assert _orphans(fake_tree) == set()

    def test_package_holding_a_staged_module_is_not_flagged(
        self, fake_tree: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Staged work is reported in its own section — "abandoned != staged"."""
        monkeypatch.setattr(dm, "STAGED_MODULES", {"outbound/client.py": "wired in Phase 2"})
        _write(fake_tree / "outbound" / "__init__.py", "")
        _write(fake_tree / "outbound" / "client.py", "class Client: ...\n")

        assert _orphans(fake_tree) == set()

    def test_an_ordinary_orphan_is_still_flagged_alongside_them(self, fake_tree: Path) -> None:
        """The exemptions must not swallow the signal the pass exists for."""
        _write(fake_tree / "cli" / "__init__.py", "")
        _write(fake_tree / "cli" / "main.py", "def run(): ...\n")
        _write(fake_tree / "lonely" / "__init__.py", "from lonely.config import CONFIG\n")
        _write(fake_tree / "lonely" / "config.py", "CONFIG = {}\n")

        assert _orphans(fake_tree) == {"lonely"}


class TestImportsComeFromTheAST:
    """
    Imports are parsed, not pattern-matched — prose is not a reference.

    The regex scanner this replaced matched raw text, so a `from x import y`
    inside a USAGE docstring counted as a real import. Worst case, a module's
    OWN docstring example vouched for it: `core/utils/list_context_helpers.py`
    documented `from core.utils.list_context_helpers import get_entities`, and
    that self-reference alone kept it off the dead list for the repo's whole
    history. Three modules hid that way (#1088).
    """

    def test_a_module_cannot_vouch_for_itself_in_its_own_docstring(self, fake_tree: Path) -> None:
        """
        THE bug. All three hidden modules had exactly this shape.

        core/utils/list_context_helpers.py documented
        `from core.utils.list_context_helpers import get_entities` in its own
        USAGE block, and nothing else in the tree referenced it. The regex
        matched that line, so the module was its own importer.
        """
        _write(
            fake_tree / "helpers.py",
            '"""Usage::\n\n    from helpers import go\n"""\n\n\ndef go(): ...\n',
        )

        assert "helpers" in _dead_modules(fake_tree)

    def test_a_docstring_example_elsewhere_is_not_an_import(self, fake_tree: Path) -> None:
        """A USAGE block in another file is prose about a module, not a use of it."""
        _write(fake_tree / "helpers.py", "def go(): ...\n")
        _write(fake_tree / "docs_module.py", '"""See::\n\n    from helpers import go\n"""\n')

        assert "helpers" in _dead_modules(fake_tree)

    def test_a_commented_out_import_is_not_an_import(self, fake_tree: Path) -> None:
        _write(fake_tree / "helpers.py", "def go(): ...\n")
        _write(fake_tree / "app.py", "x = 1  # from helpers import go\n")

        assert "helpers" in _dead_modules(fake_tree)

    def test_a_real_import_still_counts(self, fake_tree: Path) -> None:
        """The negative control for the three above."""
        _write(fake_tree / "helpers.py", "def go(): ...\n")
        _write(fake_tree / "app.py", "from helpers import go\n")

        assert "helpers" not in _dead_modules(fake_tree)

    def test_multiline_and_aliased_imports_are_parsed(self, fake_tree: Path) -> None:
        """What the regex needed bespoke bracket-matching for, the parser gets free."""
        _write(fake_tree / "pkg" / "__init__.py", "")
        _write(fake_tree / "pkg" / "helpers.py", "def go(): ...\ndef stop(): ...\n")
        _write(
            fake_tree / "app.py",
            "from pkg.helpers import (  # noqa\n    go as _go,\n    stop,\n)\n",
        )

        assert _orphans(fake_tree) == set()

    def test_relative_imports_resolve_to_absolute_paths(self, fake_tree: Path) -> None:
        _write(fake_tree / "outer" / "__init__.py", "")
        _write(fake_tree / "outer" / "app.py", "from .inner.thing import T\n")
        _write(fake_tree / "outer" / "inner" / "__init__.py", "")
        _write(fake_tree / "outer" / "inner" / "thing.py", "class T: ...\n")
        _write(fake_tree / "top.py", "import outer.app\n")

        assert _orphans(fake_tree) == set()

    def test_an_unparseable_file_is_recorded_not_silently_skipped(
        self, fake_tree: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Silence would be a false positive: its real imports would look dead."""
        monkeypatch.setattr(dm, "UNPARSEABLE", set())
        broken = fake_tree / "broken.py"
        _write(broken, "def oops(:\n")

        dm.collect_imports([broken])

        assert broken in dm.UNPARSEABLE
