"""
Boundary guard (W1 / ADR-063, extending ADR-044): core/ third-party import allowlist.

WHY AN ALLOWLIST, NOT A DENYLIST
--------------------------------
The original guard banned three hardcoded SDK names
(``openai`` / ``anthropic`` / ``huggingface_hub``). A denylist fails *open*: a
future ``import stripe`` / ``import requests`` / ``import httpx`` *client* in
``core/services/`` would sail straight through, because it isn't one of the
three names anyone thought to ban. An allowlist fails *closed* — every external
package ``core/`` pulls in must be enumerated below on purpose, so a new vendor
SDK cannot reach ``core/`` without a deliberate edit to this file (and the
review that comes with it).

This complements SKUEL022 (no ``import adapters`` in ``core/``) and the
raw-Cypher guards: SKUEL022 catches first-party *adapter* leaks, this catches
third-party *vendor* leaks. Neither lint rule can see ``import stripe`` — this
guard does.

TWO TIERS
---------
1. ``ALLOWED_THIRD_PARTY`` — pure / edge-tier packages ``core/`` may import
   anywhere: Pydantic at the edges (three-tier type system), YAML + markdown
   for ingestion/rendering, structlog for logging, bcrypt/cryptography/keyring/
   dotenv for credentials, prometheus_client for metrics. None of these carry a
   transport/client concern that belongs below the boundary.

2. ``EXCEPTION_CLASS_ONLY`` — vendor SDK / driver / transport packages whose
   *exception classes* ``core/`` narrow-catches (SKUEL017). The clients live
   below the boundary in ``adapters/external/`` (ADR-063) and
   ``adapters/persistence/`` (ADR-044); only the exception tuples live in
   ``core/`` — and only in ``core/utils/exception_types.py``. Several core
   services narrow-catch ``LLM_EXCEPTIONS`` / ``NEO4J_EXCEPTIONS`` /
   ``FIREFLY_EXCEPTIONS`` and cannot import those tuples from ``adapters/``
   without violating SKUEL022, so the tuples must live in ``core/``. TWO
   guarantees are enforced (not merely documented): (a) *location* — only
   ``exception_types.py`` may import them; and (b) *what* — only their exception
   CLASSES, never a client. A bare ``import openai`` / ``from httpx import
   Client`` in that file is rejected: every symbol imported from a Tier-2
   package must resolve to a ``BaseException`` subclass
   (``test_exception_types_imports_only_exception_classes_from_tier2``).

   ``huggingface_hub`` is deliberately absent from BOTH tiers: it has no
   exception tuple (the HF embeddings adapter uses a broad safety-net catch),
   so ``core/`` imports it nowhere.

Any third-party top-level module in ``core/`` that is in neither tier — or an
``EXCEPTION_CLASS_ONLY`` module imported anywhere but ``exception_types.py`` —
fails this guard. Adding a genuinely-needed dependency means adding it to the
right tier here, on purpose.

See: docs/decisions/ADR-063-llm-embeddings-sdk-ports.md,
     docs/decisions/ADR-044 (hexagonal boundary)
"""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parent.parent
_CORE = _APP_ROOT / "core"

# --- Tier 1: pure / edge-tier packages core/ may import anywhere -------------
ALLOWED_THIRD_PARTY = frozenset(
    {
        "pydantic",  # validation at the edges (three-tier type system)
        "yaml",  # PyYAML — ingestion / frontmatter parsing
        "markdown",  # markdown rendering
        "structlog",  # structured logging
        "bcrypt",  # password hashing (auth)
        "cryptography",  # credential store encryption
        "keyring",  # OS credential store
        "dotenv",  # python-dotenv — .env loading at the config edge
        "prometheus_client",  # metrics instrumentation
    }
)

# --- Tier 2: exception-class-only, confined to exception_types.py ------------
# Vendor SDK / driver / transport packages. The CLIENTS live below the
# boundary; core/ imports only their exception classes, and only here.
EXCEPTION_CLASS_ONLY = frozenset({"openai", "anthropic", "neo4j", "httpx"})
_EXCEPTION_CLASS_FILE = "core/utils/exception_types.py"

# __future__ is not in sys.stdlib_module_names but is always-available stdlib.
_STDLIB = set(sys.stdlib_module_names) | {"__future__"}


