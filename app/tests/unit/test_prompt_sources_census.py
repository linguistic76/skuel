"""Every LLM call in ``core/`` names where the words it sends come from.

The census walks ``core/`` for calls to the LLM port methods, and each call site
is a row in ``CENSUS``: ``{(file, function): Source}``. A new call site fails
until someone names its source, and a row whose site is gone fails as stale.

**Detection is by method name.** The port methods are derived from the port
classes (``PORT_CLASSES``), so a new port method is detected with no edit here.
Today every call in ``core/`` to one of those names is an LLM call; a same-named
method on something else would go in ``NOT_LLM`` with what it is. A port method
named without being called (a bound-method alias, a ``getattr``, a bare-name
call) can't be followed, so it fails as a problem. ``tests/fixtures/
llm_call_census_control.py`` is the control: it calls each port method once, in
the receiver shapes ``core/`` uses, and the detector must find every call.

**Each row is traced.** The tracer slices a call's word arguments (everything but
``model``, ``temperature`` and ``max_tokens``) backwards: through local bindings,
list appends, the returns of the functions it calls (same class, same module, an
imported function, or ``self.<attr>.<method>`` typed by the class's
``__init__``), and a parameter back to its callers in the same module. A row
passes when the slice reaches its source's mark:

- ``REGISTRY``: a ``PROMPT_REGISTRY.render`` / ``.get`` call.
- ``INSTRUCTION_FILE``: a function of the journal instruction loader.
- ``AUTHORED_CURRICULUM``: an exercise's ``get_feedback_prompt``.
- ``REQUEST``: a parameter whose callers are outside its module (the route).
- ``FORWARDED``: inside a port method, its own parameters.

The slice is a may-analysis: it shows that the source is one place the words come
from, not that it is the only one. One thing it does refuse at every row: a word
argument that is literal text alone has no source to name.

**Two doors assemble their own words**, so a call to one chooses none and has no
row: ``_generate_insight`` renders the template its ``AIPromptId`` names
(``test_ai_prompt_templates.py`` holds each id to its template), and
``generate_context_aware_answer`` renders the Askesis stance and guidelines. The
LLM call inside each door is a row like any other.

Labels on assembled content (the journal's "Please process this as Stage 2 —
Thought Partner.", ``_generate_insight``'s ``Context:`` prefix) are code, not
prompts, and need no row: the census lists LLM call sites, not lines of text.

Problems are collected into lists that one test each asserts empty, so a scan
that can't read a site fails a test instead of the collection of the session.
"""

from __future__ import annotations

import ast
import inspect
import tokenize
import typing
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import pytest

from core.models.exercises.exercise import Exercise
from core.ports.llm_protocols import ChatCompletionPort, ToolSelectionPort
from core.services.askesis.query_tools import ToolSelector
from core.services.base_ai_service import AIPromptId
from core.services.llm_caller import LLMCallerProtocol, UnifiedLLMCaller
from core.services.llm_service import LLMService

APP = Path(__file__).resolve().parents[2]
CONTROL = APP / "tests" / "fixtures" / "llm_call_census_control.py"


class Source(Enum):
    """Where an LLM call's words come from."""

    REGISTRY = "a committed template in core/prompts/templates/, founder-overridable (ADR-082 D1)"
    INSTRUCTION_FILE = (
        "the journal instruction loader: data/instructions/ over committed floors (ADR-081)"
    )
    AUTHORED_CURRICULUM = "the exercise's vault-authored feedback prompt (ADR-091)"
    REQUEST = "the request's own instructions: typed by the user, or an instruction file they name"
    FORWARDED = "a port method passing its caller's words on (the caller's site is a row)"


#: The LLM ports. Their public coroutines are the port methods the census detects.
PORT_CLASSES: tuple[type, ...] = (
    LLMService,
    LLMCallerProtocol,
    ChatCompletionPort,
    ToolSelectionPort,
    ToolSelector,
)

#: The ports implemented in ``core/``: their methods forward their callers' words.
FORWARDING_CLASSES = frozenset({LLMService.__name__, UnifiedLLMCaller.__name__})

