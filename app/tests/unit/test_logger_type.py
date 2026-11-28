"""One logger type: what ``get_logger`` returns, and the two names that type a SKUEL logger wrongly.

``get_logger`` hands out structlog's filtering bound logger (``setup_logging`` configures
``wrapper_class=structlog.make_filtering_bound_logger(...)``). Its type is
``structlog.typing.FilteringBoundLogger``. Two other names would type-check a SKUEL logger
wrongly and are held out of the tree here:

- ``logging.Logger`` refuses the keyword fields of a structured call and admits calls the
  structlog logger lacks; it is the true type only for a ``logging.getLogger`` logger.
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
LOGGING_MODULE = APP / "core" / "utils" / "logging.py"

# The one annotation where ``logging.Logger`` is the true type: ZPDService's optional logger,
# whose fallback is ``logging.getLogger`` (a stdlib logger, not one from ``get_logger``).
STDLIB_LOGGER_ANNOTATIONS = frozenset({("core/services/zpd/zpd_service.py", "logger")})

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
    """Annotations naming ``structlog.BoundLogger`` or a stdlib ``Logger`` outside the registry."""
    tree = ast.parse(source)
    bare_is_stdlib = _imports_stdlib_logger_name(tree)
    hits: list[str] = []
    for line, name, text in _annotations(tree):
        stdlib = _STDLIB_LOGGER.search(text) or (bare_is_stdlib and _BARE_LOGGER.search(text))
        if _BOUND_LOGGER.search(text) or (
            stdlib and (rel_path, name) not in STDLIB_LOGGER_ANNOTATIONS
        ):
            hits.append(f"{rel_path}:{line} {name}: {text}")
    return hits


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
    return [
        (path.relative_to(APP).as_posix(), path.read_text(encoding="utf-8"))
        for tree in TREES
        for path in sorted((APP / tree).rglob("*.py"))
    ]


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


def test_the_stdlib_registry_names_live_annotations() -> None:
    """Each registered stdlib annotation still exists and still names ``Logger``."""
    for rel, name in STDLIB_LOGGER_ANNOTATIONS:
        source = (APP / rel).read_text(encoding="utf-8")
        tree = ast.parse(source)
        matches = [
            text
            for _, target, text in _annotations(tree)
            if target == name and _BARE_LOGGER.search(text.replace("FilteringBoundLogger", ""))
        ]
        assert matches, (rel, name)


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


def test_control_registry_admits_only_its_own_site() -> None:
    source = "from logging import Logger\n\ndef f(logger: Logger | None = None) -> None: ...\n"
    assert false_logger_annotations(source, "core/services/zpd/zpd_service.py") == []
    assert false_logger_annotations(source, "core/services/other.py") != []


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
