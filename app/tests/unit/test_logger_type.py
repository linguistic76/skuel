"""One logger type: what ``get_logger`` returns, where the app's loggers come from, and the two
names that type a SKUEL logger wrongly.

``get_logger`` hands out structlog's filtering bound logger (``setup_logging`` configures
``wrapper_class=structlog.make_filtering_bound_logger(...)``). Its type is
``structlog.typing.FilteringBoundLogger``. Every logger in the trees read here (the app and its
scripts) comes from it: a ``logging.getLogger`` logger skips the structlog processors (no
``request_id``, no ``exception`` field) and prints its ``extra=`` context nowhere. The one
``logging.getLogger`` call in those trees is ``core/utils/logging.py``'s, which sets third-party
namespaces' levels.

Two other names would type-check a SKUEL logger wrongly and are held out of the tree here:

- ``logging.Logger`` refuses the keyword fields of a structured call and admits calls the
  structlog logger lacks.
- ``structlog.BoundLogger`` resolves every log method through ``__getattr__`` to ``Any``, so no
  log call through it is checked.

A ``# type: ignore`` on a logger assignment hides a wrong declaration; the tree holds none.

One gap is structlog's own: ``FilteringBoundLogger`` declares ``err``, which the class
``make_filtering_bound_logger`` builds does not define. The type cannot refuse ``logger.err(...)``,
so the tree is held to never calling it.
"""

from __future__ import annotations

import ast
import logging
import operator
import re
import typing
from pathlib import Path

import structlog
from structlog.typing import FilteringBoundLogger

from core.utils.logging import get_logger

APP = Path(__file__).resolve().parents[2]
TREES = ("core", "adapters", "ui", "services_bootstrap", "scripts")
FILES = ("main.py",)
LOGGING_MODULE = APP / "core" / "utils" / "logging.py"

# Members FilteringBoundLogger declares that the class structlog builds lacks.
STRUCTLOG_WRAPPER_GAPS = frozenset({"err"})

_BOUND_LOGGER = re.compile(r"\bBoundLogger\b")
_STDLIB_LOGGER = re.compile(r"\blogging\.Logger\b")
_BARE_LOGGER = re.compile(r"\bLogger\b")
_LOGGER_NAME = re.compile(r"^_?(event_)?(logger|log)$")


def _imports_stdlib_logger_name(tree: ast.Module) -> bool:
    return any(
        isinstance(node, ast.ImportFrom)
        and node.module == "logging"
        and any(alias.name == "Logger" and alias.asname is None for alias in node.names)
        for node in ast.walk(tree)
    )


def _annotations(tree: ast.Module) -> list[tuple[int, str, str]]:
    """Every (line, target name, annotation text) in the module."""
    found: list[tuple[int, str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign):
            target = node.target
            name = (
                target.attr
                if isinstance(target, ast.Attribute)
                else target.id
                if isinstance(target, ast.Name)
                else ""
            )
            found.append((node.lineno, name, ast.unparse(node.annotation)))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            found.extend(
                (arg.lineno, arg.arg, ast.unparse(arg.annotation))
                for arg in [
                    *args.posonlyargs,
                    *args.args,
                    *args.kwonlyargs,
                    args.vararg,
                    args.kwarg,
                ]
                if arg is not None and arg.annotation is not None
            )
            if node.returns is not None:
                found.append((node.lineno, f"{node.name}()", ast.unparse(node.returns)))
    return sorted(found, key=operator.itemgetter(0))


def false_logger_annotations(source: str, rel_path: str) -> list[str]:
    """Annotations naming ``structlog.BoundLogger`` or a stdlib ``Logger``."""
    tree = ast.parse(source)
    bare_is_stdlib = _imports_stdlib_logger_name(tree)
    hits: list[str] = []
    for line, name, text in _annotations(tree):
        stdlib = _STDLIB_LOGGER.search(text) or (bare_is_stdlib and _BARE_LOGGER.search(text))
        if _BOUND_LOGGER.search(text) or stdlib:
            hits.append(f"{rel_path}:{line} {name}: {text}")
    return hits


def stdlib_logger_calls(source: str, rel_path: str) -> list[str]:
    """Calls of ``logging.getLogger`` or of a ``getLogger`` imported from ``logging``."""
    tree = ast.parse(source)
    imported = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "logging"
        for alias in node.names
        if alias.name == "getLogger"
    }
    calls: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "getLogger"
            and isinstance(func.value, ast.Name)
            and func.value.id == "logging"
        ) or (isinstance(func, ast.Name) and func.id in imported):
            calls.append((node.lineno, ast.unparse(node)))
    return [f"{rel_path}:{line} {text}" for line, text in sorted(calls)]


def ignored_logger_assignments(source: str, rel_path: str) -> list[str]:
    """Assignments to a logger name whose lines carry a ``# type: ignore``."""
    lines = source.splitlines()
    hits: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
        else:
            continue
        names = [
            t.attr if isinstance(t, ast.Attribute) else t.id if isinstance(t, ast.Name) else ""
            for t in targets
        ]
        if not any(_LOGGER_NAME.match(n) for n in names):
            continue
        span = lines[node.lineno - 1 : (node.end_lineno or node.lineno)]
        if any("type: ignore" in physical for physical in span):
            hits.append(f"{rel_path}:{node.lineno} {lines[node.lineno - 1].strip()}")
    return hits


