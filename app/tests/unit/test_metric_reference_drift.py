"""Drift guard: every metric name referenced by dashboards/alerts must be defined.

Grafana panels and Prometheus alert rules reference metrics by name with no
compile-time link to ``prometheus_metrics.py`` — a renamed or never-instrumented
metric silently renders an empty panel or an alert that can never fire. This
guard closes that gap statically: any ``skuel_*`` name appearing in
``monitoring/grafana/dashboards/*.json`` or ``monitoring/prometheus/alerts.yml``
must resolve to a metric defined in
``core/infrastructure/monitoring/prometheus_metrics.py``.

Commented-out alert rules are deliberately IN scope: staged rules (e.g. the
``skuel_slo`` group) must reference real metrics too, or they rot before they
are ever enabled. Emit-first doctrine (CLAUDE.md § Observability): a metric
definition lands WITH its emission — so "defined" here is a faithful proxy for
"emitted".

See: monitoring/README.md, @prometheus-grafana skill
"""

from __future__ import annotations

import re
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]

METRICS_SOURCE = APP_ROOT / "core" / "infrastructure" / "monitoring" / "prometheus_metrics.py"
DASHBOARDS_DIR = APP_ROOT / "monitoring" / "grafana" / "dashboards"
ALERTS_FILE = APP_ROOT / "monitoring" / "prometheus" / "alerts.yml"

# Alert GROUP names match the skuel_[a-z0-9_]+ pattern but are rule-group
# identifiers, not metrics — without this allowlist they would be permanent
# false positives. skuel_critical is the live group; skuel_slo is the staged
# (commented-out) group, which the commented-line scan deliberately still sees.
NON_METRIC_NAMES: frozenset[str] = frozenset({"skuel_critical", "skuel_slo"})

# Prometheus histograms expose derived series the source never names literally.
HISTOGRAM_SUFFIXES: tuple[str, ...] = ("_bucket", "_sum", "_count")

# All metric names in prometheus_metrics.py appear as double-quoted string
# literals (the Counter/Gauge/Histogram name argument).
_DEFINITION_PATTERN = re.compile(r'"(skuel_[a-z0-9_]+)"')
_REFERENCE_PATTERN = re.compile(r"\bskuel_[a-z0-9_]+")


def load_defined_metric_names() -> set[str]:
    """Metric names defined (and, per emit-first, emitted) by the app."""
    return set(_DEFINITION_PATTERN.findall(METRICS_SOURCE.read_text()))


def extract_references(text: str, filename: str) -> list[tuple[str, str]]:
    """All ``skuel_*`` names in ``text`` as (name, filename) pairs.

    Commented lines are NOT filtered out — staged alert rules must stay honest.
    """
    return [
        (name, filename)
        for name in _REFERENCE_PATTERN.findall(text)
        if name not in NON_METRIC_NAMES
    ]


def collect_monitoring_references() -> list[tuple[str, str]]:
    """Every metric reference across Grafana dashboards and alert rules."""
    references: list[tuple[str, str]] = []
    for path in sorted(DASHBOARDS_DIR.glob("*.json")):
        references.extend(extract_references(path.read_text(), path.name))
    references.extend(extract_references(ALERTS_FILE.read_text(), ALERTS_FILE.name))
    return references


def resolves(name: str, defined: set[str]) -> bool:
    """True if ``name`` is a defined metric or a derived histogram series.

    Exact match MUST run before suffix stripping: gauges like
    ``skuel_orphaned_entities_count`` end in ``_count`` as part of their LITERAL
    name — stripping first would probe for a nonexistent
    ``skuel_orphaned_entities`` and wrongly flag them.
    """
    if name in defined:
        return True
    return any(
        name.endswith(suffix) and name.removesuffix(suffix) in defined
        for suffix in HISTOGRAM_SUFFIXES
    )


DEFINED: set[str] = load_defined_metric_names()


def test_metric_definitions_were_found() -> None:
    """An empty DEFINED set would make the drift test pass vacuously backwards.

    (Zero definitions means every reference fails, but a regex/path regression
    should announce itself as THIS failure, not as 40 confusing offenders.)
    """
    assert DEFINED, f"no skuel_* metric definitions found in {METRICS_SOURCE}"


def test_all_referenced_metric_names_are_defined() -> None:
    """No dashboard panel or alert rule may reference an undefined metric."""
    unresolved = [
        (name, filename)
        for name, filename in collect_monitoring_references()
        if not resolves(name, DEFINED)
    ]
    offenders = "\n".join(
        f"  {name}  (in {filename})" for name, filename in sorted(set(unresolved))
    )
    assert not unresolved, (
        "Metric references with no matching definition in prometheus_metrics.py:\n"
        f"{offenders}\n"
        "Fix: instrument the metric (definition + emission in the same change — "
        "emit-first doctrine) or remove the stale dashboard/alert reference."
    )


def test_unknown_metric_is_flagged() -> None:
    """Synthetic negative: the guard must actually detect drift, not just pass."""
    assert resolves("skuel_nonexistent_metric_total", DEFINED) is False

    fabricated = "expr: rate(skuel_nonexistent_metric_total[5m]) > 0"
    extracted = extract_references(fabricated, "fabricated.yml")
    assert ("skuel_nonexistent_metric_total", "fabricated.yml") in extracted
    assert [pair for pair in extracted if not resolves(pair[0], DEFINED)] == [
        ("skuel_nonexistent_metric_total", "fabricated.yml")
    ]


def test_allowlisted_group_names_are_excluded() -> None:
    """The allowlist strips group names but never a real metric reference."""
    text = "- name: skuel_critical\n  expr: skuel_http_errors_total > 0"
    extracted = extract_references(text, "alerts.yml")
    assert extracted == [("skuel_http_errors_total", "alerts.yml")]
