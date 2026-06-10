"""
Tests for the bloat detector (event lifecycle analysis)
========================================================

Two layers:
- Synthetic tests: string content parsed into a fake ParsedCodebase — every
  publish/subscribe/dispatch shape, positive AND negative.
- Sentinel tests against the live codebase: known-live events must never be
  flagged; known-dead events must be. Sentinels referencing dead code are
  deleted alongside that code when it is removed.
"""

import ast
import sys
from pathlib import Path

import pytest

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from detect_bloat import (  # type: ignore[import-not-found]
    ROOT,
    BloatSeverity,
    EventUniverse,
    EventUsageCollector,
    ParsedCodebase,
    analyze_events,
)

# ============================================================================
# HELPERS
# ============================================================================

EVENTS_FILE = ROOT / "core" / "events" / "synthetic_events.py"

BASE_EVENTS_SRC = """
class BaseEvent:
    pass

class AlphaEvent(BaseEvent):
    pass

class BetaDerived(AlphaEvent):
    pass

class GammaOrphan(BaseEvent):
    pass
"""


def build_codebase(files: dict[str, str], tests: dict[str, str] | None = None) -> ParsedCodebase:
    """Fake ParsedCodebase from {relative_path: source} without touching disk."""
    codebase = ParsedCodebase(ROOT)
    codebase.production[EVENTS_FILE] = ast.parse(BASE_EVENTS_SRC)
    for rel, src in files.items():
        codebase.production[ROOT / rel] = ast.parse(src)
    for rel, src in (tests or {}).items():
        codebase.tests[ROOT / rel] = ast.parse(src)
    return codebase


def analyze(files: dict[str, str], tests: dict[str, str] | None = None):
    codebase = build_codebase(files, tests)
    universe = EventUniverse(codebase)
    universe.build()
    usage = EventUsageCollector(universe, codebase).collect()
    findings, _exempted = analyze_events(universe, usage)
    return universe, usage, findings


def finding_for(findings, subject):
    matches = [f for f in findings if f.subject == subject]
    return matches[0] if matches else None


# ============================================================================
# EVENT UNIVERSE — inheritance closure
# ============================================================================


def test_universe_includes_indirect_subclasses():
    universe, _, _ = analyze({})
    assert "AlphaEvent" in universe
    assert "BetaDerived" in universe  # via AlphaEvent, not BaseEvent directly
    assert "GammaOrphan" in universe
    assert "BaseEvent" not in universe.classes  # the root itself is not a finding subject


def test_descendants_map_is_transitive():
    universe, _, _ = analyze({})
    assert universe.descendants["AlphaEvent"] == {"BetaDerived"}


def test_non_event_classes_excluded():
    codebase = build_codebase({})
    codebase.production[ROOT / "core" / "events" / "other.py"] = ast.parse(
        "class NotAnEvent:\n    pass\n"
    )
    universe = EventUniverse(codebase)
    universe.build()
    assert "NotAnEvent" not in universe


# ============================================================================
# PUBLICATION SHAPES
# ============================================================================


def test_publish_event_helper_with_inline_constructor():
    _, usage, _ = analyze(
        {
            "core/services/x.py": (
                "from core.events import publish_event, AlphaEvent\n"
                "async def f(self):\n"
                "    await publish_event(self.event_bus, AlphaEvent(uid='1'), self.logger)\n"
            )
        }
    )
    assert "AlphaEvent" in usage.published


def test_publish_via_assigned_variable():
    _, usage, _ = analyze(
        {
            "core/services/x.py": (
                "async def f(self):\n"
                "    event = AlphaEvent(uid='1')\n"
                "    await self.event_bus.publish_async(event)\n"
            )
        }
    )
    assert "AlphaEvent" in usage.published


def test_publish_via_import_alias():
    _, usage, _ = analyze(
        {
            "core/services/x.py": (
                "from core.events.synthetic_events import AlphaEvent as Renamed\n"
                "async def f(self):\n"
                "    await publish_event(self.event_bus, Renamed(uid='1'), self.logger)\n"
            )
        }
    )
    assert "AlphaEvent" in usage.published


def test_module_level_publish_wrapper_is_inferred():
    # The group_service shape: a local wrapper publishing its parameter.
    _, usage, _ = analyze(
        {
            "core/services/x.py": (
                "async def _my_publish(event_bus, event, logger):\n"
                "    await event_bus.publish_async(event)\n"
                "async def f(self):\n"
                "    await _my_publish(self.event_bus, AlphaEvent(uid='1'), self.logger)\n"
            )
        }
    )
    assert "AlphaEvent" in usage.published
    assert not usage.unresolved_publishes  # wrapper interior is accounted for