#: The doors that assemble their own words: a call to one chooses none.
DOORS = frozenset({"_generate_insight", "generate_context_aware_answer"})

#: Parameters of a port method that carry no words.
NOT_WORDS = frozenset({"model", "temperature", "max_tokens"})

#: Calls in ``core/`` to a port method's name on something that is not an LLM
#: port, as ``{(file, function, method): what the receiver is}``. Empty today.
NOT_LLM: dict[tuple[str, str, str], str] = {}

CENSUS: dict[tuple[str, str], Source] = {
    # The ports, forwarding their callers' words.
    ("core/services/llm_service.py", "LLMService.generate"): Source.FORWARDED,
    ("core/services/llm_service.py", "LLMService.select_tool"): Source.FORWARDED,
    ("core/services/llm_caller.py", "UnifiedLLMCaller.generate"): Source.FORWARDED,
    ("core/services/llm_caller.py", "UnifiedLLMCaller.complete"): Source.FORWARDED,
    ("core/services/llm_caller.py", "UnifiedLLMCaller.select_tool"): Source.FORWARDED,
    # Inside the two doors.
    ("core/services/base_ai_service.py", "BaseAIService._generate_insight"): Source.REGISTRY,
    # askesis_stance + askesis_response_guidelines
    ("core/services/llm_service.py", "LLMService.generate_context_aware_answer"): Source.REGISTRY,
    # Askesis. The guided system prompt is askesis_stance + an askesis_guided_* leaf; the
    # user turn is askesis_curriculum_reference when the bundle carries curriculum.
    (
        "core/services/askesis/query_processor.py",
        "QueryProcessor._generate_guided_answer",
    ): Source.REGISTRY,
    # askesis_tool_selection; the tool specs come from the typed build_aggregation_catalog.
    ("core/services/askesis/query_tools.py", "select_and_run"): Source.REGISTRY,
    # dsl_domain_recognition(_compact) + dsl_domain_recognition_system
    ("core/services/dsl/llm_dsl_bridge.py", "LLMDSLBridgeService._call_llm"): Source.REGISTRY,
    # transcript_formatting inside transcript_editing (+ transcript_editing_context)
    (
        "core/services/content_enrichment_service.py",
        "ContentEnrichmentService._apply_intelligent_editing",
    ): Source.REGISTRY,
    (
        "core/services/entry_grounding_service.py",
        "EntryGroundingService._judge_entry",
    ): Source.REGISTRY,
    (
        "core/services/prereq_suggestion_service.py",
        "PrereqSuggestionService._judge_batch",
    ): Source.REGISTRY,
    (
        "core/services/lifepath/lifepath_vision_service.py",
        "LifePathVisionService._extract_themes_with_llm",
    ): Source.REGISTRY,
    (
        "core/services/report/entry_report_service.py",
        "EntryReportService.generate_entry_response",
    ): Source.REGISTRY,
    (
        "core/services/report/entry_report_service.py",
        "EntryReportService.generate_report",
    ): Source.AUTHORED_CURRICULUM,
    (
        "core/services/report/progress_report_generator.py",
        "ProgressReportGenerator._generate_llm_report",
    ): Source.REGISTRY,
    # InstructionResolver renders a journal_* template; a user's custom instructions replace it.
    (
        "core/services/user_entry/user_entry_processing_service.py",
        "UserEntryProcessingService._generate",
    ): Source.REGISTRY,
    (
        "core/services/journal/journal_service.py",
        "JournalService.run_stage1",
    ): Source.INSTRUCTION_FILE,
    (
        "core/services/journal/journal_service.py",
        "JournalService.run_stage2",
    ): Source.INSTRUCTION_FILE,
    (
        "core/services/journal/journal_service.py",
        "JournalService.run_stage3",
    ): Source.INSTRUCTION_FILE,
    (
        "core/services/journal/journal_service.py",
        "JournalService.run_discussion",
    ): Source.INSTRUCTION_FILE,
    (
        "core/services/journal/journal_service.py",
        "JournalService.run_follow_up",
    ): Source.INSTRUCTION_FILE,
    # The run's instructions (typed in the form, or a data/instructions/ file named there),
    # with the je_raw/je_pro exemplars.
    (
        "core/services/journal/journal_batch_service.py",
        "JournalBatchService._call_llm_with_instructions",
    ): Source.REQUEST,
}

