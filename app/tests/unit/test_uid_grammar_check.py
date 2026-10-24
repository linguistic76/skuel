"""In-app uid grammar check tests.

``check_uid_grammar`` is the PRODUCTION evaluator of the uid census (production
runs no Prometheus — the ``UidOutsideGrammar`` / ``UidHeldByTwoNodes`` rules
evaluate only in dev): silent on a graph that fits, one ERROR per kind of breach,
every cycle while it holds. The module logger is stubbed, as in
``test_aura_cap_check.py`` — structlog's sink is process-global.
"""

import pytest

from core.infrastructure.monitoring import uid_grammar_check
from core.infrastructure.monitoring.uid_grammar_check import UidBreaches, check_uid_grammar


class RecordingLogger:
    """Captures (level, message) pairs in place of the module structlog logger."""

    def __init__(self) -> None:
        self.records: list[tuple[str, str]] = []

    def error(self, message: str) -> None:
        self.records.append(("error", message))


def _run(breaches: UidBreaches, monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    recorder = RecordingLogger()
    monkeypatch.setattr(uid_grammar_check, "logger", recorder)
    check_uid_grammar(breaches)
    return recorder.records


def test_silent_on_a_graph_that_fits(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _run(UidBreaches(outside=0, shared=0), monkeypatch) == []


def test_a_uid_outside_the_grammar_is_an_error_naming_it(monkeypatch: pytest.MonkeyPatch) -> None:
    records = _run(
        UidBreaches(outside=2, shared=0, outside_sample=("Group group_x", "Task task_y")),
        monkeypatch,
    )
    assert len(records) == 1
    level, message = records[0]
    assert level == "error"
    assert "2 uid(s) outside the grammar" in message
    assert "Group group_x, Task task_y" in message
    assert "./dev uid-census" in message


def test_a_shared_uid_is_an_error_of_its_own(monkeypatch: pytest.MonkeyPatch) -> None:
    records = _run(
        UidBreaches(outside=1, shared=1, outside_sample=("Ku ku.Bad",), shared_sample=("ku.a",)),
        monkeypatch,
    )
    assert [level for level, _ in records] == ["error", "error"]
    assert "held by more than one node" in records[1][1]
    assert "ku.a" in records[1][1]
