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
from datetime import date, timedelta
from pathlib import Path
from typing import cast

import pytest

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import detect_bloat  # type: ignore[import-not-found]
from detect_bloat import (  # type: ignore[import-not-found]
    PLANNED_EVENTS,
    ROOT,
    BloatSeverity,
    DispatchKnowledge,
    EventUniverse,
    EventUsageCollector,
    Finding,
    ParsedCodebase,
    PlannedEntry,
    Readiness,
    VultureScan,
    analyze_events,
    analyze_methods,
    analyze_planned_templates,
    build_parser,
    gate_fails,
    json_document,
    measure_vulture_blind_spot,
    print_event_report,
    print_ready_report,
    print_summary,
    print_template_report,
    run_vulture,
    summarize_planned_aging,
)

# ============================================================================
# HELPERS
# ============================================================================

EVENTS_FILE = ROOT / "core" / "events" / "synthetic_events.py"


def staged(reason: str = "awaiting synthetic wiring") -> PlannedEntry:
    """A synthetic PLANNED entry — readiness and date are required, so tests
    that only care about the tier mechanics get them from one place."""
    return PlannedEntry(Readiness.DELAYED, reason, since=date(2026, 6, 10))


def ready(reason: str = "awaiting synthetic wiring", *, days_ago: int = 0) -> PlannedEntry:
    """A READY synthetic entry staged ``days_ago`` days before today — the
    aging tests measure against today, so the date is relative by design."""
    return PlannedEntry(Readiness.READY, reason, since=date.today() - timedelta(days=days_ago))


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
# PLANNED TIER — unwired by intent is not bloat
# ============================================================================


def test_planned_event_reports_planned_not_dead(monkeypatch):
    # setattr replaces the registry wholesale — the production entries (real
    # embedding events) are absent from synthetic universes and would
    # otherwise fire the vanished-key stale check.
    monkeypatch.setattr(detect_bloat, "PLANNED_EVENTS", {"GammaOrphan": staged()})
    _, _, findings = analyze({})
    finding = finding_for(findings, "GammaOrphan")
    assert finding is not None
    assert finding.severity is BloatSeverity.PLANNED
    assert finding.kind == "event-awaiting-wiring"
    assert "awaiting synthetic wiring" in finding.detail


def test_planned_event_subscriber_is_staging_not_dead_chain(monkeypatch):
    monkeypatch.setattr(detect_bloat, "PLANNED_EVENTS", {"GammaOrphan": staged()})
    _, _, findings = analyze(
        {
            "services_bootstrap/wiring.py": (
                "def wire(event_bus, handler):\n    event_bus.subscribe(GammaOrphan, handler)\n"
            )
        }
    )
    finding = finding_for(findings, "GammaOrphan")
    assert finding is not None
    assert finding.severity is BloatSeverity.PLANNED
    assert any("subscribers staged" in note for note in finding.annotations)
    assert not any("dead wiring chain" in note for note in finding.annotations)


def test_published_planned_event_is_masked_not_stale(monkeypatch):
    monkeypatch.setattr(detect_bloat, "PLANNED_EVENTS", {"GammaOrphan": staged()})
    _, _, findings = analyze(
        {
            "core/services/x.py": (
                "async def f(self):\n"
                "    await publish_event(self.event_bus, GammaOrphan(uid='1'), self.logger)\n"
            )
        }
    )
    # publish resolution over-approximates (file-scoped var index, class
    # registries, inferred wrappers), so "now published" can never gate — it is
    # reported as unverifiable, not stale (Codex P2, PR #1188).
    assert not [f for f in findings if f.kind == "planned-marking-stale"]
    masked = [f for f in findings if f.kind == "planned-marking-masked"]
    assert [f.subject for f in masked] == ["GammaOrphan"]
    assert masked[0].severity is BloatSeverity.INFO
    assert "cannot be attributed" in masked[0].detail


def test_vanished_planned_event_marking_is_reported(monkeypatch):
    # A PLANNED_EVENTS key whose class was deleted/renamed/mistyped is not in
    # the universe — the stale check must still fire (Codex P2, PR #274).
    monkeypatch.setattr(detect_bloat, "PLANNED_EVENTS", {"NoSuchEventAnywhere": staged()})
    _, _, findings = analyze({})
    stale = [f for f in findings if f.kind == "planned-marking-stale"]
    assert [f.subject for f in stale] == ["NoSuchEventAnywhere"]
    assert stale[0].severity is BloatSeverity.WARNING
    assert "no such event class" in stale[0].detail


class FakeVultureItem:
    def __init__(self, rel: str, name: str, lineno: int = 1):
        self.filename = str(ROOT / rel)
        self.name = name
        self.first_lineno = lineno
        self.typ = "method"
        self.confidence = 60


def test_planned_method_reports_planned_not_dead(monkeypatch):
    # setattr replaces the registry wholesale — the production entries (real
    # staged habit/search methods) are absent from synthetic universes and
    # would otherwise fire the vanished-key stale check.
    monkeypatch.setattr(
        detect_bloat,
        "PLANNED_METHODS",
        {"core/services/x.py::future_method": staged()},
    )
    codebase = build_codebase({"core/services/x.py": "def future_method():\n    pass\n"})
    analysis = analyze_methods(
        codebase,
        VultureScan([FakeVultureItem("core/services/x.py", "future_method")], frozenset()),
    )
    finding = finding_for(analysis.findings, "future_method")
    assert finding is not None
    assert finding.severity is BloatSeverity.PLANNED
    assert finding.kind == "method-awaiting-wiring"