INSTRUCTION_LOADER = "core/services/journal/instruction_loader.py"
REGISTRY_MARKS = frozenset(
    {"core.prompts.PROMPT_REGISTRY.render", "core.prompts.PROMPT_REGISTRY.get"}
)
FEEDBACK_PROMPT = "get_feedback_prompt"
MAX_DEPTH = 8


def _port_methods() -> frozenset[str]:
    methods = {
        name
        for port in PORT_CLASSES
        for name, member in vars(port).items()
        if not name.startswith("_") and inspect.iscoroutinefunction(member)
    }
    return frozenset(methods | {"_generate_insight"})


PORT_METHODS = _port_methods()


# ============================================================================
# Detection
# ============================================================================


@dataclass(frozen=True)
class CallSite:
    path: str
    function: str
    method: str
    line: int
    call: ast.Call


def _rel(path: Path) -> str:
    return path.resolve().relative_to(APP).as_posix()


def _defs(tree: ast.Module) -> Iterator[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
    """Every function in a module with its qualified name (``Class.method.inner``)."""

    def walk(
        node: ast.AST, prefix: str
    ) -> Iterator[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualname = f"{prefix}{child.name}"
                yield qualname, child
                yield from walk(child, f"{qualname}.")
            elif isinstance(child, ast.ClassDef):
                yield from walk(child, f"{prefix}{child.name}.")
            else:
                yield from walk(child, prefix)

    yield from walk(tree, "")


def _own_nodes(fn: ast.AST) -> Iterator[ast.AST]:
    """The nodes of a function body, not descending into nested functions."""
    stack = list(ast.iter_child_nodes(fn))
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            stack.extend(ast.iter_child_nodes(node))


def _owners(tree: ast.Module) -> dict[int, str]:
    """``id(node)`` -> the qualified name of the function (or class body) it sits in."""
    owners: dict[int, str] = {}

    def walk(node: ast.AST, owner: str, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            owners[id(child)] = owner
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualname = f"{prefix}{child.name}"
                walk(child, qualname, f"{qualname}.")
            elif isinstance(child, ast.ClassDef):
                walk(child, f"{prefix}{child.name}", f"{prefix}{child.name}.")
            else:
                walk(child, owner, prefix)

    walk(tree, "<module>", "")
    return owners


def detect(source: str, rel: str) -> tuple[list[CallSite], list[str]]:
    """The port-method calls in one module, and the port-method uses it can't follow."""
    tree = ast.parse(source)
    owners = _owners(tree)
    sites: list[CallSite] = []
    problems: list[str] = []
    called: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in PORT_METHODS:
            called.add(id(func))
            sites.append(CallSite(rel, owners[id(node)], func.attr, node.lineno, node))
        elif isinstance(func, ast.Name) and func.id in PORT_METHODS:
            problems.append(f"{rel}:{node.lineno} calls {func.id}() by bare name")
        elif (
            isinstance(func, ast.Name)
            and func.id == "getattr"
            and len(node.args) > 1
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value in PORT_METHODS
        ):
            problems.append(f"{rel}:{node.lineno} reaches {node.args[1].value} through getattr")
    problems.extend(
        f"{rel}:{node.lineno} names {node.attr} without calling it"
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and node.attr in PORT_METHODS
        and isinstance(node.ctx, ast.Load)
        and id(node) not in called
    )
    return sites, problems


def _scan_core() -> tuple[list[CallSite], list[str]]:
    sites: list[CallSite] = []
    problems: list[str] = []
    for path in sorted((APP / "core").rglob("*.py")):
        try:
            found, unfollowable = detect(path.read_text(encoding="utf-8"), _rel(path))
        except SyntaxError as exc:
            problems.append(f"{_rel(path)}: unreadable ({exc})")
            continue
        sites.extend(found)
        problems.extend(unfollowable)
    return sites, problems


# ============================================================================
# Tracing
# ============================================================================


@dataclass
class Module:
    path: str
    tree: ast.Module
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef]
    imports: dict[str, str]  # local name -> dotted origin

    @classmethod
    def load(cls, path: Path) -> Module:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    imports[alias.asname or alias.name] = f"{node.module}.{alias.name}"
        return cls(_rel(path), tree, dict(_defs(tree)), imports)


@dataclass(frozen=True)
class Reached:
    """A call the slice reached: its spelling, imports resolved, and the function it runs."""

    dotted: str  # the leading name replaced by what it was imported as: core.prompts.PROMPT_REGISTRY.render
    resolved: tuple[str, str] | None  # (file, qualname)


@dataclass
class Trace:
    calls: set[Reached] = field(default_factory=set)
    params: set[tuple[str, str, str]] = field(default_factory=set)  # (file, function, param)
    open_params: set[tuple[str, str, str]] = field(default_factory=set)
    text: list[str] = field(default_factory=list)  # string constants seen
    values: int = 0  # leaves that are not string constants


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}"
    if isinstance(node, ast.Call):
        return f"{_dotted(node.func)}()"
    return type(node).__name__


def _params(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    args = fn.args
    return [a.arg for a in [*args.posonlyargs, *args.args, *args.kwonlyargs]] + [
        a.arg for a in (args.vararg, args.kwarg) if a is not None
    ]


def _annotation_class(annotation: ast.expr | None) -> str | None:
    """``Foo`` from ``Foo``, ``Foo | None``, ``"Foo"``."""
    if annotation is None:
        return None
    if isinstance(annotation, ast.Name):
        return annotation.id
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        return annotation.value.split("|")[0].strip() or None
    if isinstance(annotation, ast.BinOp):
        return _annotation_class(annotation.left) or _annotation_class(annotation.right)
    return None


class Tracer:
    def __init__(self) -> None:
        self._modules: dict[str, Module] = {}

    def module(self, rel: str) -> Module:
        if rel not in self._modules:
            self._modules[rel] = Module.load(APP / rel)
        return self._modules[rel]

    def _module_for(self, dotted_module: str) -> Module | None:
        path = APP / Path(*dotted_module.split("."))
        for candidate in (path.with_suffix(".py"), path / "__init__.py"):
            if candidate.is_file():
                return self.module(_rel(candidate))
        return None

    # ---- resolution -------------------------------------------------------

    def _imported(self, module: Module, name: str, hops: int = 0) -> tuple[Module, str] | None:
        origin = module.imports.get(name)
        if origin is None or not origin.startswith("core."):
            return None
        target_module, _, target = origin.rpartition(".")
        target_mod = self._module_for(target_module)
        if target_mod is None:
            return None
        if target in target_mod.functions or any(
            isinstance(n, ast.ClassDef) and n.name == target for n in target_mod.tree.body
        ):
            return target_mod, target
        return self._imported(target_mod, target, hops + 1) if hops < 4 else None  # a re-export

    def _attr_class(self, module: Module, cls: str, attr: str) -> tuple[Module, str] | None:
        """The class of ``self.<attr>`` in ``cls``, from ``__init__`` or a class annotation."""
        init = module.functions.get(f"{cls}.__init__")
        annotation: ast.expr | None = None
        if init is not None:
            annotations = {a.arg: a.annotation for a in [*init.args.args, *init.args.kwonlyargs]}
            for node in _own_nodes(init):
                if isinstance(node, ast.AnnAssign) and _dotted(node.target) == f"self.{attr}":
                    annotation = node.annotation
                elif (
                    isinstance(node, ast.Assign)
                    and any(_dotted(t) == f"self.{attr}" for t in node.targets)
                    and isinstance(node.value, ast.Name)
                ):
                    annotation = annotation or annotations.get(node.value.id)
        name = _annotation_class(annotation)
        if name is None:
            return None
        if any(isinstance(n, ast.ClassDef) and n.name == name for n in module.tree.body):
            return module, name
        return self._imported(module, name)

    def resolve(self, module: Module, qualname: str, func: ast.expr) -> tuple[Module, str] | None:
        cls = qualname.split(".")[0] if "." in qualname else None
        if isinstance(func, ast.Name):
            if func.id in module.functions:
                return module, func.id
            return self._imported(module, func.id)
        if not isinstance(func, ast.Attribute):
            return None
        base = func.value
        if isinstance(base, ast.Name) and base.id in ("self", "cls") and cls:
            if f"{cls}.{func.attr}" in module.functions:
                return module, f"{cls}.{func.attr}"
            return None
        if (
            isinstance(base, ast.Attribute)
            and isinstance(base.value, ast.Name)
            and base.value.id == "self"
            and cls
        ):
            owner = self._attr_class(module, cls, base.attr)
            if owner is not None:
                owner_module, owner_cls = owner
                if f"{owner_cls}.{func.attr}" in owner_module.functions:
                    return owner_module, f"{owner_cls}.{func.attr}"
        return None

    # ---- slicing ----------------------------------------------------------

    def trace(self, site: CallSite, *, follow_callers: bool) -> Trace:
        out = Trace()
        module = self.module(site.path)
        seen: set[tuple[str, str, str]] = set()
        for arg in self.word_arguments(site.call):
            self._expr(arg, module, site.function, out, seen, 0, follow_callers)
        return out

    @staticmethod
    def word_arguments(call: ast.Call) -> list[ast.expr]:
        return [*call.args, *(k.value for k in call.keywords if k.arg not in NOT_WORDS)]

    def _expr(
        self,
        expr: ast.AST,
        module: Module,
        qualname: str,
        out: Trace,
        seen: set[tuple[str, str, str]],
        depth: int,
        follow: bool,
    ) -> None:
        stack = [expr]
        while stack:
            node = stack.pop()
            if isinstance(node, ast.Call):
                self._call(node, module, qualname, out, seen, depth, follow)
                func = node.func
                if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Constant):
                    stack.append(func.value)  # "sep".join(...), "...".format(...): text
                else:
                    out.values += 1  # a call's result is a value
                    stack.append(func)
                stack.extend(node.args)
                stack.extend(keyword.value for keyword in node.keywords)
                continue
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                self._name(node.id, module, qualname, out, seen, depth, follow)
                continue
            if isinstance(node, ast.Constant):
                if isinstance(node.value, str):
                    out.text.append(node.value)
                else:
                    out.values += 1
            elif isinstance(node, (ast.Attribute, ast.Subscript)):
                out.values += 1
            stack.extend(ast.iter_child_nodes(node))

    def _call(
        self,
        call: ast.Call,
        module: Module,
        qualname: str,
        out: Trace,
        seen: set[tuple[str, str, str]],
        depth: int,
        follow: bool,
    ) -> None:
        target = self.resolve(module, qualname, call.func)
        head, _, rest = _dotted(call.func).partition(".")
        dotted = (
            f"{module.imports.get(head, head)}.{rest}" if rest else module.imports.get(head, head)
        )
        out.calls.add(Reached(dotted, (target[0].path, target[1]) if target else None))
        if target is None or depth >= MAX_DEPTH:
            return
        target_module, target_name = target
        fn = target_module.functions.get(target_name)
        if fn is None:
            return
        for node in _own_nodes(fn):
            if isinstance(node, ast.Return) and node.value is not None:
                # The callee's parameters are the call's arguments, sliced where they are.
                self._expr(node.value, target_module, target_name, out, seen, depth + 1, False)

    def _name(
        self,
        name: str,
        module: Module,
        qualname: str,
        out: Trace,
        seen: set[tuple[str, str, str]],
        depth: int,
        follow: bool,
    ) -> None:
        key = (module.path, qualname, name)
        if key in seen or name in ("self", "cls"):
            return
        seen.add(key)
        fn = module.functions.get(qualname)
        bindings = list(self._bindings(fn, name)) if fn is not None else []
        if fn is not None and name in _params(fn):
            out.params.add(key)
            if follow:
                callers = list(self._callers(module, qualname, fn, name))
                if not callers:
                    out.open_params.add(key)
                for caller_name, arg in callers:
                    self._expr(arg, module, caller_name, out, seen, depth + 1, follow)
        elif not bindings:
            module_level = [
                node.value
                for node in module.tree.body
                if isinstance(node, ast.Assign) and any(_dotted(t) == name for t in node.targets)
            ]
            if module_level:
                bindings.extend(module_level)
            else:
                out.values += 1  # an import, a comprehension variable, a builtin
        for value in bindings:
            self._expr(value, module, qualname, out, seen, depth, follow)

    @staticmethod
    def _bindings(fn: ast.AST, name: str) -> Iterator[ast.AST]:
        """The expressions a function binds ``name`` to, or appends to it."""

        def binds(target: ast.AST) -> bool:
            return any(isinstance(n, ast.Name) and n.id == name for n in ast.walk(target))

        for node in _own_nodes(fn):
            if isinstance(node, ast.Assign) and any(binds(t) for t in node.targets):
                yield node.value
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)) and binds(
                node.target
            ):
                if node.value is not None:
                    yield node.value
            elif isinstance(node, (ast.For, ast.AsyncFor)) and binds(node.target):
                yield node.iter
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("append", "extend", "insert")
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == name
            ):
                yield from node.args

    @staticmethod
    def _callers(
        module: Module, qualname: str, fn: ast.FunctionDef | ast.AsyncFunctionDef, param: str
    ) -> Iterator[tuple[str, ast.expr]]:
        """The argument each same-module call of ``qualname`` binds to ``param``."""
        method = "." in qualname
        name = qualname.rsplit(".", 1)[-1]
        positional = [a.arg for a in [*fn.args.posonlyargs, *fn.args.args]]
        if method and positional and positional[0] in ("self", "cls"):
            positional = positional[1:]
        for caller_name, caller in module.functions.items():
            for node in _own_nodes(caller):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                same = (not method and isinstance(func, ast.Name) and func.id == name) or (
                    method
                    and isinstance(func, ast.Attribute)
                    and func.attr == name
                    and isinstance(func.value, ast.Name)
                    and func.value.id in ("self", "cls")
                )
                if not same:
                    continue
                for keyword in node.keywords:
                    if keyword.arg == param:
                        yield caller_name, keyword.value
                if param in positional:
                    index = positional.index(param)
                    if index < len(node.args) and not any(
                        isinstance(a, ast.Starred) for a in node.args[: index + 1]
                    ):
                        yield caller_name, node.args[index]