def test_method_publish_wrapper_strips_self():
    # The BaseAIService shape: self._publish(event) -> caller arg index 0.
    _, usage, _ = analyze(
        {
            "core/services/x.py": (
                "class S:\n"
                "    async def _emit(self, event):\n"
                "        await self.event_bus.publish_async(event)\n"
                "    async def f(self):\n"
                "        await self._emit(AlphaEvent(uid='1'))\n"
            )
        }
    )
    assert "AlphaEvent" in usage.published


def test_same_name_wrappers_with_different_signatures():
    # Regression: two defs named alike, event at different positions — both
    # call sites must resolve (the dedup-by-param-name bug).
    _, usage, _ = analyze(
        {
            "core/services/a.py": (
                "async def _emit(event_bus, event, logger):\n"
                "    await event_bus.publish_async(event)\n"
                "async def f(self):\n"
                "    await _emit(self.event_bus, AlphaEvent(uid='1'), self.logger)\n"
            ),
            "core/services/b.py": (
                "class S:\n"
                "    async def _emit(self, event):\n"
                "        await self.event_bus.publish_async(event)\n"
                "    async def f(self):\n"
                "        await self._emit(GammaOrphan(uid='1'))\n"
            ),
        }
    )
    assert "AlphaEvent" in usage.published
    assert "GammaOrphan" in usage.published


def test_cross_file_publish_lands_unverified_not_dead():
    # Constructed in one file, published as a parameter in another through an
    # unknown helper: no cross-file dataflow by design -> UNVERIFIED tier.
    _, usage, findings = analyze(
        {
            "core/services/maker.py": ("def make():\n    return AlphaEvent(uid='1')\n"),
            "core/services/sender.py": (
                "async def send(bus, thing):\n    await bus.publish_async(thing)\n"
            ),
        }
    )
    assert "AlphaEvent" not in usage.published
    finding = finding_for(findings, "AlphaEvent")
    assert finding is not None
    assert finding.severity is BloatSeverity.UNVERIFIED


def test_unresolvable_publish_event_arg_is_counted():
    # An unknown attribute arg counts as unresolved. (A function publishing
    # its own parameter is instead promoted to a wrapper — interior excluded.)
    _, usage, _ = analyze(
        {
            "core/services/y.py": (
                "async def f(self):\n"
                "    await publish_event(self.event_bus, self.pending, self.logger)\n"
            )
        }
    )
    assert len(usage.unresolved_publishes) == 1


def test_test_only_publication_does_not_confer_liveness():
    _, usage, findings = analyze(
        {},
        tests={
            "tests/unit/x_test.py": (
                "async def test_f(bus):\n    await publish_event(bus, AlphaEvent(uid='1'), None)\n"
            )
        },
    )
    assert "AlphaEvent" not in usage.published
    finding = finding_for(findings, "AlphaEvent")
    assert finding is not None
    assert finding.severity is BloatSeverity.WARNING
    assert any("tests" in note for note in finding.annotations)


# ============================================================================
# SUBSCRIPTION SHAPES
# ============================================================================


def test_direct_subscription():
    _, usage, _ = analyze(
        {
            "services_bootstrap/wiring.py": (
                "def wire(event_bus, handler):\n    event_bus.subscribe(AlphaEvent, handler)\n"
            )
        }
    )
    assert "AlphaEvent" in usage.subscribed


def test_loop_subscription_over_assigned_list():
    _, usage, _ = analyze(
        {
            "services_bootstrap/wiring.py": (
                "def wire(event_bus, handler):\n"
                "    events = [AlphaEvent, GammaOrphan]\n"
                "    for event_type in events:\n"
                "        event_bus.subscribe(event_type, handler)\n"
            )
        }
    )
    assert "AlphaEvent" in usage.subscribed
    assert "GammaOrphan" in usage.subscribed


def test_loop_subscription_over_inline_list():
    _, usage, _ = analyze(
        {
            "services_bootstrap/wiring.py": (
                "def wire(event_bus, handler):\n"
                "    for event_type in [AlphaEvent]:\n"
                "        event_bus.subscribe(event_type, handler)\n"
            )
        }
    )
    assert "AlphaEvent" in usage.subscribed


def test_aliased_subscription():
    _, usage, _ = analyze(
        {
            "services_bootstrap/wiring.py": (
                "from core.events.synthetic_events import AlphaEvent as ZPDAlpha\n"
                "def wire(event_bus, handler):\n"
                "    event_bus.subscribe(ZPDAlpha, handler)\n"
            )
        }
    )
    assert "AlphaEvent" in usage.subscribed


