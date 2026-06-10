#!/usr/bin/env python3
"""
Bloat Detection — AST-sound dead-code analysis for SKUEL semantics.
===================================================================

Finds dead code that generic tools cannot express:

- Event lifecycle: events defined but never published, subscribed but never
  published, published but never subscribed (the publish/subscribe semantics
  live in SKUEL's event bus, not in Python's import graph).
- Service-method liveness (PR 2, pending): Vulture as the liveness engine,
  post-filtered through SKUEL dynamic-dispatch knowledge (route-factory
  templates, relationship-registry method names, dispatch tables).

Design rules (mirrors the SKUEL linter's structural-soundness discipline):

- AST only — no regex over source. Docstring examples are inert for free.
- No cross-file dataflow. An event constructed in one file and published from
  another is reported as UNVERIFIED ("constructed but publication not
  structurally traceable"), never as dead. A tool that lies is worse than none.
- Over-approximation is only allowed in the safe direction: it may suppress a
  dead-code accusation, never create one.
- No silent caps: everything the analysis could not resolve is counted and
  printed in the Limitations section.

Advisory by default (exit 0). ``--check`` exits 1 on surviving WARNING
findings — not wired into quality gates until the manual false-positive audit
passes (see the rewrite plan).

Usage:
    uv run python scripts/detect_bloat.py
    uv run python scripts/detect_bloat.py --events-only
    uv run python scripts/detect_bloat.py --methods-only
    uv run python scripts/detect_bloat.py --verbose --json
"""

import argparse
import ast
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Production code that confers liveness. tests/ is parsed separately and only
# ever contributes annotations ("published in tests"), never liveness.
FIRST_PARTY_ROOTS = ["core", "adapters", "api", "ui", "services_bootstrap", "main.py"]
EXCLUDED_PARTS = {"__pycache__", "archive"}

EVENTS_PACKAGE = ROOT / "core" / "events"
EVENT_ROOT_BASE = "BaseEvent"

# Exemptions require a documented reason (audit_route_security.py convention).
# Exempted findings are still printed, collapsed — never hidden.
EXEMPTED_EVENTS: dict[str, str] = {}


class Colors:
    """Terminal colors for better output readability."""

    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"

    @classmethod
    def disable(cls) -> None:
        """Disable colors (for non-TTY output)."""
        cls.RED = ""
        cls.GREEN = ""
        cls.YELLOW = ""
        cls.BLUE = ""
        cls.CYAN = ""
        cls.BOLD = ""
        cls.DIM = ""
        cls.RESET = ""


class BloatSeverity(Enum):
    """Finding tiers. Only WARNING can ever fail a --check run."""

    WARNING = "warning"  # structurally dead — verified absence of liveness
    UNVERIFIED = "unverified"  # constructed somewhere; publication untraceable
    INFO = "info"  # live but noteworthy (e.g. published, never subscribed)


@dataclass
class Finding:
    """One bloat finding."""

    kind: str  # e.g. "event-never-published"
    severity: BloatSeverity
    subject: str  # e.g. event class name
    file: str
    line: int
    detail: str
    annotations: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "severity": self.severity.value,
            "subject": self.subject,
            "file": self.file,
            "line": self.line,
            "detail": self.detail,
            "annotations": self.annotations,
        }


@dataclass
class Site:
    """A source location."""

    file: str
    line: int

    def __str__(self) -> str:
        return f"{self.file}:{self.line}"


# ============================================================================
# Parsed codebase — every file parsed exactly once, shared by all analyses
# ============================================================================