TRACER = Tracer()


def _verdict(site: CallSite, source: Source) -> str | None:
    """Why ``site`` isn't traced to ``source``, or ``None`` when it is."""
    if source is Source.FORWARDED:
        cls, _, method = site.function.rpartition(".")
        if cls not in FORWARDING_CLASSES or method not in PORT_METHODS or method in DOORS:
            return f"{site.function} is not a forwarding port method"
        trace = TRACER.trace(site, follow_callers=False)
        own = {param for path, function, param in trace.params if function == site.function}
        if not own:
            return f"its words don't come from {site.function}'s parameters"
        return None
    trace = TRACER.trace(site, follow_callers=True)
    if source is Source.REGISTRY:
        found = any(reached.dotted in REGISTRY_MARKS for reached in trace.calls)
        mark = "PROMPT_REGISTRY.render"
    elif source is Source.INSTRUCTION_FILE:
        found = any(
            r.resolved is not None and r.resolved[0] == INSTRUCTION_LOADER for r in trace.calls
        )
        mark = f"a function of {INSTRUCTION_LOADER}"
    elif source is Source.AUTHORED_CURRICULUM:
        found = any(r.dotted.endswith(f".{FEEDBACK_PROMPT}") for r in trace.calls)
        mark = f"an exercise's {FEEDBACK_PROMPT}"
    else:
        found = bool(trace.open_params)
        mark = "a parameter its callers outside the module fill"
    return None if found else f"its words are not traced to {mark}"