def logger_err_calls(source: str, rel_path: str) -> list[str]:
    """Calls of ``.err(...)`` on a logger-named receiver."""
    hits: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "err"
        ):
            receiver = node.func.value
            name = (
                receiver.attr
                if isinstance(receiver, ast.Attribute)
                else receiver.id
                if isinstance(receiver, ast.Name)
                else ""
            )
            if _LOGGER_NAME.match(name):
                hits.append(f"{rel_path}:{node.lineno}")
    return hits


def _first_party_sources() -> list[tuple[str, str]]:
    paths = [
        *(path for tree in TREES for path in sorted((APP / tree).rglob("*.py"))),
        *(APP / name for name in FILES),
    ]
    return [(path.relative_to(APP).as_posix(), path.read_text(encoding="utf-8")) for path in paths]


# --------------------------------------------------------------------------- the producer


def test_get_logger_returns_filtering_bound_logger() -> None:
    assert typing.get_type_hints(get_logger)["return"] is FilteringBoundLogger


def test_setup_logging_configures_the_filtering_wrapper() -> None:
    """The type names the class ``setup_logging`` installs — read from its configure call."""
    tree = ast.parse(LOGGING_MODULE.read_text(encoding="utf-8"))
    wrappers = [
        ast.unparse(keyword.value.func)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "structlog.configure"
        for keyword in node.keywords
        if keyword.arg == "wrapper_class" and isinstance(keyword.value, ast.Call)
    ]
    assert wrappers == ["structlog.make_filtering_bound_logger"]


def test_the_wrapper_defines_every_member_the_type_declares_but_err() -> None:
    """Probe the real class against the protocol: it lacks no declared member but structlog's ``err``."""
    wrapper = structlog.make_filtering_bound_logger(logging.INFO)
    bound = structlog.wrap_logger(
        logging.getLogger("skuel.tests.logger_type"), processors=[], wrapper_class=wrapper
    ).bind()
    assert type(bound) is wrapper
    missing = {
        member
        for member in typing.get_protocol_members(FilteringBoundLogger)
        if getattr(bound, member, None) is None
    }
    assert missing <= STRUCTLOG_WRAPPER_GAPS, missing


# --------------------------------------------------------------------------- the tree


def test_no_annotation_names_a_false_logger_type() -> None:
    hits = [
        hit for rel, src in _first_party_sources() for hit in false_logger_annotations(src, rel)
    ]
    assert hits == []


def test_no_logger_assignment_carries_a_type_ignore() -> None:
    hits = [
        hit for rel, src in _first_party_sources() for hit in ignored_logger_assignments(src, rel)
    ]
    assert hits == []


def test_no_logger_is_called_through_err() -> None:
    hits = [hit for rel, src in _first_party_sources() for hit in logger_err_calls(src, rel)]
    assert hits == []


def test_every_app_logger_comes_from_get_logger() -> None:
    hits = [hit for rel, src in _first_party_sources() for hit in stdlib_logger_calls(src, rel)]
    assert [hit for hit in hits if not hit.startswith("core/utils/logging.py:")] == []


def test_the_logging_module_calls_getlogger_only_for_third_party_levels() -> None:
    """Its one call is the loop over ``COMPONENT_LOGGERS``, the third-party namespaces it quiets."""
    calls = stdlib_logger_calls(LOGGING_MODULE.read_text(encoding="utf-8"), "core/utils/logging.py")
    assert [call.split(" ", 1)[1] for call in calls] == ["logging.getLogger(logger_name)"]


# --------------------------------------------------------------------------- the controls


_FALSE_TYPES = """
import logging
from logging import Logger
import structlog

class Host:
    logger: logging.Logger
    other: Logger

def helper(log: structlog.BoundLogger, event_logger: Logger | None = None) -> None: ...
"""

_TRUE_TYPES = """
from structlog.typing import FilteringBoundLogger
from core.services.whole_set_read import WarningLogger

class Host:
    logger: FilteringBoundLogger

def helper(logger: FilteringBoundLogger | None, w: WarningLogger) -> None: ...
"""


def test_control_false_types_are_flagged() -> None:
    hits = false_logger_annotations(_FALSE_TYPES, "control.py")
    assert [hit.split(" ", 1)[1] for hit in hits] == [
        "logger: logging.Logger",
        "other: Logger",
        "log: structlog.BoundLogger",
        "event_logger: Logger | None",
    ]


def test_control_true_types_pass() -> None:
    assert false_logger_annotations(_TRUE_TYPES, "control.py") == []


def test_control_stdlib_logger_calls_are_flagged() -> None:
    source = (
        "import logging\n"
        "from logging import getLogger as get\n"
        "from core.utils.logging import get_logger\n"
        "a = logging.getLogger(__name__)\n"
        "b = get('x')\n"
        "c = get_logger('skuel.x')\n"
        "d = structlog.getLogger('y')\n"
    )
    assert stdlib_logger_calls(source, "control.py") == [
        "control.py:4 logging.getLogger(__name__)",
        "control.py:5 get('x')",
    ]


def test_control_ignored_logger_assignment_is_flagged() -> None:
    source = (
        "class S:\n"
        "    def __init__(self):\n"
        '        self.logger = get_logger("x")  # type: ignore[assignment]\n'
        '        self.name = get_logger("y")  # type: ignore[assignment]\n'
    )
    assert ignored_logger_assignments(source, "control.py") == [
        'control.py:3 self.logger = get_logger("x")  # type: ignore[assignment]'
    ]


def test_control_err_call_is_flagged() -> None:
    source = "self.logger.err('x')\nlog.err('y')\nresult.err('z')\n"
    assert logger_err_calls(source, "control.py") == ["control.py:1", "control.py:2"]