def test_stale_planned_method_marking_when_definition_vanished(monkeypatch):
    monkeypatch.setattr(
        detect_bloat,
        "PLANNED_METHODS",
        {"core/services/x.py::deleted_method": staged()},
    )
    codebase = build_codebase({})
    # not a vulture candidate, and no definition anywhere -> deleted or renamed
    analysis = analyze_methods(codebase, VultureScan([], frozenset()))
    stale = [f for f in analysis.findings if f.kind == "planned-marking-stale"]
    assert [f.subject for f in stale] == ["deleted_method"]
    assert stale[0].severity is BloatSeverity.WARNING
    assert "no longer exists at this path" in stale[0].detail


def test_attribute_collision_on_a_single_def_is_masked_not_stale(monkeypatch):
    """One `x.name` load anywhere drops the candidate — with only ONE def.

    Codex P2 on PR #1188: counting definition sites catches only the def-side
    collision. Vulture's used-name set is global by attribute name, so an
    unrelated `other.only_defined_once` masks a method that is still unwired.
    Reading that as "wiring complete" would fail --check on honest staged work.
    """
    monkeypatch.setattr(
        detect_bloat,
        "PLANNED_METHODS",
        {"core/services/x.py::only_defined_once": staged()},
    )
    codebase = build_codebase({"core/services/x.py": "def only_defined_once():\n    pass\n"})
    # single def, but the NAME is in vulture's used set -> unverifiable
    analysis = analyze_methods(codebase, VultureScan([], frozenset({"only_defined_once"})))

    assert not [f for f in analysis.findings if f.kind == "planned-marking-stale"]
    masked = [f for f in analysis.findings if f.kind == "planned-marking-masked"]
    assert [f.subject for f in masked] == ["only_defined_once"]
    assert masked[0].severity is BloatSeverity.INFO
    assert "loaded as an attribute elsewhere" in masked[0].detail


def test_name_masked_planned_method_is_flagged_but_never_stale(monkeypatch):
    """A same-named method elsewhere makes vulture drop the candidate.

    Regression for the attendee pair (#1119): the service method stayed staged
    and unwired, but `self.backend.add_attendee(...)` marked the NAME used, so
    the old negative-only check called a true marking stale. Deleting the entry
    to clear that report would have hidden genuinely staged work.
    """
    monkeypatch.setattr(
        detect_bloat,
        "PLANNED_METHODS",
        {"core/services/x.py::add_attendee": staged()},
    )
    codebase = build_codebase(
        {
            "core/services/x.py": "def add_attendee():\n    pass\n",
            "core/services/y.py": "def add_attendee():\n    pass\n",
        }
    )
    analysis = analyze_methods(codebase, VultureScan([], frozenset()))

    assert not [f for f in analysis.findings if f.kind == "planned-marking-stale"]
    masked = [f for f in analysis.findings if f.kind == "planned-marking-masked"]
    assert [f.subject for f in masked] == ["add_attendee"]
    assert masked[0].severity is BloatSeverity.INFO
    assert "defined at 2 sites" in masked[0].detail
    assert "KEEP the entry" in masked[0].detail


def test_planned_event_outside_universe_but_defined_is_masked(monkeypatch):
    """A class that exists but stopped being an event is an inheritance defect.

    Codex P2 on PR #1188: universe membership proves event ELIGIBILITY, not
    definition existence. A base-class edit — or a module missing from
    core/events/__init__.py — drops a live class out of the universe, and
    gating on that would tell the maintainer to delete registry metadata when
    the real repair is the inheritance.
    """
    monkeypatch.setattr(detect_bloat, "PLANNED_EVENTS", {"NotAnEventAnymore": staged()})
    codebase = build_codebase(
        {"core/events/x.py": "class NotAnEventAnymore:\n    pass\n"},
    )
    universe = EventUniverse(codebase)
    universe.build()
    usage = EventUsageCollector(universe, codebase).collect()
    findings, _exempted = analyze_events(universe, usage)

    assert not [f for f in findings if f.kind == "planned-marking-stale"]
    masked = [f for f in findings if f.kind == "planned-marking-masked"]
    assert [f.subject for f in masked] == ["NotAnEventAnymore"]
    assert masked[0].severity is BloatSeverity.INFO
    assert "outside the event universe" in masked[0].detail
    assert masked[0].file == "core/events/x.py"


def test_same_named_class_outside_events_package_does_not_mask_a_deleted_event(monkeypatch):
    """A name collision outside core/events/ must not suppress a true stale.

    Codex round 5 on PR #1188: the first cut scanned the whole tree, so an
    unrelated `class TaskCompleted` in a service would have masked a genuinely
    deleted event and dropped it out of the gate. The scan is scoped with the
    same predicate EventUniverse.build uses.
    """
    monkeypatch.setattr(detect_bloat, "PLANNED_EVENTS", {"DeletedEvent": staged()})
    codebase = build_codebase({"core/services/x.py": "class DeletedEvent:\n    pass\n"})
    universe = EventUniverse(codebase)
    universe.build()
    usage = EventUsageCollector(universe, codebase).collect()
    findings, _exempted = analyze_events(universe, usage)

    assert not [f for f in findings if f.kind == "planned-marking-masked"]
    stale = [f for f in findings if f.kind == "planned-marking-stale"]
    assert [f.subject for f in stale] == ["DeletedEvent"]
    assert stale[0].severity is BloatSeverity.WARNING