def _literal_arguments(site: CallSite) -> list[str]:
    """The word arguments of ``site`` that are literal text alone."""
    literal = []
    module = TRACER.module(site.path)
    for arg in Tracer.word_arguments(site.call):
        out = Trace()
        TRACER._expr(arg, module, site.function, out, set(), 0, False)
        if out.text and out.values == 0 and not out.params:
            literal.append(ast.unparse(arg))
    return literal


# ============================================================================
# The scan, collected once (problems never raise at collection)
# ============================================================================

SITES, UNFOLLOWABLE = _scan_core()


def _rows_and_problems() -> tuple[dict[tuple[str, str], list[CallSite]], list[str]]:
    rows: dict[tuple[str, str], list[CallSite]] = {}
    problems: list[str] = []
    allowed_ids = set(typing.get_args(AIPromptId))
    for site in SITES:
        if (site.path, site.function, site.method) in NOT_LLM:
            continue
        if site.method == "_generate_insight":
            first = site.call.args[0] if site.call.args else None
            if not (isinstance(first, ast.Constant) and first.value in allowed_ids):
                problems.append(
                    f"{site.path}:{site.line} {site.function}: _generate_insight's id is not "
                    "an AIPromptId literal"
                )
            continue
        if site.method in DOORS:
            continue
        rows.setdefault((site.path, site.function), []).append(site)
    for key in sorted(rows.keys() - CENSUS.keys()):
        lines = ", ".join(str(s.line) for s in rows[key])
        problems.append(f"{key[0]}:{lines} {key[1]}: an LLM call with no CENSUS row")
    problems.extend(
        f"{key[0]} {key[1]}: a CENSUS row with no LLM call (stale)"
        for key in sorted(CENSUS.keys() - rows.keys())
    )
    return rows, problems


