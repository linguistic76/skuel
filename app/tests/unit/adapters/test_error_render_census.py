"""A door renders an error's ``display_message`` — never its ``message`` or ``str(error)``.

``ErrorContext.message`` is the developer's sentence: for a SYSTEM error it is the raw text
of whatever exception the service met (``with_error_handling`` sets it to ``str(e)``), and
``str(error)`` adds the severity, the code and the server path of the line that built it.
``display_message`` is the factory's ``user_message`` — every ``Errors`` factory sets one,
and for a validation, business or forbidden refusal it IS the message, so an actionable
refusal reads the same either way.

The census reads every module under ``adapters/inbound`` and ``ui`` by syntax tree. An
error is ``X.error``, ``X.expect_error()``, a name bound from either, or a parameter typed
``ErrorContext``. What it refuses: ``.message`` read off an error, ``str(error)`` and an
error interpolated into an f-string. Exempt, because no learner reads them: logger calls,
a ``raise``, and the debug-only technical details of an error banner
(``technical_details=`` or ``render_error_banner``'s second argument).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parents[3]
SCANNED_TREES = ("adapters/inbound", "ui")
_LOG_METHODS = frozenset({"debug", "info", "warning", "error", "exception", "critical", "log"})
_BANNER = "render_error_banner"


def _is_error_expr(node: ast.expr, bound: set[str]) -> bool:
    if isinstance(node, ast.Attribute) and node.attr == "error":
        return True
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "expect_error"
    ):
        return True
    return isinstance(node, ast.Name) and node.id in bound


def _names_error_context(annotation: ast.expr | None) -> bool:
    return annotation is not None and "ErrorContext" in ast.unparse(annotation)


def _bound_error_names(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    bound = {
        arg.arg
        for arg in (*fn.args.posonlyargs, *fn.args.args, *fn.args.kwonlyargs)
        if _names_error_context(arg.annotation)
    }
    for node in ast.walk(fn):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign | ast.NamedExpr):
            targets = [node.target]
        value = getattr(node, "value", None)
        if targets and isinstance(value, ast.expr) and _is_error_expr(value, set()):
            bound.update(t.id for t in targets if isinstance(t, ast.Name))
    return bound


def _is_logger_call(node: ast.AST) -> bool:
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
        return False
    if node.func.attr not in _LOG_METHODS:
        return False
    receiver = node.func.value
    if isinstance(receiver, ast.Name):
        return receiver.id in {"logger", "log"}
    return isinstance(receiver, ast.Attribute) and receiver.attr == "logger"


def _is_exempt(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> bool:
    child, current = node, parents.get(node)
    while current is not None:
        if isinstance(current, ast.Raise) or _is_logger_call(current):
            return True
        if isinstance(current, ast.keyword) and current.arg == "technical_details":
            return True
        if (
            isinstance(current, ast.Call)
            and isinstance(current.func, ast.Name)
            and current.func.id == _BANNER
            and len(current.args) > 1
            and current.args[1] is child
        ):
            return True
        child, current = current, parents.get(current)
    return False


def _hands_out_raw_text(node: ast.expr, bound: set[str]) -> bool:
    """``error.message``, ``f"{error}"`` or ``str(error)``."""
    if isinstance(node, ast.Attribute):
        return node.attr == "message" and _is_error_expr(node.value, bound)
    if isinstance(node, ast.FormattedValue):
        return _is_error_expr(node.value, bound)
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "str"
        and bool(node.args)
        and _is_error_expr(node.args[0], bound)
    )


def raw_error_renders(source: str, label: str) -> list[str]:
    """Every place ``source`` hands an error's raw text to a reader, as ``label:line: code``."""
    tree = ast.parse(source)
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    found: set[tuple[int, str]] = set()
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        bound = _bound_error_names(fn)
        for node in ast.walk(fn):
            if (
                isinstance(node, ast.expr)
                and _hands_out_raw_text(node, bound)
                and not _is_exempt(node, parents)
            ):
                found.add((node.lineno, ast.unparse(node)))
    return [f"{label}:{line}: {code}" for line, code in sorted(found)]


def _tree_renders() -> list[str]:
    renders: list[str] = []
    for tree in SCANNED_TREES:
        for path in sorted((APP_ROOT / tree).rglob("*.py")):
            label = str(path.relative_to(APP_ROOT))
            renders.extend(raw_error_renders(path.read_text(encoding="utf-8"), label))
    return renders


def test_no_door_renders_an_errors_raw_text() -> None:
    renders = _tree_renders()
    assert renders == [], (
        "a door renders an error's raw text — use `error.display_message`:\n" + "\n".join(renders)
    )


@pytest.mark.parametrize(
    "body",
    [
        "    return P(result.error.message)",
        "    return P(result.expect_error().message)",
        "    error = result.expect_error()\n    return P(error.message)",
        "    if (error := result.error):\n        return P(error.message)",
        "    return P(str(result.error))",
        '    return P(f"Failed: {result.error}")',
        "    error = result.expect_error()\n    return Div(str(error))",
        "    return render_error_banner(result.expect_error().message)",
    ],
)
def test_census_finds_each_raw_shape(body: str) -> None:
    source = f"def door(result):\n{body}\n"
    assert raw_error_renders(source, "door.py"), body


def test_census_finds_a_parameter_typed_error_context() -> None:
    source = "def banner(error: ErrorContext) -> FT:\n    return P(error.message)\n"
    assert raw_error_renders(source, "banner.py")


@pytest.mark.parametrize(
    "body",
    [
        "    return P(result.expect_error().display_message)",
        '    logger.error(f"failed: {result.error}")',
        "    self.logger.warning(result.expect_error().message)",
        '    raise RuntimeError(f"{result.expect_error().message}")',
        '    return render_error_banner("Could not load", str(result.error))',
        '    return render_error_banner("x", technical_details=result.expect_error().message)',
        "    return P(report.message)",
    ],
)
def test_census_passes_what_no_learner_reads(body: str) -> None:
    source = f"def door(result, report):\n{body}\n"
    assert raw_error_renders(source, "door.py") == [], body