# ============================================================================
# PLANNED_TEMPLATES — existence is provable, a render match is not
# ============================================================================


def _template_codebase(tmp_path, sources: dict[str, str], on_disk: list[str]) -> ParsedCodebase:
    """ParsedCodebase rooted in tmp_path, with real .md floors written out.

    analyze_planned_templates stats the filesystem, so the root cannot be the
    repo — these tests own their template directory.
    """
    codebase = ParsedCodebase(tmp_path)
    for rel, src in sources.items():
        codebase.production[tmp_path / rel] = ast.parse(src)
    tdir = tmp_path / detect_bloat.TEMPLATES_DIR_REL
    tdir.mkdir(parents=True, exist_ok=True)
    for template_id in on_disk:
        (tdir / f"{template_id}.md").write_text("# floor\n", encoding="utf-8")
    return codebase


def test_stale_planned_template_marking_when_file_vanished(monkeypatch, tmp_path):
    monkeypatch.setattr(detect_bloat, "PLANNED_TEMPLATES", {"gone_tpl": staged()})
    findings = analyze_planned_templates(_template_codebase(tmp_path, {}, []))
    stale = [f for f in findings if f.kind == "planned-marking-stale"]
    assert [f.subject for f in stale] == ["gone_tpl"]
    assert stale[0].severity is BloatSeverity.WARNING
    assert "no longer exists" in stale[0].detail


def test_receiver_blind_render_match_is_masked_not_stale(monkeypatch, tmp_path):
    """An unrelated `.get()` on the same string must not demand removal.

    Codex P2 on PR #1188: _collect_rendered_template_ids is receiver-blind, so
    `settings.get("staged_tpl")` reads as a render site. Raising the became-live
    report to WARNING would have turned that pre-existing false positive into a
    CI failure telling the author to delete a still-valid PLANNED entry.
    """
    monkeypatch.setattr(detect_bloat, "PLANNED_TEMPLATES", {"staged_tpl": staged()})
    codebase = _template_codebase(
        tmp_path,
        {"core/services/x.py": 'def f(settings):\n    return settings.get("staged_tpl")\n'},
        ["staged_tpl"],
    )
    findings = analyze_planned_templates(codebase)

    assert not [f for f in findings if f.kind == "planned-marking-stale"]
    masked = [f for f in findings if f.kind == "planned-marking-masked"]
    assert [f.subject for f in masked] == ["staged_tpl"]
    assert masked[0].severity is BloatSeverity.INFO
    assert "receiver-blind" in masked[0].detail


def test_unreferenced_template_stays_planned(monkeypatch, tmp_path):
    monkeypatch.setattr(detect_bloat, "PLANNED_TEMPLATES", {"staged_tpl": staged()})
    findings = analyze_planned_templates(_template_codebase(tmp_path, {}, ["staged_tpl"]))
    assert [(f.kind, f.severity) for f in findings] == [
        ("template-awaiting-wiring", BloatSeverity.PLANNED)
    ]


# ============================================================================
# PLANNED-TIER AGING — backlog size + oldest staging decision (structured)
# ============================================================================


def test_aging_oldest_is_the_earliest_since_across_entries():
    summary = summarize_planned_aging(
        "PLANNED_TEST",
        {
            "a": PlannedEntry(Readiness.DELAYED, "staged surface", since=date(2026, 6, 13)),
            "b": PlannedEntry(Readiness.READY, "staged twin", since=date(2026, 6, 12)),
            "c": PlannedEntry(Readiness.DELAYED, "staged lens", since=date(2026, 7, 25)),
        },
    )
    assert summary.entries == 3
    assert summary.oldest == date(2026, 6, 12)


def test_aging_splits_by_readiness():
    # A DELAYED entry aging is expected; a READY one aging is the signal — so
    # the summary carries count + oldest per class, not just per tier.
    summary = summarize_planned_aging(
        "PLANNED_TEST",
        {
            "a": PlannedEntry(Readiness.DELAYED, "staged surface", since=date(2026, 6, 13)),
            "b": PlannedEntry(Readiness.READY, "staged twin", since=date(2026, 6, 12)),
            "c": PlannedEntry(Readiness.READY, "staged lens", since=date(2026, 7, 25)),
        },
    )
    assert (summary.ready.entries, summary.ready.oldest) == (2, date(2026, 6, 12))
    assert (summary.delayed.entries, summary.delayed.oldest) == (1, date(2026, 6, 13))
    assert summary.ready.entries + summary.delayed.entries == summary.entries


def test_aging_reads_since_not_prose():
    # A date in the reason prose is inert — the structured field is the only
    # source, which is the whole point of having one.
    summary = summarize_planned_aging(
        "PLANNED_TEST",
        {"a": PlannedEntry(Readiness.DELAYED, "re-ruled 2026-01-01", since=date(2026, 6, 10))},
    )
    assert summary.oldest == date(2026, 6, 10)


def test_aging_empty_registry_is_zero_not_error():
    summary = summarize_planned_aging("PLANNED_TEST", {})
    assert summary.entries == 0
    assert summary.oldest is None