ROWS, CENSUS_PROBLEMS = _rows_and_problems()


# ============================================================================
# Tests
# ============================================================================


def _control_marks() -> set[tuple[int, str]]:
    """``(line, method)`` for each ``# census: <method>`` comment in the control."""
    with CONTROL.open("rb") as source:
        return {
            (token.start[0], token.string.removeprefix("# census:").strip())
            for token in tokenize.tokenize(source.readline)
            if token.type == tokenize.COMMENT and token.string.startswith("# census:")
        }


def test_the_detector_finds_every_call_in_the_control() -> None:
    sites, problems = detect(CONTROL.read_text(encoding="utf-8"), _rel(CONTROL))

    assert problems == []
    assert {(s.line, s.method) for s in sites} == _control_marks()


def test_the_control_calls_every_port_method() -> None:
    assert {method for _, method in _control_marks()} == PORT_METHODS


@pytest.mark.parametrize(
    ("source", "problem"),
    [
        ("def f(llm):\n    return getattr(llm, 'complete')\n", "through getattr"),
        ("def f(llm):\n    generate = llm.generate\n    return generate\n", "without calling it"),
        ("async def f():\n    return await select_tool('q', [])\n", "by bare name"),
    ],
)
def test_a_port_method_the_census_cannot_follow_is_a_problem(source: str, problem: str) -> None:
    sites, problems = detect(source, "probe.py")

    assert sites == []
    assert len(problems) == 1
    assert problem in problems[0]


