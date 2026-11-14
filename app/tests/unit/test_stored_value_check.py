"""In-app stored-value check and the census's readers.

``check_stored_values`` is the PRODUCTION evaluator of the stored-value census
(production runs no Prometheus — ``StoredValueUnreadable`` evaluates only in dev):
silent on a graph whose every value reads, one ERROR naming a few while any does
not. ``mapper_readers`` is the set the census reads: every node reader the backends
are, users and sessions, never the base ``Entity`` reader. The module logger is
stubbed, as in ``test_uid_grammar_check.py`` — structlog's sink is process-global.
"""

import pytest

from adapters.persistence.neo4j.stored_value_census_backend import mapper_readers
from core.infrastructure.monitoring import stored_value_check
from core.infrastructure.monitoring.stored_value_check import (
    UnreadableStoredValues,
    check_stored_values,
)
from core.models.auth.session import Session
from core.models.enums.neo_labels import NeoLabel
from core.models.user.user import User
from tests.helpers.production_backends import build_production_backends


class RecordingLogger:
    """Captures error messages in place of the module structlog logger."""

    def __init__(self) -> None:
        self.records: list[str] = []

    def error(self, message: str) -> None:
        self.records.append(message)


def _run(found: UnreadableStoredValues, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    recorder = RecordingLogger()
    monkeypatch.setattr(stored_value_check, "logger", recorder)
    check_stored_values(found)
    return recorder.records


def test_silent_on_a_graph_whose_every_value_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _run(UnreadableStoredValues(count=0), monkeypatch) == []


def test_an_unreadable_value_is_an_error_naming_it(monkeypatch: pytest.MonkeyPatch) -> None:
    records = _run(
        UnreadableStoredValues(count=3, sample=("Task task_x.status", "Ku ku.a.b.complexity")),
        monkeypatch,
    )

    assert len(records) == 1
    assert "unreadable stored values: 3" in records[0]
    assert "Task task_x.status, Ku ku.a.b.complexity" in records[0]
    assert "./dev stored-value-census" in records[0]


def test_the_census_reads_every_backend_node_reader() -> None:
    backends = build_production_backends(object())
    readers = backends["stored_value_census_backend"].readers
    labels = {label for label, _ in readers}

    assert readers == mapper_readers(backends.values())
    assert {(NeoLabel.USER, User), (NeoLabel.SESSION, Session)} <= set(readers)
    assert {NeoLabel.TASK, NeoLabel.KU, NeoLabel.GROUP, NeoLabel.LEARNING_PATH} <= labels
    assert NeoLabel.ENTITY not in labels
    assert len(readers) == len(set(readers))