def test_aging_json_shape_is_pinned_for_the_janitor_workflow():
    # weekly-janitor.yml reads these keys with jq — a rename breaks the
    # scheduled report without failing anything here unless pinned.
    doc = summarize_planned_aging("PLANNED_TEST", {"a": staged()}).to_json()
    assert doc == {
        "tier": "PLANNED_TEST",
        "entries": 1,
        "oldest": "2026-06-10",
        "ready": {"entries": 0, "oldest": None},
        "delayed": {"entries": 1, "oldest": "2026-06-10"},
    }


def test_json_document_top_level_keys_are_pinned_for_the_janitor_workflow():
    finding = Finding(
        kind="event-never-published",
        severity=BloatSeverity.WARNING,
        subject="AlphaEvent",
        file="core/events/x.py",
        line=1,
        detail="synthetic",
    )
    aging = summarize_planned_aging("PLANNED_TEST", {})
    doc = json_document([finding], [aging])
    assert sorted(doc) == ["findings", "planned_aging"]
    findings = cast("list[dict[str, object]]", doc["findings"])
    assert findings[0]["severity"] == "warning"
    # every finding carries the key; null when it is not about a PLANNED entry
    assert findings[0]["readiness"] is None


PLANNED_TIER_BORN = date(2026, 6, 10)  # campaign 1 — the first staging decision ever recorded


def test_live_registries_summarize_cleanly():
    # Sentinel over the live registries: every value is a PlannedEntry whose
    # staging decision is a real past date no earlier than the tier itself,
    # and the summary counts add up. Deliberately no exact-count/date pins —
    # entries come and go with wiring campaigns; the invariants are what hold.
    for tier, registry in [
        ("PLANNED_EVENTS", detect_bloat.PLANNED_EVENTS),
        ("PLANNED_METHODS", detect_bloat.PLANNED_METHODS),
        ("PLANNED_TEMPLATES", detect_bloat.PLANNED_TEMPLATES),
    ]:
        for key, entry in registry.items():
            assert isinstance(entry, PlannedEntry), key
            assert isinstance(entry.readiness, Readiness), key
            assert PLANNED_TIER_BORN <= entry.since <= date.today(), key
            assert entry.reason.strip(), key
        summary = summarize_planned_aging(tier, registry)
        assert summary.entries == len(registry)
        assert (summary.oldest is None) == (not registry)
        assert summary.ready.entries + summary.delayed.entries == summary.entries
    methods = summarize_planned_aging("PLANNED_METHODS", detect_bloat.PLANNED_METHODS)
    assert methods.oldest == PLANNED_TIER_BORN


def test_live_exempted_methods_still_exist(live_codebase):
    # EXEMPTED_METHODS has no stale audit in the detector (an exemption for a
    # deleted method is never reported), so this sentinel is the audit: every
    # key must name a definition that still exists at that path.
    for key in detect_bloat.EXEMPTED_METHODS:
        rel, _, name = key.rpartition("::")
        assert detect_bloat._definition_line(live_codebase, rel, name) > 0, key


# ============================================================================
# READINESS — the PLANNED block's third axis; --ready; the 90-day signal
# ============================================================================


def _planned(subject: str, readiness: Readiness | None) -> Finding:
    return Finding(
        kind="template-awaiting-wiring",
        severity=BloatSeverity.PLANNED,
        subject=subject,
        file="f.md",
        line=1,
        detail="synthetic",
        readiness=readiness,
    )


def _about(
    kind: str, severity: BloatSeverity, subject: str, readiness: Readiness | None
) -> Finding:
    return Finding(
        kind=kind,
        severity=severity,
        subject=subject,
        file="f",
        line=1,
        detail="synthetic",
        readiness=readiness,
    )


def test_planned_finding_without_readiness_is_rejected():
    # The PLANNED block is grouped by readiness — a PLANNED finding carrying
    # none would print nowhere, so construction refuses it (fail-fast applied
    # to the tool itself).
    with pytest.raises(ValueError, match="carries no readiness"):
        _planned("orphan", None)


def test_finding_json_carries_readiness_or_null():
    assert _planned("x", Readiness.READY).to_json()["readiness"] == "ready"
    assert _planned("x", Readiness.DELAYED).to_json()["readiness"] == "delayed"
    assert (
        _about("event-never-subscribed", BloatSeverity.INFO, "y", None).to_json()["readiness"]
        is None
    )


def test_awaiting_wiring_findings_carry_the_entry_readiness(monkeypatch):
    monkeypatch.setattr(
        detect_bloat,
        "PLANNED_METHODS",
        {
            "core/services/x.py::ready_method": ready(),
            "core/services/x.py::delayed_method": staged(),
        },
    )
    codebase = build_codebase(
        {"core/services/x.py": "def ready_method():\n    pass\n\ndef delayed_method():\n    pass\n"}
    )
    analysis = analyze_methods(
        codebase,
        VultureScan(
            [
                FakeVultureItem("core/services/x.py", "ready_method"),
                FakeVultureItem("core/services/x.py", "delayed_method", 4),
            ],
            frozenset(),
        ),
    )
    by_subject = {f.subject: f for f in analysis.findings}
    assert by_subject["ready_method"].readiness is Readiness.READY
    assert by_subject["delayed_method"].readiness is Readiness.DELAYED


