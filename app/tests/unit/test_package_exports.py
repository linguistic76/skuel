"""Repo-wide guard: every name a package advertises in ``__all__`` must resolve.

WHY THIS EXISTS — AND WHY NO STATIC CHECK CATCHES IT
----------------------------------------------------
``__all__`` is a *promise* about a package's public surface, and in this repo most
of the names in it arrive by re-export: ``__init__.py`` does ``from .submodule
import Name`` and then lists ``Name``. That makes the promise able to outlive its
implementation — delete the submodule and the entry in ``__all__`` still reads
perfectly fine to every static tool, while ``from package import Name`` raises
ImportError.

That is not hypothetical. The ``query_builders/`` decommission (PR #1081,
2026-08-17) deleted ``adapters/persistence/neo4j/query/_query_models.py``, which
had been re-exporting ``QueryIntent``. Ruff, mypy, pyright and the whole unit
suite stayed green — nothing *currently* imports ``QueryIntent`` from that path,
so no static analyser had a reason to look — yet
``from adapters.persistence.neo4j.query import QueryIntent`` was broken. Static
analysis cannot see this class: the breakage is a *runtime* attribute lookup on a
module whose contents are assembled at import time, and the only surviving
reference to the dead name is the ``__all__`` list itself. The single cheap way to
check the promise is to import the package and look.

So that is the guard: import every package that declares ``__all__``, and check
each advertised name against the live module. It replaces
``test_query_package_exports.py``, which asserted this for exactly one of the 122
packages that declare ``__all__``.

FAIL CLOSED
-----------
A package that cannot be imported is a FAILURE, never a skip. An unimportable
``__init__.py`` breaks ``from package import X`` for every name it advertises —
strictly worse than the drift this guard was written for — so swallowing it would
invert the guard's purpose. There is deliberately no try/except escape hatch and
no exclusion list: all 122 packages import in ~2s with no app context, no
fixtures, and no live Neo4j. If a package ever genuinely needs app context, the
answer is a named, commented exception here (and the review that comes with it),
not a bare except.

Discovery is dynamic — git-tracked ``__init__.py`` files whose AST shows a
module-level ``__all__`` assignment. A hardcoded package list would rot in exactly
the way the ``__all__`` entries this guard checks rot, and would go quietly blind
to every package added after it was written.

SCOPE: ALL git-tracked packages, ``tests/`` included
----------------------------------------------------
Every tracked package is in scope, with no tree filter. Two reasons. First, the
break class is a property of re-export, not of a directory:
``tests/fixtures/__init__.py`` re-exports a dozen fixtures from
``service_factories`` / ``embedding_fixtures`` and would rot identically if one of
those modules were deleted — and it would rot *silently*, because a fixture nobody
currently imports from the package root is exactly the case no test exercises.
Second, an exclusion list is itself the hardcoded-staleness class described above;
filtering to production trees would buy nothing except a list to maintain.

WHAT THIS GUARD DOES NOT CHECK — AND WHY
----------------------------------------
The inverse direction (a public name bound on the module but absent from
``__all__``) is deliberately out of scope. Measured on main @ f2bafea9d: 560 such
names, of which 512 are submodule-binding artifacts — ``from .card_generator
import X`` binds ``card_generator`` itself as a package attribute, which is import
machinery, not an authoring omission. Of the 48 remaining, most are incidentally
re-exported typing imports (``Any``, ``Protocol``, ``ClassVar``). That is a
backlog, not an invariant: a guard nobody can keep green gets suppressed, and a
suppressed guard is worth less than no guard (``feedback_no_suppressions_to_hit_zero``).

Precedent for repo-wide invariant tests: ``test_llm_sdk_boundary.py``,
``test_content_boundary.py``, ``test_untracked_refs.py``.
"""

from __future__ import annotations

import ast
import importlib
import subprocess
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

_APP_ROOT = Path(__file__).resolve().parents[2]

# Liveness canary, NOT an inventory. Discovery is dynamic, so a broken git
# invocation or a wrong working directory would return zero packages and this
# whole guard would pass vacuously — fail-open, the one failure mode a guard
# must not have. The floor only proves discovery ran; it is deliberately well
# below the real count (122 on main @ f2bafea9d) so that adding or merging
# packages never touches it. If a consolidation genuinely drops the repo below
# this, lower it on purpose.
_MIN_DISCOVERED_PACKAGES = 100

# Sentinel for the attribute probe in _unresolved(). `getattr(module, name,
# _MISSING)` is the repo-sanctioned spelling of an existence check — SKUEL011
# forbids `hasattr` and names `getattr` as the replacement (AGENTS.md § Style);
# the rule's test-file exclusion is a lint-scope decision, not a design exemption.
# A sentinel rather than a None default, because a package may legitimately export
# a name that is bound to None.
_MISSING = object()


def _tracked_init_files() -> list[str]:
    """Every git-tracked ``__init__.py``, as app-root-relative posix paths.

    Git-tracked rather than ``rglob``: it keeps the walk out of ``.venv`` and
    ``node_modules``, ignores untracked scratch, and makes "what this guard
    covers" identical to "what this repo ships". ``check=True`` — if git cannot
    answer, the guard errors rather than reporting an empty, reassuring list.
    """
    completed = subprocess.run(
        ["git", "-C", str(_APP_ROOT), "ls-files", "--", "*__init__.py"],
        capture_output=True,
        text=True,
        check=True,
    )
    return sorted(completed.stdout.split())


