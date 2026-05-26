"""
Boundary guard (W1): vendor AI SDK *clients* must not live in core/.

The ``openai`` / ``anthropic`` / ``huggingface_hub`` clients belong below the
hexagonal boundary in ``adapters/external/`` (W1, extending ADR-044). ``core/``
depends only on the ``ChatCompletionPort`` / ``EmbeddingClientOperations``
ports; the composition root injects the concrete adapters.

This locks in W1 the way SKUEL022 locks in "no ``adapters`` imports in
``core/``" — but SKUEL022 cannot catch ``import openai``, so this guard does.

THE ONE SANCTIONED EXCEPTION — ``core/utils/exception_types.py``:
It imports openai/anthropic *exception classes* (behind ``try/except``,
degrading to ``()`` when the SDK is absent) to build the narrow-catch tuples
that SKUEL017 centralizes there. Five core/ services narrow-catch
``LLM_EXCEPTIONS`` and cannot import it from ``adapters/`` (that would violate
SKUEL022), so the tuples must live in core/ — but as exception classes only,
never the client. ``huggingface_hub`` has no such exemption (no HF exception
tuple exists; the HF adapter uses a broad safety-net catch).

See: docs/decisions/ADR-063-llm-embeddings-sdk-ports.md
"""

from __future__ import annotations

import ast
from pathlib import Path

# AI vendor SDKs whose *clients* must stay below the hexagonal boundary.
FORBIDDEN_SDKS = {"openai", "anthropic", "huggingface_hub"}

# openai/anthropic exception-CLASS imports (not the client) are allowed only here.
EXEMPT_FOR_EXCEPTION_CLASSES = {"core/utils/exception_types.py"}

_APP_ROOT = Path(__file__).resolve().parent.parent
_CORE = _APP_ROOT / "core"


def _top_level_imported_modules(tree: ast.AST) -> set[str]:
    """Top-level module names referenced by ``import x`` / ``from x import ...``."""
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
        # Skip relative imports (node.level > 0 has no top-level vendor name).
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module.split(".")[0])
    return modules


def test_no_ai_sdk_client_imports_in_core() -> None:
    violations: list[str] = []
    for py in _CORE.rglob("*.py"):
        rel = py.relative_to(_APP_ROOT).as_posix()
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        imported = _top_level_imported_modules(tree)
        for sdk in FORBIDDEN_SDKS & imported:
            if sdk in {"openai", "anthropic"} and rel in EXEMPT_FOR_EXCEPTION_CLASSES:
                continue  # sanctioned exception-class imports (see module docstring)
            violations.append(f"{rel} imports `{sdk}`")

    assert not violations, (
        "Vendor AI SDK client imports leaked into core/ (W1 / ADR-063). Move the "
        "client below the boundary into adapters/external/ and depend on the "
        "ChatCompletionPort / EmbeddingClientOperations port instead:\n  "
        + "\n  ".join(sorted(violations))
    )


def test_exception_types_exemption_is_still_load_bearing() -> None:
    """Canary: the exemption only exists because exception_types.py really does
    import openai/anthropic. If that ever stops being true, drop the exemption
    so the guard tightens automatically."""
    tree = ast.parse((_CORE / "utils" / "exception_types.py").read_text(encoding="utf-8"))
    imported = _top_level_imported_modules(tree)
    assert {"openai", "anthropic"} & imported, (
        "exception_types.py no longer imports openai/anthropic — remove it from "
        "EXEMPT_FOR_EXCEPTION_CLASSES so the boundary guard tightens."
    )