def test_masked_and_stale_findings_carry_the_entry_readiness(monkeypatch):
    # --ready filters findings by readiness, so a READY entry the run found
    # masked or gone must still reach it: readiness is a fact about the ENTRY,
    # whatever the run learned about its subject.
    monkeypatch.setattr(
        detect_bloat,
        "PLANNED_METHODS",
        {
            "core/services/x.py::masked_ready": ready(),
            "core/services/x.py::gone_ready": ready(),
        },
    )
    codebase = build_codebase({"core/services/x.py": "def masked_ready():\n    pass\n"})
    analysis = analyze_methods(codebase, VultureScan([], frozenset({"masked_ready"})))
    by_subject = {f.subject: f for f in analysis.findings}
    assert by_subject["masked_ready"].kind == "planned-marking-masked"
    assert by_subject["gone_ready"].kind == "planned-marking-stale"
    assert {f.readiness for f in analysis.findings} == {Readiness.READY}


def test_ready_entry_past_the_window_gets_an_aging_finding_beside_its_row(monkeypatch):
    monkeypatch.setattr(
        detect_bloat,
        "PLANNED_METHODS",
        {"core/services/x.py::old_ready": ready(days_ago=detect_bloat.READY_AGING_DAYS + 1)},
    )
    codebase = build_codebase({"core/services/x.py": "def old_ready():\n    pass\n"})
    analysis = analyze_methods(
        codebase, VultureScan([FakeVultureItem("core/services/x.py", "old_ready")], frozenset())
    )
    # beside the backlog row — never instead of it
    assert [(f.kind, f.severity) for f in analysis.findings] == [
        ("method-awaiting-wiring", BloatSeverity.PLANNED),
        ("planned-ready-aging", BloatSeverity.INFO),
    ]
    row, aging = analysis.findings
    assert (aging.subject, aging.file, aging.line) == (row.subject, row.file, row.line)
    assert aging.readiness is Readiness.READY
    assert f"READY for {detect_bloat.READY_AGING_DAYS + 1} days" in aging.detail


@pytest.mark.parametrize(
    ("readiness", "days_ago"),
    [
        pytest.param(Readiness.READY, 89, id="ready-inside-the-window"),
        pytest.param(Readiness.DELAYED, 400, id="delayed-never-ages"),
    ],
)
def test_no_aging_finding_inside_the_window_or_for_delayed(monkeypatch, readiness, days_ago):
    entry = PlannedEntry(readiness, "staged", since=date.today() - timedelta(days=days_ago))
    monkeypatch.setattr(detect_bloat, "PLANNED_METHODS", {"core/services/x.py::m": entry})
    codebase = build_codebase({"core/services/x.py": "def m():\n    pass\n"})
    analysis = analyze_methods(
        codebase, VultureScan([FakeVultureItem("core/services/x.py", "m")], frozenset())
    )
    assert [f.kind for f in analysis.findings] == ["method-awaiting-wiring"]


def test_ready_aging_is_emitted_by_every_awaiting_wiring_site(monkeypatch, tmp_path):
    # Four construction sites carry the entry: events, in-scope methods,
    # out-of-scope methods, templates. One left out would age silently.
    old = ready(days_ago=detect_bloat.READY_AGING_DAYS + 1)
    monkeypatch.setattr(detect_bloat, "PLANNED_EVENTS", {"GammaOrphan": old})
    _, _, event_findings = analyze({})

    monkeypatch.setattr(
        detect_bloat,
        "PLANNED_METHODS",
        {"core/services/x.py::in_scope": old, "adapters/x.py::out_of_scope": old},
    )
    codebase = build_codebase(
        {
            "core/services/x.py": "def in_scope():\n    pass\n",
            "adapters/x.py": "def out_of_scope():\n    pass\n",
        }
    )
    method_findings = analyze_methods(
        codebase, VultureScan([FakeVultureItem("core/services/x.py", "in_scope")], frozenset())
    ).findings

    monkeypatch.setattr(detect_bloat, "PLANNED_TEMPLATES", {"old_tpl": old})
    template_findings = analyze_planned_templates(_template_codebase(tmp_path, {}, ["old_tpl"]))

    everything = event_findings + method_findings + template_findings
    aging = sorted(f.subject for f in everything if f.kind == "planned-ready-aging")
    assert aging == ["GammaOrphan", "in_scope", "old_tpl", "out_of_scope"]
    rows = sorted(f.subject for f in everything if f.severity is BloatSeverity.PLANNED)
    assert rows == aging  # beside, never instead


def test_ready_aging_is_info_and_never_fails_the_gate():
    aging = _about("planned-ready-aging", BloatSeverity.INFO, "x", Readiness.READY)
    assert not gate_fails([aging])
    stale = _about("planned-marking-stale", BloatSeverity.WARNING, "gone", Readiness.READY)
    assert gate_fails([aging, stale])


def test_report_prints_ready_before_delayed_each_labelled(capsys):
    print_template_report([_planned("later", Readiness.DELAYED), _planned("now", Readiness.READY)])
    out = capsys.readouterr().out
    ready_at, delayed_at = out.index("Planned, READY"), out.index("Planned, DELAYED")
    assert ready_at < out.index("now") < delayed_at < out.index("later")