def _imported_top_level_modules(tree: ast.AST) -> list[tuple[str, int]]:
    """Top-level module names referenced by ``import x`` / ``from x import ...``.

    Returns ``(top_level_name, lineno)`` pairs. Relative imports (``node.level
    > 0``) are skipped — they resolve to first-party ``core/`` siblings, never
    a vendor package.
    """
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.extend((alias.name.split(".")[0], node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.append((node.module.split(".")[0], node.lineno))
    return out


def _is_first_party(module: str) -> bool:
    """True if ``module`` is a top-level package/module in this repo.

    Detected structurally (a directory or ``{module}.py`` at the app root) so it
    covers namespace packages without ``__init__.py`` (e.g. ``core`` itself).
    """
    return (_APP_ROOT / module).is_dir() or (_APP_ROOT / f"{module}.py").is_file()


def _violations_for(rel: str, tree: ast.AST) -> list[str]:
    """Classify one module's imports against the allowlist. Pure — unit-testable."""
    violations: list[str] = []
    for module, lineno in _imported_top_level_modules(tree):
        if module in _STDLIB or _is_first_party(module):
            continue  # stdlib + first-party are out of this guard's scope
        if module in ALLOWED_THIRD_PARTY:
            continue
        if module in EXCEPTION_CLASS_ONLY:
            if rel != _EXCEPTION_CLASS_FILE:
                violations.append(
                    f"{rel}:{lineno}: imports `{module}` — its CLIENT belongs below the "
                    f"boundary (ADR-063/044); only {_EXCEPTION_CLASS_FILE} may import its "
                    "exception classes"
                )
            continue
        violations.append(
            f"{rel}:{lineno}: imports unlisted third-party package `{module}` — add it to "
            "ALLOWED_THIRD_PARTY (with a reason) only if core/ genuinely needs it, or move "
            "the dependency below the boundary into adapters/"
        )
    return violations


def _third_party_imported_in_core() -> set[str]:
    """Every third-party top-level module actually imported anywhere in core/."""
    found: set[str] = set()
    for py in _CORE.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for module, _ in _imported_top_level_modules(tree):
            if module not in _STDLIB and not _is_first_party(module):
                found.add(module)
    return found


def test_core_third_party_imports_are_allowlisted() -> None:
    """core/ may import only allowlisted third-party packages (fails closed)."""
    violations: list[str] = []
    for py in sorted(_CORE.rglob("*.py")):
        rel = py.relative_to(_APP_ROOT).as_posix()
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        violations.extend(_violations_for(rel, tree))

    assert not violations, (
        "Unlisted third-party imports leaked into core/ (W1 / ADR-063 / ADR-044). "
        "core/ must stay vendor-light and SDK-client-free — keep clients below the "
        "boundary in adapters/ behind a core/ports protocol:\n  " + "\n  ".join(sorted(violations))
    )


def test_allowlist_fails_closed_on_unlisted_and_misplaced_imports() -> None:
    """Prove the guard rejects what a denylist would have missed.

    A future ``import stripe`` / ``import requests`` in a service, or an SDK
    *client* imported outside exception_types.py, must be flagged.
    """
    leaky_service = ast.parse(
        "import stripe\n"
        "import requests\n"
        "from openai import OpenAI\n"  # SDK client outside exception_types.py
        "import pydantic\n"  # allowlisted — must NOT be flagged
        "from core.models import Entity\n"  # first-party — must NOT be flagged
    )
    flagged = {
        v.split("`")[1] for v in _violations_for("core/services/billing_service.py", leaky_service)
    }
    assert flagged == {"stripe", "requests", "openai"}, flagged

    # The same SDK exception-class import IS allowed inside exception_types.py.
    assert _violations_for(_EXCEPTION_CLASS_FILE, ast.parse("from openai import APIError")) == []


def test_exception_class_exemptions_are_still_load_bearing() -> None:
    """Canary: every EXCEPTION_CLASS_ONLY entry is really imported by
    exception_types.py. If one stops being used there, drop it from the set so
    the boundary tightens automatically (One Path Forward — no dead exemptions)."""
    tree = ast.parse((_APP_ROOT / _EXCEPTION_CLASS_FILE).read_text(encoding="utf-8"))
    imported_here = {module for module, _ in _imported_top_level_modules(tree)}
    dead = EXCEPTION_CLASS_ONLY - imported_here
    assert not dead, (
        f"{_EXCEPTION_CLASS_FILE} no longer imports {sorted(dead)} — remove them from "
        "EXCEPTION_CLASS_ONLY so the boundary guard tightens."
    )


def test_exception_types_imports_only_exception_classes_from_tier2() -> None:
    """Enforce — not just document — the Tier-2 invariant inside exception_types.py.

    The location exemption (only this file may import openai/anthropic/neo4j/httpx)
    is necessary but not sufficient: a ``from openai import OpenAI`` / ``from neo4j
    import GraphDatabase`` / ``from httpx import Client`` *here* would still drag a
    CLIENT below the boundary. So require that every Tier-2 symbol imported in this
    file resolves to a ``BaseException`` subclass, and forbid the bare ``import
    <pkg>`` form (it exposes ``<pkg>.Client`` / ``<pkg>.GraphDatabase`` as attributes).
    """
    tree = ast.parse((_APP_ROOT / _EXCEPTION_CLASS_FILE).read_text(encoding="utf-8"))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            offenders.extend(
                f"line {node.lineno}: `import {alias.name}` pulls the whole module (exposes its "
                f"client) — use `from {alias.name} import <ExceptionClass>`"
                for alias in node.names
                if alias.name.split(".")[0] in EXCEPTION_CLASS_ONLY
            )
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            if node.module.split(".")[0] not in EXCEPTION_CLASS_ONLY:
                continue
            try:
                mod = importlib.import_module(node.module)
            except ImportError:
                continue  # package absent → exception tuple degrades to (); nothing to leak
            for alias in node.names:
                obj = getattr(mod, alias.name, None)
                if not (isinstance(obj, type) and issubclass(obj, BaseException)):
                    offenders.append(
                        f"line {node.lineno}: `from {node.module} import {alias.name}` is not a "
                        "BaseException subclass — only exception CLASSES may cross the boundary here"
                    )

    assert not offenders, (
        f"{_EXCEPTION_CLASS_FILE} may import the Tier-2 packages "
        f"({', '.join(sorted(EXCEPTION_CLASS_ONLY))}) for their EXCEPTION CLASSES ONLY — never a "
        "client. Move any client below the boundary into adapters/external/ (ADR-063):\n  "
        + "\n  ".join(offenders)
    )


def test_allowlist_has_no_dead_entries() -> None:
    """Canary: the allowlist documents reality, not aspiration. An ALLOWED_THIRD_PARTY
    entry that core/ imports nowhere is dead — prune it (and shrink the surface)."""
    used = _third_party_imported_in_core()
    dead = ALLOWED_THIRD_PARTY - used
    assert not dead, (
        f"ALLOWED_THIRD_PARTY lists {sorted(dead)} but core/ imports them nowhere. "
        "Prune dead allowlist entries (One Path Forward — no aspirational deps)."
    )