class ParsedCodebase:
    """File discovery + one-shot ast.parse cache.

    Syntax errors are collected and REPORTED — never silently skipped. A file
    the analysis cannot see is a hole in every liveness claim.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.production: dict[Path, ast.Module] = {}
        self.tests: dict[Path, ast.Module] = {}
        self.syntax_errors: list[str] = []

    def load(self) -> None:
        for path in self._discover(FIRST_PARTY_ROOTS):
            self._parse_into(path, self.production)
        for path in self._discover(["tests"]):
            self._parse_into(path, self.tests)

    def _discover(self, roots: list[str]) -> list[Path]:
        files: list[Path] = []
        for root_name in roots:
            target = self.root / root_name
            if target.is_file() and target.suffix == ".py":
                files.append(target)
            elif target.is_dir():
                for path in sorted(target.rglob("*.py")):
                    if not EXCLUDED_PARTS.intersection(path.parts):
                        files.append(path)
        return files

    def _parse_into(self, path: Path, cache: dict[Path, ast.Module]) -> None:
        try:
            cache[path] = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            self.syntax_errors.append(f"{self.rel(path)}: {exc.msg} (line {exc.lineno})")
        except (OSError, UnicodeDecodeError) as exc:
            self.syntax_errors.append(f"{self.rel(path)}: unreadable ({exc})")

    def rel(self, path: Path) -> str:
        return str(path.relative_to(self.root))


# ============================================================================
# Event universe — transitive inheritance closure from BaseEvent
# ============================================================================


def _base_name(node: ast.expr) -> str | None:
    """Resolve a class base expression to its terminal name."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


class EventUniverse:
    """All event classes in core/events/, closed transitively over BaseEvent.

    Catches indirect subclasses (e.g. TaskEmbeddingRequested(EmbeddingRequested))
    that a direct-base check misses. Builds a descendants map so an intermediate
    base counts as publish-live when any descendant is published.
    """

    def __init__(self, codebase: ParsedCodebase) -> None:
        self.codebase = codebase
        self.classes: dict[str, Site] = {}  # event class -> definition site
        self.descendants: dict[str, set[str]] = defaultdict(set)

    def build(self) -> None:
        bases: dict[str, list[str]] = {}
        sites: dict[str, Site] = {}
        for path, tree in self.codebase.production.items():
            if EVENTS_PACKAGE not in path.parents:
                continue
            rel = self.codebase.rel(path)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    names = [b for b in map(_base_name, node.bases) if b]
                    bases[node.name] = names
                    sites[node.name] = Site(rel, node.lineno)

        # Fixpoint closure from BaseEvent.
        universe = {EVENT_ROOT_BASE}
        changed = True
        while changed:
            changed = False
            for cls, cls_bases in bases.items():
                if cls not in universe and universe.intersection(cls_bases):
                    universe.add(cls)
                    changed = True

        for cls in universe - {EVENT_ROOT_BASE}:
            self.classes[cls] = sites[cls]

        # Direct-child edges -> transitive descendants.
        children: dict[str, set[str]] = defaultdict(set)
        for cls in self.classes:
            for base in bases.get(cls, []):
                if base in self.classes:
                    children[base].add(cls)
        for cls in self.classes:
            stack = list(children[cls])
            while stack:
                child = stack.pop()
                if child not in self.descendants[cls]:
                    self.descendants[cls].add(child)
                    stack.extend(children[child])

    def __contains__(self, name: str) -> bool:
        return name in self.classes

    def registry_size(self) -> int | None:
        """Entry count of EVENT_REGISTRY in core/events/__init__.py (AST, no import).

        Used as a self-diagnostic cross-check; None if the dict moved.
        """
        init_path = EVENTS_PACKAGE / "__init__.py"
        tree = self.codebase.production.get(init_path)
        if tree is None:
            return None
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id == "EVENT_REGISTRY"
                and isinstance(node.value, ast.Dict)
            ):
                return len(node.value.keys)
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
                targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
                if "EVENT_REGISTRY" in targets:
                    return len(node.value.keys)
        return None


# ============================================================================
# Publication / construction / subscription collectors (pure AST)
# ============================================================================


@dataclass
class EventUsage:
    """Aggregated event usage across the production tree (tests kept apart)."""

    published: dict[str, list[Site]] = field(default_factory=lambda: defaultdict(list))
    constructed: dict[str, list[Site]] = field(default_factory=lambda: defaultdict(list))
    subscribed: dict[str, list[Site]] = field(default_factory=lambda: defaultdict(list))
    test_published: dict[str, list[Site]] = field(default_factory=lambda: defaultdict(list))
    test_constructed: dict[str, list[Site]] = field(default_factory=lambda: defaultdict(list))
    unresolved_publishes: list[Site] = field(default_factory=list)
    unresolved_subscribes: list[Site] = field(default_factory=list)