def test_block_headings_carry_no_escapes_once_colours_are_disabled(capsys, monkeypatch):
    # main() calls Colors.disable() for non-tty stdout, which rewrites the class
    # attributes; a heading colour bound as a default at import would survive
    # that and leave an unterminated escape in piped output (Codex P2, #1190).
    for name in ("RED", "GREEN", "YELLOW", "BLUE", "CYAN", "BOLD", "DIM", "RESET"):
        monkeypatch.setattr(detect_bloat.Colors, name, "")
    print_template_report(
        [
            _planned("now", Readiness.READY),
            _about("planned-marking-stale", BloatSeverity.WARNING, "gone", Readiness.READY),
        ]
    )
    out = capsys.readouterr().out
    assert "\x1b[" not in out
    assert "Planned, READY" in out and "Stale planned markings" in out


def test_ready_aging_prints_under_its_own_heading_not_the_info_one(capsys):
    # The printers bucket INFO under "published but never subscribed"; the new
    # kind is pulled out by name the way stale/masked are.
    universe, usage, _ = analyze({})
    aging = _about("planned-ready-aging", BloatSeverity.INFO, "GammaOrphan", Readiness.READY)
    print_event_report(universe, usage, [aging], [], verbose=False)
    out = capsys.readouterr().out
    assert "Published but never subscribed" not in out
    assert f"READY for more than {detect_bloat.READY_AGING_DAYS} days" in out
    assert "GammaOrphan" in out


def test_ready_report_prints_only_ready_entries_in_whatever_state_the_run_found(capsys):
    findings = [
        _planned("ready_row", Readiness.READY),
        _planned("delayed_row", Readiness.DELAYED),
        _about("planned-marking-masked", BloatSeverity.INFO, "masked_ready", Readiness.READY),
        _about("planned-marking-stale", BloatSeverity.WARNING, "gone_ready", Readiness.READY),
        _about("planned-marking-masked", BloatSeverity.INFO, "masked_delayed", Readiness.DELAYED),
        _about("event-never-subscribed", BloatSeverity.INFO, "unrelated", None),
    ]
    print_ready_report([("PLANNED_TEST", findings)])
    out = capsys.readouterr().out
    assert "PLANNED_TEST" in out and ": 3 READY" in out  # a colour code sits between them
    for shown in ("ready_row", "masked_ready", "gone_ready"):
        assert shown in out
    for hidden in ("delayed_row", "masked_delayed", "unrelated"):
        assert hidden not in out


def test_summary_counts_ready_aging_apart_from_info(capsys):
    aging = _about("planned-ready-aging", BloatSeverity.INFO, "x", Readiness.READY)
    print_summary([_planned("x", Readiness.READY), aging], ["methods"])
    out = capsys.readouterr().out
    assert f"(1 planned, 1 READY over {detect_bloat.READY_AGING_DAYS} days)" in out
    assert "unverified/info" not in out


def test_ready_and_json_are_mutually_exclusive():
    # --json is the full document (filter on .readiness with jq); --ready is a
    # text-mode filter. One output shape per run.
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--ready", "--json"])
    assert build_parser().parse_args(["--ready", "--check"]).ready_only


# ============================================================================
# DISPATCH KNOWLEDGE — dynamic-dispatch vocabulary collection
# ============================================================================


def dispatch_for(files: dict[str, str]) -> DispatchKnowledge:
    codebase = build_codebase(files)
    dispatch = DispatchKnowledge(codebase)
    dispatch.collect()
    return dispatch


def test_literal_method_kwarg_marks_live():
    dispatch = dispatch_for(
        {
            "adapters/inbound/x_routes.py": (
                "t = RouteSpec(target_status='active', method_name='activate_goal')\n"
                "h = HierarchyRouteFactory(get_children_method='get_steps')\n"
            )
        }
    )
    assert "activate_goal" in dispatch.live
    assert "get_steps" in dispatch.live


def test_query_route_templates_expand_per_domain():
    dispatch = dispatch_for(
        {
            "adapters/inbound/x_routes.py": (
                "cfg = create_activity_domain_route_config(domain_name='tasks')\n"
            )
        }
    )
    for name in ["get_user_tasks", "find_tasks", "get_tasks_for_goal", "get_tasks_for_habit"]:
        assert name in dispatch.live


def test_hyphenated_domain_expands_underscored_variant():
    dispatch = dispatch_for(
        {"adapters/inbound/x_routes.py": ("cfg = DomainRouteConfig(domain_name='path-steps')\n")}
    )
    assert "get_user_path_steps" in dispatch.live


def test_relationship_registry_cross_product():
    dispatch = dispatch_for(
        {
            "core/models/registry.py": (
                "cfg = DomainRelationshipConfig(\n"
                "    entity_label='Task',\n"
                "    outgoing_relationships={'subtasks': spec},\n"
                "    incoming_relationships={'parents': spec},\n"
                ")\n"
            )
        }
    )
    assert "get_task_subtasks" in dispatch.live
    assert "get_task_parents" in dispatch.live


def test_positional_method_arg_marks_live():
    # AIRouteSpec.method_name is field index 4, passed positionally in the
    # route table — the kwarg collector alone misses it.
    dispatch = dispatch_for(
        {
            "adapters/inbound/ai_routes.py": (
                "SPEC = AIRouteSpec('ps', 'Path Steps', 'path-steps', 'similar', "
                "'find_similar_steps', 'uid_limit', 'ps_ai_similar', 'similar_steps')\n"
            )
        }
    )
    assert "find_similar_steps" in dispatch.live


