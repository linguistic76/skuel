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
    ParsedCodebase,
    VultureScan,
    analyze_events,
    analyze_methods,
    measure_vulture_blind_spot,
    run_vulture,
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
# PLANNED TIER — unwired by intent is not bloat
# ============================================================================


def test_planned_event_reports_planned_not_dead(monkeypatch):
    # setattr replaces the registry wholesale — the production entries (real
    # embedding events) are absent from synthetic universes and would
    # otherwise fire the vanished-key stale check.
    monkeypatch.setattr(
        detect_bloat, "PLANNED_EVENTS", {"GammaOrphan": "awaiting synthetic wiring"}
    )
    _, _, findings = analyze({})
    finding = finding_for(findings, "GammaOrphan")
    assert finding is not None
    assert finding.severity is BloatSeverity.PLANNED
    assert finding.kind == "event-awaiting-wiring"
    assert "awaiting synthetic wiring" in finding.detail


def test_planned_event_subscriber_is_staging_not_dead_chain(monkeypatch):
    monkeypatch.setattr(
        detect_bloat, "PLANNED_EVENTS", {"GammaOrphan": "awaiting synthetic wiring"}
    )
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


def test_stale_planned_event_marking_is_reported(monkeypatch):
    monkeypatch.setattr(
        detect_bloat, "PLANNED_EVENTS", {"GammaOrphan": "awaiting synthetic wiring"}
    )
    _, _, findings = analyze(
        {
            "core/services/x.py": (
                "async def f(self):\n"
                "    await publish_event(self.event_bus, GammaOrphan(uid='1'), self.logger)\n"
            )
        }
    )
    stale = [f for f in findings if f.kind == "planned-marking-stale"]
    assert [f.subject for f in stale] == ["GammaOrphan"]
    assert stale[0].severity is BloatSeverity.INFO


def test_vanished_planned_event_marking_is_reported(monkeypatch):
    # A PLANNED_EVENTS key whose class was deleted/renamed/mistyped is not in
    # the universe — the stale check must still fire (Codex P2, PR #274).
    monkeypatch.setattr(
        detect_bloat, "PLANNED_EVENTS", {"NoSuchEventAnywhere": "awaiting synthetic wiring"}
    )
    _, _, findings = analyze({})
    stale = [f for f in findings if f.kind == "planned-marking-stale"]
    assert [f.subject for f in stale] == ["NoSuchEventAnywhere"]
    assert stale[0].severity is BloatSeverity.INFO
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
        {"core/services/x.py::future_method": "awaiting synthetic wiring"},
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


def test_stale_planned_method_marking_is_reported(monkeypatch):
    monkeypatch.setattr(
        detect_bloat,
        "PLANNED_METHODS",
        {"core/services/x.py::now_live_method": "awaiting synthetic wiring"},
    )
    codebase = build_codebase({})
    # not a vulture candidate -> live or deleted
    analysis = analyze_methods(codebase, VultureScan([], frozenset()))
    stale = [f for f in analysis.findings if f.kind == "planned-marking-stale"]
    assert [f.subject for f in stale] == ["now_live_method"]
    assert stale[0].severity is BloatSeverity.INFO


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
                "t = StatusTransition(target_status='active', method_name='activate_goal')\n"
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


def test_status_factory_transitions_expand():
    dispatch = dispatch_for(
        {
            "adapters/inbound/x_routes.py": (
                "f = StatusRouteFactory(\n"
                "    domain_singular='goal',\n"
                "    transitions={'activate': t1, 'pause': t2},\n"
                ")\n"
            )
        }
    )
    assert "activate_goal" in dispatch.live
    assert "pause_goal" in dispatch.live


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