@dataclass(frozen=True)
class PublishWrapper:
    """A function/method that publishes one of its own parameters.

    ``caller_index`` is the event argument's position as seen by callers
    (``self``/``cls`` already stripped); ``param_name`` resolves keyword calls.
    """

    caller_index: int
    param_name: str


class PublishWrapperInference:
    """Infers publish-wrapper functions structurally, to a fixpoint.

    A def whose body publishes one of its OWN parameters (via a primitive
    ``publish_async``/``publish`` or an already-known wrapper) is itself a
    wrapper — e.g. ``publish_event`` (core/events/__init__.py),
    ``group_service._publish_event``, ``BaseAIService._publish_event``.
    Applied globally by name: marking events live is the safe direction.
    Interior publish sites of recognized wrappers (the parameter pass-through)
    are accounted for at call sites and excluded from the unresolved count.
    """

    # Bus methods (Attribute calls only — bare publish()/publish_async() names
    # would be ambiguous) and the canonical helper (Name or Attribute; its
    # signature publish_event(event_bus, event, logger) is the documented
    # contract at core/events/__init__.py).
    PRIMITIVES = {"publish_async": 0, "publish": 0}
    CANONICAL_HELPERS = {"publish_event": 1}

    def __init__(self, codebase: ParsedCodebase) -> None:
        self.codebase = codebase
        self.wrappers: dict[str, set[PublishWrapper]] = defaultdict(set)
        self.interior_sites: set[tuple[str, int]] = set()  # (file, line) to skip

    def infer(self) -> None:
        defs: list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]] = []
        for path, tree in self.codebase.production.items():
            rel = self.codebase.rel(path)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    defs.append((rel, node))

        changed = True
        while changed:
            changed = False
            for rel, fn in defs:
                if self._try_promote(rel, fn):
                    changed = True

    def event_arg_candidates(self, call: ast.Call) -> tuple[list[ast.expr], bool]:
        """(candidate event arguments, is publish-shaped) for a call node.

        A wrapper name can carry several inferred signatures (two different
        ``_publish_event`` defs exist); every signature's argument is a
        candidate and the caller records whichever resolves to an event class.
        """
        name = _base_name(call.func)
        if name in self.PRIMITIVES and isinstance(call.func, ast.Attribute):
            arg = _call_arg(call, self.PRIMITIVES[name], "event")
            return ([arg] if arg is not None else []), True
        if name in self.CANONICAL_HELPERS:
            arg = _call_arg(call, self.CANONICAL_HELPERS[name], "event")
            return ([arg] if arg is not None else []), True
        if name in self.wrappers:
            candidates = []
            for wrapper in sorted(self.wrappers[name], key=lambda w: w.caller_index):
                arg = _call_arg(call, wrapper.caller_index, wrapper.param_name)
                if arg is not None:
                    candidates.append(arg)
            return candidates, True
        return [], False

    def _try_promote(self, rel: str, fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        params = [a.arg for a in fn.args.args]
        promoted = False
        for node in ast.walk(fn):
            if not isinstance(node, ast.Call):
                continue
            candidates, is_publish = self.event_arg_candidates(node)
            if not is_publish:
                continue
            for arg in candidates:
                if not isinstance(arg, ast.Name) or arg.id not in params:
                    continue
                self.interior_sites.add((rel, node.lineno))
                index = params.index(arg.id)
                if params and params[0] in ("self", "cls"):
                    index -= 1
                if index < 0:
                    continue
                wrapper = PublishWrapper(index, arg.id)
                # Dedup on the full (index, param) signature — two defs sharing
                # a name may put the event at different positions.
                if wrapper not in self.wrappers[fn.name]:
                    self.wrappers[fn.name].add(wrapper)
                    promoted = True
        return promoted


def _call_arg(node: ast.Call, position: int, keyword: str) -> ast.expr | None:
    for kw in node.keywords:
        if kw.arg == keyword:
            return kw.value
    if len(node.args) > position:
        return node.args[position]
    return None


class EventUsageCollector:
    """Collects publish / construct / subscribe sites for the event universe.

    Resolution rules (all structural, all file-scoped):
    - Import aliases: ``from core.events.x import TaskCompleted as TC`` makes
      ``TC`` resolve to ``TaskCompleted`` within that file.
    - Variables: ``x = EventClass(...)`` anywhere in a file lets a later
      ``publish_*(x)`` in the same file resolve — over-approximation in the
      safe direction (it can only suppress a dead-event accusation).
    - Publish wrappers: see PublishWrapperInference.
    Cross-FILE event flow is never traced — it surfaces as an unresolved
    publish site plus the UNVERIFIED construction tier.
    """

    def __init__(self, universe: EventUniverse, codebase: ParsedCodebase) -> None:
        self.universe = universe
        self.codebase = codebase
        self.usage = EventUsage()
        self.wrappers = PublishWrapperInference(codebase)

    def collect(self) -> EventUsage:
        self.wrappers.infer()
        for path, tree in self.codebase.production.items():
            self._collect_file(self.codebase.rel(path), tree, is_test=False)
        for path, tree in self.codebase.tests.items():
            self._collect_file(self.codebase.rel(path), tree, is_test=True)
        return self.usage

    # -- per-file ------------------------------------------------------------

    def _collect_file(self, rel: str, tree: ast.Module, is_test: bool) -> None:
        aliases = self._file_alias_map(tree)
        var_events = self._file_event_var_index(tree, aliases)
        var_lists = self._file_event_list_index(tree, aliases)
        in_events_pkg = rel.startswith("core/events/")

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            site = Site(rel, node.lineno)

            # Constructions: EventClass(...) anywhere. Definitions inside
            # core/events/ are the class statements, not constructions, so the
            # package itself still counts (it rarely constructs its own events).
            ctor = self._ctor_class(node, aliases)
            if ctor is not None and not in_events_pkg:
                target = self.usage.test_constructed if is_test else self.usage.constructed
                target[ctor].append(site)

            candidates, is_publish = self.wrappers.event_arg_candidates(node)
            if is_publish:
                if (rel, node.lineno) in self.wrappers.interior_sites:
                    continue  # parameter pass-through, accounted at call sites
                self._record_publish(node, candidates, var_events, aliases, site, is_test)
            elif (
                _base_name(node.func) == "subscribe"
                and isinstance(node.func, ast.Attribute)
                and not is_test
            ):
                self._record_subscribe(node, var_lists, aliases, site)

    # -- name resolution -------------------------------------------------------

    def _file_alias_map(self, tree: ast.Module) -> dict[str, str]:
        """Import-alias -> canonical event class name, for one file."""
        aliases: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.asname and alias.name in self.universe:
                        aliases[alias.asname] = alias.name
        return aliases

    def _resolve(self, name: str | None, aliases: dict[str, str]) -> str | None:
        if name is None:
            return None
        if name in self.universe:
            return name
        return aliases.get(name)

    def _ctor_class(self, node: ast.expr, aliases: dict[str, str]) -> str | None:
        if isinstance(node, ast.Call):
            return self._resolve(_base_name(node.func), aliases)
        return None

    # -- variable indices (file-scoped, safe over-approximation) --------------

    def _file_event_var_index(
        self, tree: ast.Module, aliases: dict[str, str]
    ) -> dict[str, set[str]]:
        """var name -> event classes assigned to it: ``x = EventClass(...)``."""
        index: dict[str, set[str]] = defaultdict(set)
        for node in ast.walk(tree):
            value = None
            targets: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                value, targets = node.value, node.targets
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                value, targets = node.value, [node.target]
            if value is None:
                continue
            cls = self._ctor_class(value, aliases)
            if cls is None:
                continue
            for target in targets:
                if isinstance(target, ast.Name):
                    index[target.id].add(cls)
        return index

    def _file_event_list_index(
        self, tree: ast.Module, aliases: dict[str, str]
    ) -> dict[str, set[str]]:
        """var name -> event classes, for subscribe-loop resolution.

        Covers ``events = [TaskCreated, ...]`` and ``for ev in events:`` /
        ``for ev in [TaskCreated, ...]:`` (services_bootstrap/_event_wiring.py).
        """
        index: dict[str, set[str]] = defaultdict(set)
        list_vars: dict[str, set[str]] = defaultdict(set)

        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.List):
                classes = self._event_names_in_list(node.value, aliases)
                if classes:
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            list_vars[target.id].update(classes)

        for node in ast.walk(tree):
            if not isinstance(node, (ast.For, ast.AsyncFor)):
                continue
            if not isinstance(node.target, ast.Name):
                continue
            loop_classes: set[str] = set()
            if isinstance(node.iter, ast.List):
                loop_classes = self._event_names_in_list(node.iter, aliases)
            elif isinstance(node.iter, ast.Name):
                loop_classes = list_vars.get(node.iter.id, set())
            if loop_classes:
                index[node.target.id].update(loop_classes)

        return index

    def _event_names_in_list(self, node: ast.List, aliases: dict[str, str]) -> set[str]:
        resolved = (
            self._resolve(elt.id, aliases) for elt in node.elts if isinstance(elt, ast.Name)
        )
        return {name for name in resolved if name is not None}

    # -- recording -----------------------------------------------------------

    def _record_publish(
        self,
        call: ast.Call,
        candidates: list[ast.expr],
        var_events: dict[str, set[str]],
        aliases: dict[str, str],
        site: Site,
        is_test: bool,
    ) -> None:
        published = self.usage.test_published if is_test else self.usage.published
        # Bare .publish() exists on non-event objects; only its resolvable
        # calls count, and it never lands in the unresolved tally (noise).
        is_bare_publish = _base_name(call.func) == "publish"
        for arg in candidates:
            ctor = self._ctor_class(arg, aliases)
            if ctor is not None:
                published[ctor].append(site)
                return
            if isinstance(arg, ast.Name):
                classes = set(var_events.get(arg.id, set()))
                direct = self._resolve(arg.id, aliases)
                if direct is not None:
                    classes.add(direct)
                if classes:
                    for cls in classes:
                        published[cls].append(site)
                    return
        if not is_test and not is_bare_publish:
            self.usage.unresolved_publishes.append(site)

    def _record_subscribe(
        self,
        node: ast.Call,
        var_lists: dict[str, set[str]],
        aliases: dict[str, str],
        site: Site,
    ) -> None:
        arg = _call_arg(node, position=0, keyword="event_type")
        if isinstance(arg, ast.Name):
            resolved = self._resolve(arg.id, aliases)
            if resolved is not None:
                self.usage.subscribed[resolved].append(site)
                return
            if arg.id in var_lists:
                for cls in var_lists[arg.id]:
                    self.usage.subscribed[cls].append(site)
                return
        self.usage.unresolved_subscribes.append(site)


