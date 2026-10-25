"""A static census of the page bodies the page shells pad, and of what pads them again.

``SidebarPage`` pads its content column (``px-4 sm:px-6 lg:px-8 py-4 lg:py-6``,
``ui/patterns/sidebar.py``) and ``BasePage(STANDARD)`` pads its own
(``p-4 sm:p-6 lg:p-8``, ``ui/layouts/page_types.py``). The shell owns the gutter:
a body that pads its sides again doubles it. ``BasePage(page_type=CUSTOM)`` pads
nothing, so a body that pads itself there is correct, not a double.

The census reads every module under ``ui/`` and ``adapters/inbound/``. It finds
every call to a shell and to every function that passes one of its own
parameters through to one (a wrapper, found to a fixpoint), and resolves each
call's content to the elements that render at the content column's edge:
through names, local assignments, called functions (parameters bound to the
caller's arguments, and to each caller's when the walk starts inside the
function), conditionals, ``functools.partial``, function-local import aliases,
and HTMX placeholders (an element with ``hx_get`` and an ``hx_trigger`` of
``load`` is followed to the route that answers it).

The walk descends through an element only while it is transparent: no side
padding and no visible box (a border, background, shadow or ring class, a
hand-written CSS class whose rule paints one, or a ``style`` that sets a
background or border). An element whose classes pad a side is a hit and stops
the walk; a box stops it without a hit; a control or a table (``A``,
``Button``, ``Table``) is its own box, and so is a bulleted list, whose left
padding holds its markers. A text-level element (``P``, ``Span``, a heading) is
read for its own padding and not descended into: what it holds is its text. The walk also knows which elements sit at the
body's top or bottom edge (the first or last child, all the way down — a
child after one that may be absent is still at the edge), and records a block
there that pads that edge. Whatever the walk cannot
resolve is kept in ``unresolved`` with where it gave up, so the census states
its own holes.
"""

from __future__ import annotations

import ast
import re
from collections import defaultdict
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path

APP = Path(__file__).resolve().parents[3]
ROOTS = ("ui", "adapters/inbound")
SHELLS = ("BasePage", "SidebarPage")

SIDE = re.compile(r"^(?:[a-z0-9-]+:)*(?:p|px|pl|pr|ps|pe)-")
TOP = re.compile(r"^(?:[a-z0-9-]+:)*(?:p|py|pt)-")
BOTTOM = re.compile(r"^(?:[a-z0-9-]+:)*(?:p|py|pb)-")
MARKERS = re.compile(r"^list-(?:disc|decimal|square|roman|alpha)")
BOX = re.compile(r"^(?:[a-z0-9-]+:)*(?:border(?:-[a-z0-9]|$)|bg-|shadow|ring-)")
STATE_PREFIX = re.compile(r"^(?:hover|focus|group-hover|active|focus-visible|dark):")
BOX_STYLE = re.compile(r"\b(?:background|border)\b")

ELEMENTS = frozenset(
    {
        "Div", "Main", "Section", "Article", "Form", "Header", "Footer", "Nav", "Aside",
        "Ul", "Ol", "Li", "P", "Span", "H1", "H2", "H3", "H4", "H5", "H6", "Small",
        "Strong", "Em", "Code", "Fieldset", "Details", "Summary", "Template", "Label",
        "Img", "Canvas", "Pre", "Blockquote", "Dl", "Figure", "Svg", "Path", "Option",
        "Select", "Textarea", "I", "B", "Br", "Hr",
    }
)  # fmt: skip
OWN_BOX = frozenset({"A", "Button", "Table", "Thead", "Tbody", "Tr", "Th", "Td"})
BLOCKS = frozenset({"Div", "Main", "Section", "Article", "Form"})
# Text-level tags: their own padding is read, what they hold is their text.
TEXT = frozenset(
    {"P", "Span", "H1", "H2", "H3", "H4", "H5", "H6", "Small", "Strong", "Em", "Code",
     "Label", "Option", "B", "I", "Pre", "Blockquote", "Summary"}
)  # fmt: skip
ALIASES = {"HtmlButton": "Button", "_SKUELAlert": "Alert"}
# Calls that return text, a value or a non-visual element — never a padded body.
LEAVES = frozenset(
    {
        "join", "format", "str", "NotStr", "Safe", "Script", "Style", "Input", "FTInput",
        "Hidden", "Title", "getattr", "cast", "get", "upper", "lower", "title", "strftime",
        "len", "replace", "strip", "Icon", "Lucide", "HTMLResponse", "Response",
        "RedirectResponse",
    }
)  # fmt: skip
MAX_DEPTH = 18
EDGES = frozenset({"top", "bottom"})