def test_every_llm_call_in_core_names_its_source() -> None:
    assert UNFOLLOWABLE == []
    assert CENSUS_PROBLEMS == []


def test_the_scan_finds_the_whole_census() -> None:
    """An empty scan would pass every other test: the count is the floor."""
    assert len(SITES) >= len(CENSUS) + 28 + 2
    assert sum(site.method == "_generate_insight" for site in SITES) == len(
        typing.get_args(AIPromptId)
    )


def _row_id(row: tuple[str, str]) -> str:
    return row[1]


@pytest.mark.parametrize("row", sorted(CENSUS), ids=_row_id)
def test_each_row_is_traced_to_its_source(row: tuple[str, str]) -> None:
    problems = [
        f"line {site.line}: {why}"
        for site in ROWS.get(row, [])
        if (why := _verdict(site, CENSUS[row])) is not None
    ]

    assert problems == []


def test_no_word_argument_is_literal_text_alone() -> None:
    literal = [
        f"{site.path}:{site.line} {site.function}: {text}"
        for sites in ROWS.values()
        for site in sites
        for text in _literal_arguments(site)
    ]

    assert literal == []


def test_the_curriculum_mark_is_a_real_method() -> None:
    assert callable(getattr(Exercise, FEEDBACK_PROMPT, None))
