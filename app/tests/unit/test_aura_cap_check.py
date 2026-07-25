"""In-app AuraDB cap evaluator tests.

``check_aura_cap_headroom`` is the PRODUCTION evaluator for the AuraDB Free
caps (production runs no Prometheus — the alert rules only evaluate in dev),
so its threshold semantics are load-bearing: strictly greater-than, mirroring
the alert exprs (``skuel_total_entities > 160000``), WARNING above 80% of cap,
ERROR above 95%. The poller calls it every 5-min cycle; over-threshold logging
repeats each cycle by design (visibility over elegance).

Logging goes through structlog, whose sink depends on process-global config —
so the module logger is stubbed and assertions run on captured (level, message)
pairs, not on a handler.
"""

from core.constants import AuraDBCaps
from core.infrastructure.monitoring import aura_cap_check
from core.infrastructure.monitoring.aura_cap_check import check_aura_cap_headroom


class RecordingLogger:
    """Captures (level, message) pairs in place of the module structlog logger."""

    def __init__(self) -> None:
        self.records: list[tuple[str, str]] = []

    def warning(self, message: str) -> None:
        self.records.append(("warning", message))

    def error(self, message: str) -> None:
        self.records.append(("error", message))


def _run(total_nodes: int, total_relationships: int, monkeypatch) -> list[tuple[str, str]]:
    recorder = RecordingLogger()
    monkeypatch.setattr(aura_cap_check, "logger", recorder)
    check_aura_cap_headroom(total_nodes, total_relationships)
    return recorder.records


def test_silent_under_and_at_warning_threshold(monkeypatch) -> None:
    """Strictly greater-than: exactly 80% of cap does NOT log (alert-expr parity)."""
    assert _run(0, 0, monkeypatch) == []
    assert _run(AuraDBCaps.WARNING_NODES, AuraDBCaps.WARNING_RELATIONSHIPS, monkeypatch) == []


def test_warning_above_80_percent(monkeypatch) -> None:
    records = _run(AuraDBCaps.WARNING_NODES + 1, 0, monkeypatch)
    assert len(records) == 1
    level, message = records[0]
    assert level == "warning"
    assert "nodes" in message
    assert "80%" in message
    assert f"{AuraDBCaps.NODE_CAP:,}" in message
    assert "telemetry-retention" in message


def test_error_above_95_percent(monkeypatch) -> None:
    """Above 95% escalates to ERROR (once, not WARNING+ERROR)."""
    records = _run(AuraDBCaps.ERROR_NODES + 1, 0, monkeypatch)
    assert [level for level, _ in records] == ["error"]
    # At exactly 95% the strictly-greater comparison keeps it a WARNING.
    records = _run(AuraDBCaps.ERROR_NODES, 0, monkeypatch)
    assert [level for level, _ in records] == ["warning"]


def test_dimensions_evaluate_independently(monkeypatch) -> None:
    records = _run(AuraDBCaps.WARNING_NODES + 1, AuraDBCaps.ERROR_RELATIONSHIPS + 1, monkeypatch)
    assert [(level, "nodes" in msg) for level, msg in records] == [
        ("warning", True),
        ("error", False),
    ]
    assert "relationships" in records[1][1]


def test_thresholds_derive_from_caps_exactly() -> None:
    """Integer derivation guard: float ratios would truncate 95% of 200k to 189,999."""
    assert AuraDBCaps.WARNING_NODES == 160_000
    assert AuraDBCaps.WARNING_RELATIONSHIPS == 320_000
    assert AuraDBCaps.ERROR_NODES == 190_000
    assert AuraDBCaps.ERROR_RELATIONSHIPS == 380_000