# ============================================================================
# Event findings assembly
# ============================================================================


def analyze_events(
    universe: EventUniverse, usage: EventUsage
) -> tuple[list[Finding], list[Finding]]:
    """Build (findings, exempted) for the event universe.

    Liveness rule: an event is publish-live iff it OR any descendant has a
    resolved publish site (an intermediate base is not dead while its children
    fly). Tier order: live -> UNVERIFIED (constructed in production, flow not
    traceable) -> WARNING (structurally dead).
    """
    findings: list[Finding] = []
    exempted: list[Finding] = []

    for cls, site in sorted(universe.classes.items()):
        family = {cls} | universe.descendants[cls]
        publish_live = any(usage.published.get(member) for member in family)
        subscribed = usage.subscribed.get(cls, [])

        if publish_live:
            if not subscribed and not universe.descendants[cls]:
                findings.append(
                    Finding(
                        kind="event-never-subscribed",
                        severity=BloatSeverity.INFO,
                        subject=cls,
                        file=site.file,
                        line=site.line,
                        detail="published but no subscriber — fine if fire-and-forget",
                    )
                )
            continue

        constructed = [s for member in family for s in usage.constructed.get(member, [])]
        annotations = []
        if subscribed:
            annotations.append(
                f"has subscribers ({', '.join(str(s) for s in subscribed[:3])}) — dead wiring chain"
            )
        test_sites = [
            s
            for member in family
            for s in usage.test_published.get(member, []) + usage.test_constructed.get(member, [])
        ]
        if test_sites:
            annotations.append(f"referenced in tests ({len(test_sites)} sites)")

        if constructed:
            finding = Finding(
                kind="event-publication-untraced",
                severity=BloatSeverity.UNVERIFIED,
                subject=cls,
                file=site.file,
                line=site.line,
                detail=(
                    f"constructed at {constructed[0]} but publication not "
                    "structurally traceable — verify manually"
                ),
                annotations=annotations,
            )
        else:
            finding = Finding(
                kind="event-never-published",
                severity=BloatSeverity.WARNING,
                subject=cls,
                file=site.file,
                line=site.line,
                detail="defined but never published nor constructed in production code",
                annotations=annotations,
            )

        if cls in EXEMPTED_EVENTS:
            finding.annotations.append(f"exempted: {EXEMPTED_EVENTS[cls]}")
            exempted.append(finding)
        else:
            findings.append(finding)

    return findings, exempted