def test_operation_label_strings_are_inert():
    # A method's own error/metrics label is not dispatch evidence: it must
    # not demote the dead-method finding. A genuine dispatch-table string
    # for another name in the same file still registers.
    dispatch = dispatch_for(
        {
            "core/services/x.py": (
                "@track_query_metrics('ps_get_subtasks')\n"
                "@with_error_handling('get_subtasks', error_type='database')\n"
                "async def get_subtasks(self, uid):\n"
                "    return Errors.database(operation='get_subtasks_inner', message='x')\n"
                "DISPATCH = {'real_dispatch_target': None}\n"
            )
        }
    )
    assert "get_subtasks" not in dispatch.string_literals
    assert "ps_get_subtasks" not in dispatch.string_literals
    assert "get_subtasks_inner" not in dispatch.string_literals
    assert "real_dispatch_target" in dispatch.string_literals


def test_string_literal_demotion_index_skips_docstrings():
    dispatch = dispatch_for(
        {
            "core/services/x.py": (
                'DISPATCH = [("dim", "assess_special_method")]\n'
                "def f():\n"
                '    """Docstring mentioning fake_docstring_method."""\n'
                "    return None\n"
            )
        }
    )
    assert "assess_special_method" in dispatch.string_literals
    assert "fake_docstring_method" not in dispatch.string_literals


def test_computed_getattr_is_counted_not_hidden():
    dispatch = dispatch_for(
        {
            "core/services/x.py": (
                "def f(service, method_name):\n"
                "    return getattr(service, method_name)\n"
                "def g(service):\n"
                "    return getattr(service, 'literal_name')\n"
            )
        }
    )
    assert len(dispatch.unanalyzable_getattr) == 1  # literal getattr is vulture's job


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
    # PrerequisitesAnalyzed moved to PLANNED_EVENTS (campaign 18) — add a new
    # sentinel here when the next truly-dead event surfaces.
    _, _, findings = live_analysis
    for event in cast(
        "list[str]",
        [
            # (no WARNING-severity dead events currently — add sentinels as needed)
        ],
    ):
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


def test_live_planned_embedding_events_report_planned(live_analysis):
    # The curriculum/resource embedding events are staged work (subscribers
    # wired in embedding_worker.py, publishers pending) — PLANNED, not dead.
    # When the wiring ships, the stale-marking diagnostic will demand removal
    # from PLANNED_EVENTS; update this sentinel alongside.
    _, _, findings = live_analysis
    for event in sorted(PLANNED_EVENTS):
        finding = finding_for(findings, event)
        assert finding is not None and finding.severity is BloatSeverity.PLANNED, (
            f"{event} should report PLANNED (awaiting wiring)"
        )
    assert not any(f.kind == "planned-marking-stale" for f in findings)


def test_live_collector_self_diagnostic(live_analysis):
    # A scanner finding nothing is more likely broken than the codebase silent.
    _, usage, _ = live_analysis
    assert sum(len(v) for v in usage.published.values()) > 100
    assert sum(len(v) for v in usage.subscribed.values()) > 100
    # Resolution quality bar: at most a handful of irreducible unresolved sites.
    assert len(usage.unresolved_publishes) <= 3
    assert len(usage.unresolved_subscribes) <= 4


# ============================================================================
# METHOD SENTINELS — live codebase ground truth (vulture + dispatch filter)
# ============================================================================


@pytest.fixture(scope="module")
def live_methods():
    codebase = ParsedCodebase(ROOT)
    codebase.load()
    return analyze_methods(codebase, run_vulture(ROOT))


def test_live_properties_and_handlers_never_flagged(live_methods):
    # Each was a FALSE POSITIVE of the old name-regex detector: @cached_property
    # reads and by-reference handler registration are attribute accesses.
    flagged = {f.subject for f in live_methods.findings}
    for name in [
        "entity_label",
        "config_lookup_label",
        "search_fields",
        "category_field",
        "handle_task_completed",
    ]:
        assert name not in flagged, f"{name} must not be flagged"


def test_live_template_dispatched_methods_suppressed_or_absent(live_methods):
    # Names constructed by query_route_factory templates must never surface
    # as findings — either not candidates at all or suppressed with a reason.
    flagged = {f.subject for f in live_methods.findings}
    for name in ["get_user_tasks", "find_tasks", "get_tasks_for_goal"]:
        assert name not in flagged


def test_live_ai_route_spec_methods_suppressed_or_absent(live_methods):
    # Dispatched by name through AIRouteSpec's positional method_name field
    # (adapters/inbound/ai_routes.py) — must never surface as findings.
    flagged = {f.subject for f in live_methods.findings}
    for name in ["find_similar_steps", "generate_step_insight", "find_similar_tasks"]:
        assert name not in flagged, f"{name} is AIRouteSpec-dispatched, must not be flagged"


def test_live_error_label_does_not_shield_dead_method(live_methods):
    # create_instruction_set's only string occurrence is its own
    # @with_error_handling label — a label is not dispatch evidence, so the
    # method is still flagged (PLANNED, because it's in PLANNED_METHODS).
    # (Was get_inference_statistics until campaign 18 moved it to PLANNED.)
    # Delete this sentinel alongside the method when it is removed, or repoint
    # it at another label-only dead/planned method.
    finding = finding_for(live_methods.findings, "create_instruction_set")
    assert finding is not None and finding.severity is BloatSeverity.PLANNED