def _css_boxes() -> frozenset[str]:
    """The hand-written CSS classes whose own rule paints a box (background, border or shadow)."""
    found: set[str] = set()
    for sheet in (APP / "static" / "css").glob("*.css"):
        if sheet.name == "output.css":  # the compiled Tailwind build
            continue
        text = re.sub(r"/\*.*?\*/", "", sheet.read_text(), flags=re.DOTALL)
        for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", text):
            if re.search(
                r"(?:^|[;\s])(?:background(?:-color)?|border(?:-[a-z]+)?|box-shadow)\s*:", body
            ):
                for selector in selectors.split(","):
                    if bare := re.fullmatch(r"\s*\.([A-Za-z0-9_-]+)\s*", selector):
                        found.add(bare.group(1))
    return frozenset(found)


CSS_BOXES = _css_boxes()

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


@dataclass
class Element:
    """One element the walk recorded, keyed by where it is written."""

    rel: str
    line: int
    tag: str
    function: str
    classes: tuple[str, ...]
    modes: set[str] = field(default_factory=set)
    entries: set[str] = field(default_factory=set)
    chains: set[str] = field(default_factory=set)

    @property
    def where(self) -> str:
        return f"{self.rel}:{self.line} ({self.function})"


@dataclass
class Census:
    files: tuple[str, ...]
    entry_files: frozenset[str]
    entries: int
    wrappers: dict[str, str]
    elements_seen_in: frozenset[str]
    side: list[Element]
    custom_side: list[Element]
    vertical: list[Element]  # a block at the body's top or bottom edge that pads that edge
    unresolved: set[tuple[str, str]]


class _Env:
    """Where a name resolves: the function being read and its bound parameters."""

    def __init__(
        self,
        fn: FunctionNode | None,
        rel: str,
        binds: dict[str, tuple[ast.expr, _Env]] | None = None,
    ) -> None:
        self.fn, self.rel, self.binds = fn, rel, binds or {}


def _params(fn: FunctionNode) -> list[str]:
    a = fn.args
    return [x.arg for x in a.posonlyargs + a.args + a.kwonlyargs]


def _call_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _own_nodes(fn: FunctionNode) -> Iterator[ast.AST]:
    """The nodes of ``fn``'s body, not those inside a nested def or lambda."""
    stack: list[ast.AST] = list(fn.body)
    while stack:
        node = stack.pop()
        yield node
        stack.extend(
            child
            for child in ast.iter_child_nodes(node)
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))
        )


def _assigned(node: ast.AST, name: str) -> ast.expr | None:
    """The value ``node`` assigns to ``name``, if it is an assignment to it."""
    if isinstance(node, ast.Assign) and any(
        isinstance(t, ast.Name) and t.id == name for t in node.targets
    ):
        return node.value
    if (
        isinstance(node, (ast.AnnAssign, ast.AugAssign))
        and isinstance(node.target, ast.Name)
        and node.target.id == name
    ):
        return node.value
    return None


def _maybe_absent(expr: ast.expr) -> bool:
    """A child that may render nothing: ``None``, ``""``, a conditional with such a
    branch, an ``and`` / ``or``, or a starred list that may be empty."""
    if isinstance(expr, ast.Constant):
        return expr.value in (None, "")
    if isinstance(expr, ast.IfExp):
        return _maybe_absent(expr.body) or _maybe_absent(expr.orelse)
    return isinstance(expr, (ast.BoolOp, ast.Starred))


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    for k in call.keywords:
        if k.arg == name:
            return k.value
        if k.arg is None and isinstance(k.value, ast.Dict):  # **{"hx-get": ...}
            for key, value in zip(k.value.keys, k.value.values, strict=True):
                if isinstance(key, ast.Constant) and key.value in (name, name.replace("_", "-")):
                    return value
    return None