def test_docstring_subscribe_example_is_inert():
    _, usage, _ = analyze(
        {
            "core/services/x.py": (
                "def f():\n"
                '    """Example:\n'
                "        event_bus.subscribe(AlphaEvent, handler)\n"
                '    """\n'
                "    return None\n"
            )
        }
    )
    assert "AlphaEvent" not in usage.subscribed
    assert not usage.unresolved_subscribes


def test_unresolvable_subscription_is_counted():
    _, usage, _ = analyze(
        {
            "core/services/x.py": (
                "def wire(event_bus, handlers):\n"
                "    for event_type, handler in handlers.items():\n"
                "        event_bus.subscribe(event_type, handler)\n"
            )
        }
    )
    assert len(usage.unresolved_subscribes) == 1


# ============================================================================
# FINDINGS TAXONOMY
# ============================================================================


def test_dead_event_with_subscriber_gets_annotation():
    _, _, findings = analyze(
        {
            "services_bootstrap/wiring.py": (
                "def wire(event_bus, handler):\n    event_bus.subscribe(AlphaEvent, handler)\n"
            )
        }
    )
    finding = finding_for(findings, "AlphaEvent")
    assert finding is not None
    assert finding.severity is BloatSeverity.WARNING
    assert any("dead wiring chain" in note for note in finding.annotations)


def test_descendant_publication_keeps_base_alive():
    _, _, findings = analyze(
        {
            "core/services/x.py": (
                "async def f(self):\n"
                "    await publish_event(self.event_bus, BetaDerived(uid='1'), self.logger)\n"
            )
        }
    )
    base = finding_for(findings, "AlphaEvent")
    # AlphaEvent is publish-live through BetaDerived: never WARNING/UNVERIFIED.
    assert base is None or base.severity is BloatSeverity.INFO


def test_published_never_subscribed_is_info():
    _, _, findings = analyze(
        {
            "core/services/x.py": (
                "async def f(self):\n"
                "    await publish_event(self.event_bus, GammaOrphan(uid='1'), self.logger)\n"
            )
        }
    )
    finding = finding_for(findings, "GammaOrphan")
    assert finding is not None
    assert finding.severity is BloatSeverity.INFO


# ============================================================================
# SENTINELS — live codebase ground truth
# ============================================================================


@pytest.fixture(scope="module")
def live_analysis():
    codebase = ParsedCodebase(ROOT)
    codebase.load()
    universe = EventUniverse(codebase)
    universe.build()
    usage = EventUsageCollector(universe, codebase).collect()
    findings, _exempted = analyze_events(universe, usage)
    return universe, usage, findings


def test_live_known_published_events_are_never_flagged_dead(live_analysis):
    # Each of these was a FALSE POSITIVE of the old suffix-regex detector.
    _, usage, findings = live_analysis
    for event in ["UserEntryApproved", "ReportSubmitted", "TranscriptionFailed", "GroupCreated"]:
        assert event in usage.published, f"{event} must be recognized as published"
        finding = finding_for(findings, event)
        assert finding is None or finding.severity is BloatSeverity.INFO


def test_live_known_dead_events_are_flagged(live_analysis):
    # Verified by hand (zero production references). Delete each sentinel
    # entry alongside the dead event when it is removed.
    _, _, findings = live_analysis
    for event in [
        "ExerciseCreated",
        "ExerciseSubmitted",
        "PrerequisitesAnalyzed",
        "UserEntryDeleted",
    ]:
        finding = finding_for(findings, event)
        assert finding is not None and finding.severity is BloatSeverity.WARNING, (
            f"{event} should be flagged structurally dead"
        )


def test_live_docstring_examples_do_not_subscribe(live_analysis):
    # goal_events.py docstrings mention achievement_service/dashboard_service
    # subscriptions that exist nowhere in real code.
    _, usage, _ = live_analysis
    for sites in usage.subscribed.values():
        for site in sites:
            assert site.file != "core/events/goal_events.py"


def test_live_collector_self_diagnostic(live_analysis):
    # A scanner finding nothing is more likely broken than the codebase silent.
    _, usage, _ = live_analysis
    assert sum(len(v) for v in usage.published.values()) > 100
    assert sum(len(v) for v in usage.subscribed.values()) > 100
    # Resolution quality bar: at most a handful of irreducible unresolved sites.
    assert len(usage.unresolved_publishes) <= 3
    assert len(usage.unresolved_subscribes) <= 4