def _declares_all(path: Path) -> bool:
    """True if the file assigns ``__all__`` at module level.

    AST rather than a text match: ``__all__`` named in a docstring, a comment, or
    a nested function is not a declaration. A package that declares no ``__all__``
    makes no promise, so there is nothing here to check.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign | ast.AugAssign):
            targets = [node.target]
        if any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
            return True
    return False


def _packages_declaring_all() -> list[str]:
    """Dotted names of every git-tracked package whose ``__init__.py`` declares ``__all__``."""
    return [
        Path(rel).parent.as_posix().replace("/", ".")
        for rel in _tracked_init_files()
        if _declares_all(_APP_ROOT / rel)
    ]


def _unresolved(module: ModuleType, exported: Sequence[str]) -> list[str]:
    """Advertised names the imported module does not actually bind.

    Pure and separately testable — this is the whole invariant, and
    ``test_guard_detects_a_re_export_whose_source_module_vanished`` proves it
    fires on the shape that got past every static check in PR #1081.
    """
    return [name for name in exported if getattr(module, name, _MISSING) is _MISSING]


def test_every_advertised_name_resolves() -> None:
    """The invariant: for every package, each name in ``__all__`` is bound on it."""
    packages = _packages_declaring_all()

    assert len(packages) >= _MIN_DISCOVERED_PACKAGES, (
        f"Package discovery found only {len(packages)} packages declaring __all__ "
        f"(expected at least {_MIN_DISCOVERED_PACKAGES}). Discovery is probably broken — "
        "a guard that silently checks nothing is worse than no guard. Verify "
        "`git ls-files -- '*__init__.py'` runs from the app root before lowering this floor."
    )

    failures: list[str] = []
    for dotted in packages:
        try:
            module = importlib.import_module(dotted)
        except Exception as exc:  # safety-net: an unimportable package IS the failure
            failures.append(
                f"{dotted}: package does not import — {type(exc).__name__}: {exc}. "
                "Every name it advertises is unreachable."
            )
            continue

        exported = getattr(module, "__all__", None)
        if exported is None:
            failures.append(
                f"{dotted}: __init__.py assigns __all__ at module level, but the imported "
                "module does not bind it (conditional or deleted assignment?)."
            )
            continue
        if not isinstance(exported, list | tuple) or not all(isinstance(n, str) for n in exported):
            failures.append(
                f"{dotted}: __all__ must be a list/tuple of str, got "
                f"{type(exported).__name__} — Python's `from package import *` requires it."
            )
            continue

        missing = _unresolved(module, exported)
        if missing:
            failures.append(f"{dotted}: advertises {missing} in __all__ but does not bind them.")

    assert not failures, (
        "Package __all__ promises a public surface the package no longer provides. "
        "`from <package> import <name>` raises ImportError for each name below, and no "
        "static check can see it (see this module's docstring). For each: either re-add the "
        "import to the package's __init__.py, or drop the name from __all__ — whichever "
        "matches what the package still means to export:\n  " + "\n  ".join(failures)
    )


def test_no_package_advertises_a_name_twice() -> None:
    """No ``__all__`` may list the same name twice.

    A duplicate is a merge artifact — the same export claimed under two of the
    semantic group headings these lists are organised by — and it survives every
    other check silently.

    Deliberately NOT paired with a sortedness assertion: ``pyproject.toml``
    disables RUF022 ("__all__ sorting - we use semantic grouping with comments"),
    so grouped-not-sorted is a standing repo decision, and a test asserting sorted
    order here would contradict it.
    """
    duplicated: list[str] = []
    for dotted in _packages_declaring_all():
        try:
            exported = getattr(importlib.import_module(dotted), "__all__", None)
        except Exception:  # safety-net: reported (as a failure) by the resolve test above
            continue  # not a skip — one clear message beats the same break reported twice
        if not isinstance(exported, list | tuple):
            continue  # shape is reported by test_every_advertised_name_resolves
        repeats = sorted(name for name, count in Counter(exported).items() if count > 1)
        if repeats:
            duplicated.append(f"{dotted}: {repeats}")

    assert not duplicated, (
        "Duplicate entries in __all__ — keep one, under the group heading it belongs to:\n  "
        + "\n  ".join(duplicated)
    )


def test_guard_detects_a_re_export_whose_source_module_vanished() -> None:
    """Negative control: reproduce the PR #1081 shape and prove the guard fires.

    A package advertises two names; one arrived by re-export from a module that
    has since been deleted, so the package no longer binds it. Nothing imports the
    dead name today — which is precisely why every static check stayed green.
    """
    module = ModuleType("synthetic_query_package")
    vars(module).update({"UnifiedQueryBuilder": object()})  # the surviving re-export
    advertised = ["UnifiedQueryBuilder", "QueryIntent"]  # QueryIntent's source module is gone

    assert _unresolved(module, advertised) == ["QueryIntent"]

    # Restoring the binding clears it — the guard tracks the module, not the list.
    vars(module).update({"QueryIntent": object()})
    assert _unresolved(module, advertised) == []


def test_discovery_ignores_non_declarations(tmp_path: Path) -> None:
    """``__all__`` in a docstring or nested in a function is not a declaration.

    Discovery has to be AST-precise in both directions: missing a real declaration
    would silently shrink coverage, and matching prose would report a package that
    never made a promise.
    """
    declared = tmp_path / "declared.py"
    declared.write_text('__all__ = ["X"]\n')
    assert _declares_all(declared)

    annotated = tmp_path / "annotated.py"
    annotated.write_text('__all__: list[str] = ["X"]\n')
    assert _declares_all(annotated)

    augmented = tmp_path / "augmented.py"
    augmented.write_text('from .base import __all__\n__all__ += ["X"]\n')
    assert _declares_all(augmented)

    prose = tmp_path / "prose.py"
    prose.write_text('"""This package curates its __all__ by hand."""\nX = 1\n')
    assert not _declares_all(prose)

    nested = tmp_path / "nested.py"
    nested.write_text('def build() -> None:\n    __all__ = ["X"]\n')
    assert not _declares_all(nested)