class _Walker:
    def __init__(self, sources: Mapping[str, str]) -> None:
        self.files: dict[str, ast.Module] = {}
        self.parent: dict[ast.AST, ast.AST] = {}
        self.funcs: dict[str, list[tuple[str, FunctionNode]]] = defaultdict(list)
        self.consts: dict[str, list[ast.expr]] = defaultdict(list)
        self.kwfuncs: dict[str, set[str]] = defaultdict(set)
        self.import_aliases: dict[str, str] = {}
        self.calls_to: dict[str, list[tuple[str, ast.Call]]] = defaultdict(list)
        self.routes: list[tuple[re.Pattern[str], str, str, FunctionNode]] = []
        self.side: dict[tuple[str, int], Element] = {}
        self.vertical: dict[tuple[str, int], Element] = {}
        self.unresolved: set[tuple[str, str]] = set()
        self.seen_in: set[str] = set()
        for rel, text in sources.items():
            self._load(rel, ast.parse(text))

    # ------------------------------------------------------------------ loading

    def _load(self, rel: str, tree: ast.Module) -> None:
        self.files[rel] = tree
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                self.parent[child] = node
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.funcs[node.name].append((rel, node))
                for dec in node.decorator_list:
                    path = self._route_path(dec)
                    if path is not None:
                        self._add_route(path, rel, node)
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.asname and alias.asname != alias.name:
                        self.import_aliases[alias.asname] = alias.name
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node)
            if name:
                self.calls_to[name].append((rel, node))
            for k in node.keywords:
                if k.arg and isinstance(k.value, ast.Name):
                    self.kwfuncs[k.arg].add(k.value.id)
            # rt("/path")(handler)
            inner = node.func
            if (
                isinstance(inner, ast.Call)
                and node.args
                and isinstance(node.args[0], ast.Name)
                and (path := self._route_path(inner)) is not None
            ):
                for frel, fn in self.funcs.get(node.args[0].id, []):
                    if frel == rel:
                        self._add_route(path, rel, fn)
        for stmt in tree.body:
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name):
                        self.consts[target.id].append(stmt.value)
            elif (
                isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.value
            ):
                self.consts[stmt.target.id].append(stmt.value)
            elif isinstance(stmt, ast.ClassDef):
                for s in stmt.body:
                    if isinstance(s, ast.Assign):
                        for target in s.targets:
                            if isinstance(target, ast.Name):
                                self.consts[f"{stmt.name}.{target.id}"].append(s.value)

    @staticmethod
    def _route_path(dec: ast.expr) -> str | None:
        if not isinstance(dec, ast.Call) or not dec.args:
            return None
        first = dec.args[0]
        if (
            isinstance(first, ast.Constant)
            and isinstance(first.value, str)
            and first.value.startswith("/")
        ):
            return first.value
        if isinstance(first, ast.JoinedStr):
            return "".join(
                str(v.value) if isinstance(v, ast.Constant) else "{X}" for v in first.values
            )
        return None

    def _add_route(self, path: str, rel: str, fn: FunctionNode) -> None:
        pattern = "^" + re.sub(r"\\\{[^}]*\\\}", "[^/]*", re.escape(path)) + "$"
        self.routes.append((re.compile(pattern), path, rel, fn))

    def _enclosing(self, node: ast.AST) -> FunctionNode | None:
        n = self.parent.get(node)
        while n is not None and not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            n = self.parent.get(n)
        return n

    # --------------------------------------------------------------- resolving

    def _lookup(self, name: str, env: _Env) -> list[tuple[ast.expr, _Env]]:
        if name in env.binds:
            return [env.binds[name]]
        fn = env.fn
        if fn is not None and fn.args.vararg and fn.args.vararg.arg == name:
            return [env.binds["*" + name]] if "*" + name in env.binds else []
        if fn is not None and name in _params(fn):
            a = fn.args
            positional = a.posonlyargs + a.args
            defaults: dict[str, ast.expr] = dict(
                zip(
                    [x.arg for x in positional][len(positional) - len(a.defaults) :],
                    a.defaults,
                    strict=True,
                )
            )
            defaults.update(
                {
                    k.arg: d
                    for k, d in zip(a.kwonlyargs, a.kw_defaults, strict=True)
                    if d is not None
                }
            )
            if name in defaults:
                return [(defaults[name], _Env(None, env.rel))]
            return [(ast.Name(id="__UNBOUND_PARAM__" + name), env)]
        found: list[tuple[ast.expr, _Env]] = []
        if fn is not None:
            found.extend(
                (value, env) for n in _own_nodes(fn) if (value := _assigned(n, name)) is not None
            )
            if not found:  # a closure reads the outer function's names
                outer = self._enclosing(fn)
                if outer is not None:
                    return self._lookup(name, _Env(outer, env.rel))
        if not found:
            found = [(v, _Env(None, env.rel)) for v in self.consts.get(name, [])]
        return found

    def _strings(self, expr: ast.expr | None, env: _Env, depth: int = 0) -> list[str]:
        """Every string an expression can contribute (an over-approximation)."""
        if expr is None or depth > 6:
            return []
        out: list[str] = []
        for n in ast.walk(expr):
            if isinstance(n, ast.Constant) and isinstance(n.value, str):
                out.append(n.value)
            elif isinstance(n, ast.Name):
                for value, e in self._lookup(n.id, env):
                    out += self._strings(value, e, depth + 1)
            elif isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name):
                for value in self.consts.get(f"{n.value.id}.{n.attr}", []):
                    out += self._strings(value, _Env(None, env.rel), depth + 1)
        return out

    def _dict_values(self, expr: ast.expr, env: _Env, keys: tuple[str, ...]) -> list[ast.expr]:
        """The values a ``**mapping`` passes under ``keys``: a literal, or a name bound to one."""
        dicts: list[ast.Dict] = []
        if isinstance(expr, ast.Dict):
            dicts.append(expr)
        elif isinstance(expr, ast.Name):
            dicts += [v for v, _ in self._lookup(expr.id, env) if isinstance(v, ast.Dict)]
        return [
            value
            for d in dicts
            for key, value in zip(d.keys, d.values, strict=True)
            if isinstance(key, ast.Constant) and key.value in keys
        ]

    def _classes(self, call: ast.Call, env: _Env) -> list[str]:
        exprs = [k.value for k in call.keywords if k.arg in ("cls", "class_", "klass")]
        for k in call.keywords:
            if k.arg is None:
                exprs += self._dict_values(k.value, env, ("cls", "class", "class_"))
        return [token for e in exprs for s in self._strings(e, env) for token in s.split()]

    def _styled_box(self, call: ast.Call, env: _Env) -> bool:
        style = _keyword(call, "style")
        return style is not None and any(BOX_STYLE.search(s) for s in self._strings(style, env))

    def _urls(self, expr: ast.expr, env: _Env, depth: int = 0) -> list[str]:
        """A fragment URL as concrete-ish paths: a formatted part becomes ``X``."""
        if depth > 6:
            return []
        if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
            return [expr.value]
        if isinstance(expr, ast.JoinedStr):
            return [
                "".join(str(v.value) if isinstance(v, ast.Constant) else "X" for v in expr.values)
            ]
        if (
            isinstance(expr, ast.Name)
            and expr.id.startswith("__UNBOUND_PARAM__")
            and env.fn is not None
        ):
            bound = self._callers(env.fn, expr.id.removeprefix("__UNBOUND_PARAM__"))
            return [u for v, e in bound for u in self._urls(v, e, depth + 1)]
        if isinstance(expr, ast.Name):
            return [u for v, e in self._lookup(expr.id, env) for u in self._urls(v, e, depth + 1)]
        return []

    def _candidates(
        self, name: str, env: _Env, owner: str | None = None
    ) -> list[tuple[str, FunctionNode]]:
        """The functions a name can call; ``owner`` is the class or module of ``owner.name(...)``."""
        found = self.funcs.get(name) or self.funcs.get(self.import_aliases.get(name, ""), [])
        if owner is not None:
            owned = [
                (rel, fn)
                for rel, fn in found
                if Path(rel).stem == owner
                or (isinstance(cls := self.parent.get(fn), ast.ClassDef) and cls.name == owner)
            ]
            if owned:
                return owned
        same_file = [c for c in found if c[0] == env.rel]
        return same_file or found

    def _bind(
        self,
        fn: FunctionNode,
        args: list[ast.expr],
        keywords: list[ast.keyword],
        env: _Env,
        rel: str,
    ) -> _Env:
        names = [x.arg for x in fn.args.posonlyargs + fn.args.args]
        if names and names[0] in ("self", "cls"):
            names = names[1:]
        binds: dict[str, tuple[ast.expr, _Env]] = {}
        for name, arg in zip(names, args, strict=False):
            if not isinstance(arg, ast.Starred):
                binds[name] = (arg, env)
        for k in keywords:
            if k.arg:
                binds[k.arg] = (k.value, env)
        if fn.args.vararg:
            binds["*" + fn.args.vararg.arg] = (
                ast.List(elts=list(args[len(names) :]), ctx=ast.Load()),
                env,
            )
        return _Env(fn, rel, binds)

    def _callers(self, fn: FunctionNode, param: str) -> list[tuple[ast.expr, _Env]]:
        """What each call site of ``fn`` passes as ``param``."""
        found: list[tuple[ast.expr, _Env]] = []
        for rel, call in self.calls_to.get(fn.name, []):
            caller = _Env(self._enclosing(call), rel)
            bound = self._bind(fn, list(call.args), call.keywords, caller, rel)
            if param in bound.binds:
                found.append(bound.binds[param])
        return found

    # ----------------------------------------------------------------- walking

    def _hole(self, where: str, what: str) -> None:
        self.unresolved.add((where, what))

    def _siblings(
        self, items: list[ast.expr], ctx: dict[str, str]
    ) -> Iterator[tuple[ast.expr, dict[str, str]]]:
        """Each child with the edges it can sit at: the first one present has the
        parent's top edge, the last one present its bottom edge."""
        edges = set(ctx["edges"].split())
        present = [not _maybe_absent(item) for item in items]
        for i, item in enumerate(items):
            mine = set()
            if "top" in edges and not any(present[:i]):
                mine.add("top")
            if "bottom" in edges and not any(present[i + 1 :]):
                mine.add("bottom")
            yield (
                (item.value if isinstance(item, ast.Starred) else item),
                {**ctx, "edges": " ".join(sorted(mine))},
            )

    def walk(
        self,
        expr: ast.expr | None,
        env: _Env,
        ctx: dict[str, str],
        chain: tuple[str, ...],
        depth: int,
    ) -> None:
        if expr is None or depth > MAX_DEPTH:
            return
        where = f"{env.rel}:{getattr(expr, 'lineno', '?')}"
        if isinstance(expr, ast.Constant):
            return
        if isinstance(expr, (ast.List, ast.Tuple, ast.Set)):
            for e, child_ctx in self._siblings(list(expr.elts), ctx):
                self.walk(e, env, child_ctx, chain, depth + 1)
            return
        if isinstance(expr, ast.Starred):
            self.walk(expr.value, env, ctx, chain, depth + 1)
            return
        if isinstance(expr, (ast.ListComp, ast.GeneratorExp)):
            self.walk(expr.elt, env, ctx, chain, depth + 1)
            return
        if isinstance(expr, ast.IfExp):
            self.walk(expr.body, env, ctx, chain, depth + 1)
            self.walk(expr.orelse, env, ctx, chain, depth + 1)
            return
        if isinstance(expr, ast.BoolOp):
            for v in expr.values:
                self.walk(v, env, ctx, chain, depth + 1)
            return
        if isinstance(expr, (ast.JoinedStr, ast.Await, ast.Compare, ast.BinOp, ast.UnaryOp)):
            return  # text or a value, never an element
        if isinstance(expr, ast.Name) and expr.id.startswith("__UNBOUND_PARAM__"):
            param = expr.id.removeprefix("__UNBOUND_PARAM__")
            bound = self._callers(env.fn, param) if env.fn is not None else []
            if not bound:
                self._hole(where, f"unbound param {param}")
            for value, value_env in bound:
                self.walk(value, value_env, ctx, chain, depth + 1)
            return
        if isinstance(expr, ast.Name):
            if expr.id in ("None", "True", "False"):
                return
            hits = self._lookup(expr.id, env)
            if not hits:
                self._hole(where, f"name {expr.id}")
            for value, value_env in hits:
                self.walk(value, value_env, ctx, chain, depth + 1)
            return
        if isinstance(expr, ast.Call):
            self._call(expr, env, ctx, chain, depth, where)
            return
        self._hole(where, f"{type(expr).__name__} {ast.unparse(expr)[:60]}")

    def _tag(self, call: ast.Call) -> str | None:
        """The FastHTML tag a call builds: ``Div(...)``, ``fh.Div(...)``, or an import alias of one."""
        if isinstance(call.func, ast.Name):
            name = ALIASES.get(call.func.id, call.func.id)
            if name not in ELEMENTS | OWN_BOX:
                name = self.import_aliases.get(name, name)
        elif isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name):
            name = call.func.attr
        else:
            return None
        return name if name in ELEMENTS | OWN_BOX else None

    def _call(
        self,
        call: ast.Call,
        env: _Env,
        ctx: dict[str, str],
        chain: tuple[str, ...],
        depth: int,
        where: str,
    ) -> None:
        name = _call_name(call)
        name = ALIASES.get(name or "", name)
        tag = self._tag(call)
        if tag in OWN_BOX:
            self.seen_in.add(env.rel)
            return
        if tag in ELEMENTS:
            self._element(call, env, ctx, chain, depth)
            return
        if name in LEAVES:
            return
        if name == "FtResponse" and call.args:
            self.walk(call.args[0], env, ctx, chain, depth + 1)
            return
        if name == "partial" and call.args:
            return  # a renderer bound for later; the call that uses it is walked
        targets = self._callees(call, env, depth)
        if not targets and name and isinstance(call.func, ast.Attribute):
            targets = [
                (rel, fn, list(call.args), call.keywords, env)
                for f in sorted(self.kwfuncs.get(name, ()))
                for rel, fn in self.funcs.get(f, [])
            ]
        if not targets:
            self._hole(where, f"call {ast.unparse(call.func)}")
            return
        for rel, fn, args, keywords, arg_env in targets:
            bound = self._bind(fn, args, keywords, arg_env, rel)
            for n in _own_nodes(fn):
                if isinstance(n, ast.Return) and n.value is not None:
                    self.walk(n.value, bound, ctx, (*chain, f"{fn.name}()"), depth + 1)

    def _callees(
        self, call: ast.Call, env: _Env, depth: int
    ) -> list[tuple[str, FunctionNode, list[ast.expr], list[ast.keyword], _Env]]:
        """The functions a call reaches: by name, or through a name bound to a function or a partial."""
        name = _call_name(call)
        if not name:
            return []
        pending: list[tuple[ast.expr, _Env]] = (
            self._lookup(name, env) if isinstance(call.func, ast.Name) else []
        )
        if not pending:
            owner = (
                call.func.value.id
                if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name)
                else None
            )
            return [
                (rel, fn, list(call.args), call.keywords, env)
                for rel, fn in self._candidates(name, env, owner)
            ]
        out: list[tuple[str, FunctionNode, list[ast.expr], list[ast.keyword], _Env]] = []
        for _ in range(4):
            next_pending: list[tuple[ast.expr, _Env]] = []
            for value, e in pending:
                if (
                    isinstance(value, ast.Name)
                    and value.id.startswith("__UNBOUND_PARAM__")
                    and e.fn is not None
                ):
                    next_pending += self._callers(e.fn, value.id.removeprefix("__UNBOUND_PARAM__"))
                elif isinstance(value, ast.Name) and value.id in self.funcs:
                    out += [
                        (rel, fn, list(call.args), call.keywords, env)
                        for rel, fn in self._candidates(value.id, e)
                    ]
                elif isinstance(value, ast.Name):
                    next_pending += self._lookup(value.id, e)
                elif (
                    isinstance(value, ast.Call)
                    and _call_name(value) == "partial"
                    and value.args
                    and isinstance(value.args[0], ast.Name)
                ):
                    # partial(f, *bound)(*args): f's leading parameters come from the partial
                    for rel, fn in self._candidates(value.args[0].id, e):
                        bound = self._bind(fn, list(value.args[1:]), value.keywords, e, rel)
                        rest = self._bind(fn, [], [], env, rel)
                        names = [x.arg for x in fn.args.posonlyargs + fn.args.args][
                            len(value.args) - 1 :
                        ]
                        binds = dict(bound.binds)
                        for pname, arg in zip(names, call.args, strict=False):
                            binds[pname] = (arg, env)
                        for k in call.keywords:
                            if k.arg:
                                binds[k.arg] = (k.value, env)
                        rest.binds = binds
                        out.append((rel, fn, [], [], rest))
            pending = next_pending
            if not pending:
                break
        return out

    def _element(
        self, call: ast.Call, env: _Env, ctx: dict[str, str], chain: tuple[str, ...], depth: int
    ) -> None:
        self.seen_in.add(env.rel)
        tag = self._tag(call) or "?"
        tokens = self._classes(call, env)
        boxed = [
            t for t in tokens if (BOX.match(t) and not STATE_PREFIX.match(t)) or t in CSS_BOXES
        ]
        if boxed or self._styled_box(call, env):
            return
        if tag in ("Ul", "Ol") and any(MARKERS.match(t) for t in tokens):
            return  # a bulleted list: its left padding holds the markers
        fn = self._enclosing(call)
        key = (env.rel, call.lineno)
        edges = ctx["edges"].split()
        pads_an_edge = ("top" in edges and any(TOP.match(t) for t in tokens)) or (
            "bottom" in edges and any(BOTTOM.match(t) for t in tokens)
        )
        if pads_an_edge and tag in BLOCKS and ctx["shell"] != "custom":
            element = self.vertical.setdefault(
                key,
                Element(env.rel, call.lineno, tag, fn.name if fn else "<module>", tuple(tokens)),
            )
            element.modes.add(ctx["shell"])
        if any(SIDE.match(t) for t in tokens):
            element = self.side.setdefault(
                key,
                Element(env.rel, call.lineno, tag, fn.name if fn else "<module>", tuple(tokens)),
            )
            element.modes.add(ctx["shell"])
            element.entries.add(ctx["entry"])
            element.chains.add(" > ".join(chain[-5:]))
            return
        hx_get = _keyword(call, "hx_get")
        trigger = _keyword(call, "hx_trigger")
        if (
            hx_get is not None
            and trigger is not None
            and "load" in " ".join(self._strings(trigger, env))
        ):
            self._follow(call, hx_get, env, ctx, chain, depth)
            return
        if tag in TEXT:
            return
        for arg, child_ctx in self._siblings(list(call.args), ctx):
            self.walk(arg, env, child_ctx, (*chain, tag), depth + 1)

    def _follow(
        self,
        call: ast.Call,
        hx_get: ast.expr,
        env: _Env,
        ctx: dict[str, str],
        chain: tuple[str, ...],
        depth: int,
    ) -> None:
        """An HTMX placeholder: walk what the route that answers it returns."""
        where = f"{env.rel}:{call.lineno}"
        urls = sorted({u for u in self._urls(hx_get, env) if u.startswith("/")})
        if not urls:
            self._hole(where, f"hx_get {ast.unparse(hx_get)[:60]}")
            return
        swap = " ".join(self._strings(_keyword(call, "hx_swap"), env)) or "innerHTML"
        for u in urls:
            path = u.split("?")[0].replace("X", "zz")
            matched = [r for r in self.routes if r[0].match(path)] if path.startswith("/") else []
            if any("{" not in r[1] for r in matched):
                matched = [r for r in matched if "{" not in r[1]]
            if not matched:
                self._hole(where, f"route {path}")
            for _, route_path, rel, fn in matched:
                for n in _own_nodes(fn):
                    if isinstance(n, ast.Return) and n.value is not None:
                        self.walk(
                            n.value,
                            _Env(fn, rel),
                            ctx,
                            (*chain, f"HTMX {route_path} ({swap})"),
                            depth + 1,
                        )

    # ------------------------------------------------------------------ census

    def _mode(self, call: ast.Call) -> str:
        if _call_name(call) == "SidebarPage":
            return "sidebar"
        page_type = _keyword(call, "page_type")
        if page_type is None and len(call.args) > 2:
            page_type = call.args[2]
        if page_type is None:
            return "standard"
        text = ast.unparse(page_type)
        if "CUSTOM" in text:
            return "custom"
        if "STANDARD" in text:
            return "standard"
        return f"param:{text}"

    @staticmethod
    def _content(call: ast.Call, index: int, param: str) -> ast.expr | None:
        for k in call.keywords:
            if k.arg == param:
                return k.value
        if len(call.args) > index and not isinstance(call.args[index], ast.Starred):
            return call.args[index]
        return None

    def take(self) -> Census:
        shells: dict[str, tuple[int, str, str | None]] = {
            "BasePage": (0, "content", None),
            "SidebarPage": (0, "content", "sidebar"),
        }
        changed = True
        while changed:
            changed = False
            for name, defs in list(self.funcs.items()):
                if name in shells:
                    continue
                for _rel, fn in defs:
                    names = _params(fn)
                    for n in _own_nodes(fn):
                        if (
                            not isinstance(n, ast.Call)
                            or _call_name(n) not in shells
                            or _call_name(n) == name
                        ):
                            continue
                        index, param, mode = shells[_call_name(n) or ""]
                        content = self._content(n, index, param)
                        if isinstance(content, ast.Name) and content.id in names:
                            offset = 1 if names and names[0] == "self" else 0
                            shells[name] = (
                                names.index(content.id) - offset,
                                content.id,
                                mode or self._mode(n),
                            )
                            changed = True
        entries = 0
        entry_files: set[str] = set()
        for rel, tree in self.files.items():
            for n in ast.walk(tree):
                if not isinstance(n, ast.Call) or _call_name(n) not in shells:
                    continue
                enclosing = self._enclosing(n)
                index, param, mode = shells[_call_name(n) or ""]
                content = self._content(n, index, param)
                if content is None:
                    continue
                if (
                    enclosing is not None
                    and isinstance(content, ast.Name)
                    and content.id in _params(enclosing)
                    and enclosing.name in shells
                ):
                    continue  # the wrapper's own pass-through
                entries += 1
                entry_files.add(rel)
                ctx = {
                    "entry": f"{rel}:{n.lineno} {_call_name(n)}",
                    "shell": mode or self._mode(n),
                    "edges": "bottom top",
                }
                self.walk(content, _Env(enclosing, rel), ctx, (), 0)
        side = sorted(self.side.values(), key=lambda e: (e.rel, e.line))
        return Census(
            files=tuple(sorted(self.files)),
            entry_files=frozenset(entry_files),
            entries=entries,
            wrappers={k: v[2] or "?" for k, v in shells.items() if k not in SHELLS},
            elements_seen_in=frozenset(self.seen_in),
            side=[e for e in side if e.modes - {"custom"}],
            custom_side=[e for e in side if e.modes == {"custom"}],
            vertical=sorted(self.vertical.values(), key=lambda e: (e.rel, e.line)),
            unresolved=self.unresolved,
        )


def source_files() -> dict[str, str]:
    """Every module under the census roots, by path relative to ``app/``."""
    return {
        str(p.relative_to(APP)): p.read_text()
        for root in ROOTS
        for p in sorted((APP / root).rglob("*.py"))
    }


def take(sources: Mapping[str, str] | None = None) -> Census:
    """The census over ``sources`` (default: every module under the roots)."""
    return _Walker(source_files() if sources is None else sources).take()