# ============================================================================
# Reporting
# ============================================================================


def _print_finding(finding: Finding) -> None:
    mark = {
        BloatSeverity.WARNING: f"{Colors.RED}✗{Colors.RESET}",
        BloatSeverity.UNVERIFIED: f"{Colors.YELLOW}?{Colors.RESET}",
        BloatSeverity.INFO: f"{Colors.CYAN}i{Colors.RESET}",
    }[finding.severity]
    print(f"  {mark} {Colors.BOLD}{finding.subject}{Colors.RESET}  ({finding.file}:{finding.line})")
    print(f"      {finding.detail}")
    for note in finding.annotations:
        print(f"      {Colors.YELLOW}⚠ {note}{Colors.RESET}")


def print_event_report(
    universe: EventUniverse,
    usage: EventUsage,
    findings: list[Finding],
    exempted: list[Finding],
    verbose: bool,
) -> None:
    print(f"\n{Colors.BOLD}🔔 Events Analysis{Colors.RESET}")
    registry = universe.registry_size()
    registry_note = f" (EVENT_REGISTRY lists {registry})" if registry is not None else ""
    print(
        f"  Event universe (transitive BaseEvent subclasses): {len(universe.classes)}{registry_note}"
    )
    resolved_pubs = sum(len(v) for v in usage.published.values())
    resolved_subs = sum(len(v) for v in usage.subscribed.values())
    print(
        f"  Resolved publish sites: {resolved_pubs}  (unresolved: {len(usage.unresolved_publishes)})"
    )
    print(
        f"  Resolved subscriptions: {resolved_subs}  (unresolved: {len(usage.unresolved_subscribes)})"
    )

    # Self-diagnostic: a scanner finding nothing is more likely broken than
    # the codebase being silent (fail-fast applied to the tool itself).
    if resolved_pubs == 0 or resolved_subs == 0:
        print(
            f"\n{Colors.RED}{Colors.BOLD}🚨 SELF-DIAGNOSTIC: zero resolved "
            f"{'publish sites' if resolved_pubs == 0 else 'subscriptions'} — "
            f"the collector is almost certainly broken. Do not trust this report.{Colors.RESET}"
        )

    by_severity: dict[BloatSeverity, list[Finding]] = defaultdict(list)
    for finding in findings:
        by_severity[finding.severity].append(finding)

    for severity, title in [
        (BloatSeverity.WARNING, "Structurally dead events"),
        (BloatSeverity.UNVERIFIED, "Constructed but publication untraced — verify manually"),
        (BloatSeverity.INFO, "Published but never subscribed (may be intentional)"),
    ]:
        items = by_severity.get(severity, [])
        if not items:
            continue
        print(f"\n{Colors.YELLOW}{title} ({len(items)}):{Colors.RESET}\n")
        for finding in items:
            _print_finding(finding)

    if not findings:
        print(f"\n  {Colors.GREEN}✓ No event findings.{Colors.RESET}")

    if exempted:
        print(
            f"\n  {Colors.DIM}exempted ({len(exempted)}): "
            f"{', '.join(f.subject for f in exempted)}{Colors.RESET}"
        )

    if verbose and usage.unresolved_publishes:
        print(f"\n{Colors.DIM}Unresolved publish sites:{Colors.RESET}")
        for site in usage.unresolved_publishes:
            print(f"  {Colors.DIM}{site}{Colors.RESET}")
    if verbose and usage.unresolved_subscribes:
        print(f"\n{Colors.DIM}Unresolved subscription sites:{Colors.RESET}")
        for site in usage.unresolved_subscribes:
            print(f"  {Colors.DIM}{site}{Colors.RESET}")


