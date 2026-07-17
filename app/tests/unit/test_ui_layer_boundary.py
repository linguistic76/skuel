"""
Boundary guard (SoC audit PR C-1): no runtime ``adapters`` imports in ``ui/``.

``ui/`` is pure presentation — it renders what routes hand it. The dependency
arrows point inward: ``adapters/inbound`` (routes) imports ``ui/`` components,
never the reverse at runtime. SKUEL022 enforces the same rule for ``core/``;
no lint rule watches ``ui/``, which is how ``ui/calendar/converters.py`` grew
an ``adapters.calendar_adapters`` import (fixed in #653) and the CSRF render
helpers were consumed from ``adapters/inbound/csrf.py`` (split into
``core/utils/csrf_token_context.py`` + ``ui/patterns/csrf.py``). This guard
fails closed so the boundary cannot silently regress.

Zero exceptions. The last sanctioned sites — BasePage/navbar deriving auth
state from ``adapters.inbound.auth`` session readers — were cleared by the
middleware-set auth context (``core/utils/auth_context.py``, written by
``AuthContextMiddleware``, same shape as ``csrf_token_context``). Auth state
now flows inward like the CSRF token; put new shared values on the same path,
never a ui → adapters import.

Carve-out — mirrors SKUEL022's for ``core/``: imports inside an
``if TYPE_CHECKING:`` body never execute at runtime, so a type-only
``adapters.inbound.fasthtml_types.Request`` annotation is fine (the Request
protocol lives at the FastHTML boundary by design; see CLAUDE.md § FastHTML
boundary).

See: tests/unit/test_llm_sdk_boundary.py (same guard pattern for core/).
"""

from __future__ import annotations

import ast
from pathlib import Path

# Anchor on the imported package, not this file's location — the test must
# keep scanning the real ui/ tree no matter where it lives under tests/.
import ui as _ui_pkg

_UI = Path(next(iter(_ui_pkg.__path__))).resolve()


def _is_type_checking_test(test: ast.expr) -> bool:
    """True for ``TYPE_CHECKING`` / ``typing.TYPE_CHECKING`` guard expressions."""
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    return (
        isinstance(test, ast.Attribute)
        and test.attr == "TYPE_CHECKING"
        and isinstance(test.value, ast.Name)
        and test.value.id == "typing"
    )


def _type_checking_import_lines(tree: ast.AST) -> frozenset[int]:
    """Line numbers of imports in the ``if TYPE_CHECKING:`` *body* only.

    Only ``node.body`` is exempt, never ``node.orelse`` — the ``else`` branch
    of ``if TYPE_CHECKING:`` is the runtime branch.
    """
    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and _is_type_checking_test(node.test):
            for child in node.body:
                for nested in ast.walk(child):
                    if isinstance(nested, ast.Import | ast.ImportFrom):
                        lines.add(nested.lineno)
    return frozenset(lines)


def _runtime_adapters_imports(path: Path) -> list[str]:
    """``file:line -> module`` for every runtime ``adapters`` import in *path*."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    type_only = _type_checking_import_lines(tree)
    rel = str(path.relative_to(_UI.parent))
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            # level > 0 is a relative import inside ui/ — never adapters.
            modules = [node.module]
        else:
            continue
        violations.extend(
            f"{rel}:{node.lineno} -> {module}"
            for module in modules
            if module.split(".")[0] == "adapters" and node.lineno not in type_only
        )
    return violations


def test_ui_has_no_runtime_adapters_imports() -> None:
    """Every ``adapters`` import in ``ui/`` must be TYPE_CHECKING-only.

    A runtime dependency ui → adapters inverts the layering (routes compose UI,
    not the other way around). Fix by moving the shared code inward (core/ or
    ui/) or passing the value in from the route — see #653 for both shapes,
    and core/utils/auth_context.py for the middleware-set context shape.
    """
    violations: list[str] = []
    for py_file in sorted(_UI.rglob("*.py")):
        violations.extend(_runtime_adapters_imports(py_file))

    assert not violations, (
        "Runtime `adapters` import(s) in ui/ — presentation must not depend on "
        "the boundary layer. Move the shared code inward or pass the value in "
        "from the route:\n  " + "\n  ".join(violations)
    )
