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

Carve-out — mirrors SKUEL022's for ``core/``: imports inside an
``if TYPE_CHECKING:`` body never execute at runtime, so a type-only
``adapters.inbound.fasthtml_types.Request`` annotation is fine (the Request
protocol lives at the FastHTML boundary by design; see CLAUDE.md § FastHTML
boundary).

Sanctioned exceptions (``SANCTIONED_RUNTIME_IMPORTS``) — the page-chrome
layer (BasePage / navbar) derives auth state from ``request.session`` via
``adapters.inbound.auth`` readers. Those readers take Starlette Request
objects, so they cannot move inward without putting HTTP types in ``core/``;
the clean fix is a middleware-set auth context (the shape
``core/utils/csrf_token_context.py`` uses for the CSRF token), which would
change the BasePage contract and is deliberately NOT smuggled into a boundary
sweep. Until that design call is made, exactly these sites are sanctioned —
anything new fails closed.

See: tests/unit/test_llm_sdk_boundary.py (same guard pattern for core/).
"""

from __future__ import annotations

import ast
from pathlib import Path

# Anchor on the imported package, not this file's location — the test must
# keep scanning the real ui/ tree no matter where it lives under tests/.
import ui as _ui_pkg

_UI = Path(next(iter(_ui_pkg.__path__))).resolve()

# (relative file, imported module, symbol) triples sanctioned until the
# auth-context design call — see module docstring. Keyed down to the SYMBOL so
# a new name pulled from the same module in the same file still fails closed
# (a bare ``import adapters.x`` would key on symbol == the module name).
SANCTIONED_RUNTIME_IMPORTS = frozenset(
    {
        ("ui/layouts/base_page.py", "adapters.inbound.auth", "get_is_admin"),
        ("ui/layouts/base_page.py", "adapters.inbound.auth", "is_authenticated"),
        ("ui/layouts/navbar.py", "adapters.inbound.auth", "get_current_user"),
        ("ui/layouts/navbar.py", "adapters.inbound.auth", "get_is_admin"),
        ("ui/layouts/navbar.py", "adapters.inbound.auth", "get_is_teacher"),
        ("ui/layouts/navbar.py", "adapters.inbound.auth", "is_authenticated"),
    }
)


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
        # (module, symbol) per imported name — for ``import adapters.x`` the
        # symbol IS the module path, so sanctioning it requires naming it twice.
        if isinstance(node, ast.Import):
            imports = [(a.name, a.name) for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            # level > 0 is a relative import inside ui/ — never adapters.
            imports = [(node.module, a.name) for a in node.names]
        else:
            continue
        for module, symbol in imports:
            if (
                module.split(".")[0] == "adapters"
                and node.lineno not in type_only
                and (rel, module, symbol) not in SANCTIONED_RUNTIME_IMPORTS
            ):
                violations.append(f"{rel}:{node.lineno} -> {module} ({symbol})")
    return violations


def test_ui_has_no_runtime_adapters_imports() -> None:
    """Every ``adapters`` import in ``ui/`` must be TYPE_CHECKING-only.

    A runtime dependency ui → adapters inverts the layering (routes compose UI,
    not the other way around). Fix by moving the shared code inward (core/ or
    ui/) or passing the value in from the route — see #653 for both shapes.
    """
    violations: list[str] = []
    for py_file in sorted(_UI.rglob("*.py")):
        violations.extend(_runtime_adapters_imports(py_file))

    assert not violations, (
        "Runtime `adapters` import(s) in ui/ — presentation must not depend on "
        "the boundary layer. Move the shared code inward or pass the value in "
        "from the route:\n  " + "\n  ".join(violations)
    )