def test_live_string_table_dispatch_demoted_not_dead(live_methods):
    # _DISPATCH table in self_checkin_routes.py carries this name as a string.
    finding = finding_for(live_methods.findings, "assess_productivity_dual_track")
    if finding is not None:  # absent entirely is also acceptable
        assert finding.severity is BloatSeverity.UNVERIFIED


def test_live_known_dead_facade_method_flagged(live_methods):
    # Hand-verified dead (zero references of any kind outside the definition).
    # Delete this sentinel alongside the method when it is removed, or repoint
    # it at another reference-free dead/planned method.
    # (Was pure_to_dict until campaign 18 deleted it; was list_user_knowledge
    # until the curriculum campaign deleted it.)
    finding = finding_for(live_methods.findings, "get_readiness_score")
    assert finding is not None and finding.severity is BloatSeverity.PLANNED


def test_calendar_edit_surface_fully_unstaged():
    # The act-from arc wired the whole calendar edit surface and PR 6 closed it:
    # record_habit_occurrence (PR 3), reschedule_item (PR 4), and quick_create —
    # deleted as superseded (creation is the day lens's job via TasksService, C6).
    # A PLANNED entry for a wired-or-deleted method is registry rot (the
    # _CALENDAR_EDIT_SURFACE reason string emptied in the same PR).
    assert "core/services/calendar_service.py::reschedule_item" not in detect_bloat.PLANNED_METHODS
    assert "core/services/calendar_service.py::quick_create" not in detect_bloat.PLANNED_METHODS


def test_live_method_self_diagnostic(live_methods):
    # The engine must actually see candidates, and dispatch knowledge must
    # actually collect a vocabulary — zeros mean a broken collector.
    assert live_methods.total_candidates > 100
    assert len(live_methods.dispatch.live) > 100
    assert len(live_methods.dispatch.unanalyzable_getattr) > 0


# ============================================================================
# BLIND-SPOT MEASUREMENT — the detector's own under-reporting, quantified
# ============================================================================


@pytest.fixture(scope="module")
def live_codebase():
    codebase = ParsedCodebase(ROOT)
    codebase.load()
    return codebase


def test_blind_spot_is_measured_from_vultures_own_used_names(live_methods, live_codebase):
    """The caveat must carry a number, and the number must come from the mechanism.

    Vulture treats a method as used when ANY same-named attribute is loaded anywhere, so
    `used_names` is the suppressor and the only correct basis for the figure. Asserted as
    a floor so ordinary refactors don't churn it — the point is that it is substantial and
    computed, never hardcoded.
    """
    invisible, total = measure_vulture_blind_spot(live_codebase, live_methods.vulture_used_names)
    assert total > 1000, f"only {total} production methods seen — collector is broken"
    assert invisible > total // 2, (
        f"only {invisible}/{total} methods sit in the blind spot; if that genuinely "
        "dropped, re-measure and lower the floor deliberately rather than deleting it"
    )


def test_blind_spot_is_scoped_to_the_report_it_annotates():
    """The figure must describe METHOD_SCOPE, not the whole corpus (Codex, PR #876).

    `analyze_methods` discards every candidate outside `core/services/`, so a corpus-wide
    percentage would annotate the method report with a number about a different
    population — adapters/ and ui/ methods it never claims to cover. Measured, the
    distinction is material: 87% corpus-wide vs 94% in scope.
    """
    import ast as _ast
    from pathlib import Path as _Path

    class _Stub:
        root = _Path("/repo")

        def __init__(self, trees):
            self.production = trees

    tree = _ast.parse("class A:\n    def m(self): ...\n")
    in_scope = _Stub({_Path("/repo/core/services/x.py"): tree})
    out_of_scope = _Stub({_Path("/repo/adapters/persistence/y.py"): tree})

    assert measure_vulture_blind_spot(in_scope, frozenset({"m"})) == (1, 1)
    assert measure_vulture_blind_spot(out_of_scope, frozenset({"m"})) == (0, 0), (
        "methods outside core/services/ must not enter the count — the method report "
        "never claims to cover them"
    )


def test_blind_spot_counts_name_loads_not_duplicate_definitions():
    """Regression pin for the wrong proxy this replaced (Codex, PR #876).

    The first cut counted names defined on 2+ classes, which is wrong in BOTH directions:
    a duplicate-defined method whose name is never loaded is still reportable, and a
    uniquely-defined method whose name IS loaded is invisible. Both asserted here, because
    fixing only one would still look green.
    """
    import ast as _ast
    from pathlib import Path as _Path

    class _Stub:
        root = _Path("/repo")

        def __init__(self, trees):
            self.production = trees

    in_scope = _Path("/repo/core/services/x.py")

    # Two classes, same method name — duplicate-defined but NOT name-loaded.
    duplicated = _Stub(
        {
            in_scope: _ast.parse(
                "class A:\n    def dup(self): ...\nclass B:\n    def dup(self): ...\n"
            )
        }
    )
    assert measure_vulture_blind_spot(duplicated, frozenset()) == (0, 2), (
        "duplicate definitions alone must not count — with no attribute load, vulture "
        "can still report both"
    )

    # One class, one method — uniquely defined but the name IS loaded somewhere.
    unique = _Stub({in_scope: _ast.parse("class A:\n    def solo(self): ...\n")})
    assert measure_vulture_blind_spot(unique, frozenset({"solo"})) == (1, 1), (
        "a uniquely-defined method whose name is loaded elsewhere IS invisible and must be counted"
    )