def print_limitations(codebase: ParsedCodebase, usage: EventUsage | None) -> None:
    print(f"\n{Colors.BOLD}📏 Limitations (read before acting on findings){Colors.RESET}")
    if usage is not None:
        print(
            f"  - {len(usage.unresolved_publishes)} publish and "
            f"{len(usage.unresolved_subscribes)} subscribe sites could not be "
            "resolved to an event class (run --verbose for locations)."
        )
        print(
            "  - No cross-file dataflow by design: events that travel between "
            "files before publication land in the UNVERIFIED tier, not WARNING."
        )
    if codebase.syntax_errors:
        print(
            f"  - {Colors.RED}{len(codebase.syntax_errors)} files failed to parse "
            f"— their usage is INVISIBLE to this report:{Colors.RESET}"
        )
        for err in codebase.syntax_errors:
            print(f"      {err}")


# ============================================================================
# CLI
# ============================================================================


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect unused code in SKUEL (AST-sound)")
    parser.add_argument("--events-only", action="store_true", help="Check events only")
    parser.add_argument("--methods-only", action="store_true", help="Check methods only")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if WARNING findings survive (advisory otherwise)",
    )
    parser.add_argument("--json", action="store_true", dest="as_json", help="Emit findings as JSON")
    args = parser.parse_args()

    if not sys.stdout.isatty():
        Colors.disable()

    check_events = not args.methods_only
    check_methods = not args.events_only

    # With --json, stdout carries ONLY the findings document.
    progress_out = sys.stderr if args.as_json else sys.stdout

    if check_methods:
        print(
            f"{Colors.YELLOW}Method analysis: not yet implemented in the rewrite "
            f"(lands in PR 2 — Vulture engine + dispatch-knowledge filter).{Colors.RESET}",
            file=progress_out,
        )
        if not check_events:
            return 0

    print(f"{Colors.CYAN}🔍 Parsing codebase...{Colors.RESET}", file=progress_out)
    codebase = ParsedCodebase(ROOT)
    codebase.load()
    print(
        f"  {len(codebase.production)} production files, "
        f"{len(codebase.tests)} test files parsed"
        + (
            f", {Colors.RED}{len(codebase.syntax_errors)} unparseable{Colors.RESET}"
            if codebase.syntax_errors
            else ""
        ),
        file=progress_out,
    )

    findings: list[Finding] = []
    usage: EventUsage | None = None

    if check_events:
        universe = EventUniverse(codebase)
        universe.build()
        usage = EventUsageCollector(universe, codebase).collect()
        event_findings, exempted = analyze_events(universe, usage)
        findings.extend(event_findings)
        if args.as_json:
            print(json.dumps([f.to_json() for f in event_findings], indent=2))
        else:
            print_event_report(universe, usage, event_findings, exempted, args.verbose)

    if not args.as_json:
        print_limitations(codebase, usage)
        warnings = [f for f in findings if f.severity is BloatSeverity.WARNING]
        print(f"\n{Colors.BOLD}{'=' * 78}{Colors.RESET}")
        if warnings:
            print(
                f"{Colors.YELLOW}{len(warnings)} structurally-dead findings "
                f"(+{len(findings) - len(warnings)} unverified/info). "
                f"Verify before deleting.{Colors.RESET}"
            )
        else:
            print(f"{Colors.GREEN}✅ No structurally-dead findings.{Colors.RESET}")

    if args.check:
        return 1 if any(f.severity is BloatSeverity.WARNING for f in findings) else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
