"""
Whole-set reads: the helper's contract, and the census of bare page reads.
==========================================================================

Two halves.

``find_all_by`` / ``warn_if_capped`` — asks for ``QueryLimit.MAXIMUM`` rows, returns
what the backend returned, warns when the page came back full. The cap is patched
small here; the real one is 10 000 rows.

The census — the generic backend's ``find_by``, ``find_by_date_range``,
``get_user_entities`` and ``list_by_user`` return a page of 100 unless the caller
writes a limit. A call that writes none is a page read. The test walks the
first-party trees and holds the set of such calls to ``PAGE_READS``: a new bare call fails until it is either given a limit
(``find_all_by`` for a whole set) or listed here with what bounds it, and an entry
whose call is gone fails until it is removed.

See: core/services/whole_set_read.py
     tests/integration/test_whole_set_reads.py (the same reads over 130 real rows)
"""

import ast
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from core.constants import QueryLimit
from core.services.whole_set_read import find_all_by, warn_if_capped
from core.utils.result_simplified import Errors, Result

APP = Path(__file__).resolve().parents[3]

SMALL_CAP = 3


@pytest.fixture
def small_cap(monkeypatch):
    monkeypatch.setattr(QueryLimit, "MAXIMUM", SMALL_CAP)


def _backend(rows: list[str]) -> Mock:
    backend = Mock()
    backend.find_by = AsyncMock(return_value=Result.ok(rows))
    return backend


class TestFindAllBy:
    async def test_asks_for_the_maximum_and_passes_the_filters(self):
        backend = _backend(["a", "b"])

        result = await find_all_by(backend, Mock(), "Task list", user_uid="u1", status="active")

        backend.find_by.assert_awaited_once_with(
            limit=QueryLimit.MAXIMUM, user_uid="u1", status="active"
        )
        assert result.value == ["a", "b"]

    async def test_a_page_under_the_cap_is_silent(self, small_cap):
        logger = Mock()

        await find_all_by(_backend(["a", "b"]), logger, "Task list", user_uid="u1")

        logger.warning.assert_not_called()

    async def test_a_full_page_is_returned_whole_and_warned_about(self, small_cap):
        logger = Mock()
        rows = ["a", "b", "c"]

        result = await find_all_by(_backend(rows), logger, "Task list", user_uid="u1")

        assert result.value == rows
        logger.warning.assert_called_once()
        _message, reading, cap, scope = logger.warning.call_args.args
        assert (reading, cap, scope) == ("Task list", SMALL_CAP, {"user_uid": "u1"})

    async def test_a_failed_read_is_returned_as_it_failed(self, small_cap):
        backend, logger = Mock(), Mock()
        failure: Result[list[str]] = Result.fail(
            Errors.database(message="boom", operation="find_by")
        )
        backend.find_by = AsyncMock(return_value=failure)

        result = await find_all_by(backend, logger, "Task list", user_uid="u1")

        assert result is failure
        logger.warning.assert_not_called()

    async def test_the_limit_is_not_the_callers_to_set(self):
        with pytest.raises(TypeError):
            await find_all_by(_backend([]), Mock(), "Task list", user_uid="u1", limit=5)


class TestWarnIfCapped:
    def test_warns_at_the_cap(self, small_cap):
        logger = Mock()

        warn_if_capped(logger, "Goal performance analytics", ["a", "b", "c"], user_uid="u1")

        logger.warning.assert_called_once()

    def test_silent_under_the_cap(self, small_cap):
        logger = Mock()

        warn_if_capped(logger, "Goal performance analytics", ["a", "b"], user_uid="u1")

        logger.warning.assert_not_called()


# ============================================================================
# The census of bare page reads
# ============================================================================

SCANNED_TREES = ("core", "adapters", "ui", "services_bootstrap")

# door → index of ``limit`` among its positional parameters
PAGE_DOORS = {"find_by": 0, "find_by_date_range": 4, "get_user_entities": 3, "list_by_user": 1}

# (file, enclosing function, door) → what bounds the read
PAGE_READS: dict[tuple[str, str, str], str] = {
    ("core/auth/graph_auth.py", "sign_up", "find_by"): (
        "UserBackend.find_by, a door of its own with no page; one email"
    ),
    ("core/auth/graph_auth.py", "sign_in", "find_by"): (
        "UserBackend.find_by, a door of its own with no page; one email"
    ),
    ("core/services/events/_scheduling_mixin.py", "check_conflicts", "find_by"): (
        "one user's events on one calendar day"
    ),
}


def _writes_a_limit(call: ast.Call, door: str) -> bool:
    """A ``limit=`` keyword, a positional in limit's slot, or a ``**`` splat that may hold one."""
    if any(keyword.arg in ("limit", None) for keyword in call.keywords):
        return True
    return len(call.args) > PAGE_DOORS[door]


def _enclosing_function(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str:
    """The innermost function holding ``node``, or ``<module>``."""
    while node in parents:
        node = parents[node]
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            return node.name
    return "<module>"


def _bare_page_reads() -> set[tuple[str, str, str]]:
    found: set[tuple[str, str, str]] = set()
    for tree_name in SCANNED_TREES:
        for path in sorted((APP / tree_name).rglob("*.py")):
            module = ast.parse(path.read_text())
            parents = {
                child: parent
                for parent in ast.walk(module)
                for child in ast.iter_child_nodes(parent)
            }
            for node in ast.walk(module):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in PAGE_DOORS
                    and not _writes_a_limit(node, node.func.attr)
                ):
                    found.add(
                        (
                            str(path.relative_to(APP)),
                            _enclosing_function(node, parents),
                            node.func.attr,
                        )
                    )
    return found


class TestBarePageReadCensus:
    def test_every_bare_page_read_is_listed(self):
        unlisted = _bare_page_reads() - set(PAGE_READS)

        assert not unlisted, (
            "These calls take a backend door's default page of 100. Read a whole set "
            "through find_all_by (or write the limit); list a deliberate page read in "
            f"PAGE_READS with what bounds it: {sorted(unlisted)}"
        )

    def test_every_listed_read_exists(self):
        gone = set(PAGE_READS) - _bare_page_reads()

        assert not gone, f"PAGE_READS lists calls that are not bare page reads: {sorted(gone)}"
