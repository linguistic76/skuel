"""Every ``hx_*`` target authored in ``ui/`` and ``adapters/inbound/`` names a registered route.

A form or button whose ``hx_post`` / ``hx_get`` names a path the app does not serve is
a 404 at click time and nothing else: the page renders, CI is green, and the door is
dead. The route table is the runtime one (``scripts/health/route_catalog.py`` — the
factories register through f-strings a static pass cannot see), so a target is held to
the catalog the application actually mounts, and to the VERB it posts with: plain
``@rt`` serves GET/HEAD/POST, a factory route is verb-specific, and the CRUD delete is
a POST — an ``hx_delete`` against it is a 405.

Two kinds of target, two verdicts:

* **Literal** — a string constant or an f-string (each ``{expr}`` becomes a wildcard
  segment the catalog matches as a parameter), directly in the kwarg or reached
  through a name bound once in the enclosing function or module (``url = f"…"``;
  ``url = a if cond else b`` yields both branches). Not registered for its verb → the
  test FAILS, naming ``file:line VERB target``.
* **Opaque** — a parameter, attribute, call or other expression the scan cannot read.
  Counted and printed, never failed; the count is pinned so a new one is a diff
  someone reads rather than a silent exemption (a computed ``**{"hx-" + method: url}``
  key is the shape this pin exists for — it hides a target from every literal scan).

Positive controls at the bottom: a known-live factory route must pass, a known-dead
path must fail, through the same walker the tree is held to.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]

# scripts/health/ has no __init__.py — add it to sys.path for import (matches
# tests/unit/scripts/test_route_catalog.py).
sys.path.insert(0, str(ROOT / "scripts" / "health"))

import route_catalog as rc  # type: ignore[import-not-found]  # noqa: E402

SCAN_ROOTS = ("ui", "adapters/inbound")

# FastHTML kwarg spelling → HTTP verb. The hyphenated form is the key a ``**{...}``
# splat uses for the same attribute.
HX_KWARG_VERBS = {
    "hx_get": "GET",
    "hx_post": "POST",
    "hx_put": "PUT",
    "hx_patch": "PATCH",
    "hx_delete": "DELETE",
}
HX_ATTR_VERBS = {k.replace("_", "-"): v for k, v in HX_KWARG_VERBS.items()}

# Targets the scan cannot read, pinned so a new opaque target is a reviewed diff,
# never a silent exemption. The failure message lists them as ``file:line kwarg``.
OPAQUE_TARGETS_PINNED = 8

Bindings = dict[str, ast.expr]


@dataclass(frozen=True)
class HxTarget:
    file: str
    line: int
    verb: str
    targets: tuple[str, ...] | None  # None = opaque; several = a conditional's branches
    kwarg: str

    def __str__(self) -> str:
        shown = " | ".join(self.targets) if self.targets else "<opaque>"
        return f"{self.file}:{self.line}  {self.verb} {shown}  ({self.kwarg})"


def _resolve(node: ast.expr, bindings: Bindings, depth: int = 0) -> tuple[str, ...] | None:
    """The string(s) an expression can evaluate to, or ``None`` when the scan cannot say.

    A constant is itself; an f-string keeps its literal parts and turns each ``{expr}``
    into a wildcard segment (a ``{call()}`` only where ``/`` boxes it in on both sides —
    elsewhere it may expand to several segments, and the target is opaque); a
    conditional yields both branches; a name bound once in scope resolves to what it
    was bound to (two hops at most — enough for ``url = base if x else other``, never
    a chain the reader would have to trace).
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return (node.value,)
    if isinstance(node, ast.JoinedStr):
        pieces: list[str] = []
        parts = list(node.values)
        for i, part in enumerate(parts):
            if isinstance(part, ast.Constant):
                pieces.append(str(part.value))
                continue
            inner = part.value if isinstance(part, ast.FormattedValue) else part
            if isinstance(inner, ast.Call) and not (
                _bracketed_segment(parts, i) or _in_query(parts, i)
            ):
                # A call may expand to several segments (a computed tail), which no
                # wildcard can stand for; one boxed in by ``/`` on both sides is one
                # segment, and one past the ``?`` never touches the path at all.
                return None
            spliced = _resolve(inner, bindings, depth + 1) if isinstance(inner, ast.Name) else None
            pieces.append(spliced[0] if spliced and len(spliced) == 1 else "{x}")
        return ("".join(pieces),)
    if isinstance(node, ast.IfExp):
        yes = _resolve(node.body, bindings, depth)
        no = _resolve(node.orelse, bindings, depth)
        return None if yes is None or no is None else yes + no
    if isinstance(node, ast.Name) and node.id in bindings and depth < 2:
        return _resolve(bindings[node.id], bindings, depth + 1)
    return None


SCOPE_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


def _own_nodes(scope: ast.AST):
    """The nodes at a scope's own level — descending into everything but a nested scope."""
    stack = list(reversed(list(ast.iter_child_nodes(scope))))
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, SCOPE_NODES):
            stack.extend(reversed(list(ast.iter_child_nodes(node))))


def _bracketed_segment(parts: list[ast.expr], i: int) -> bool:
    """Is the ``{expr}`` at ``parts[i]`` exactly one path segment — ``/`` before it and
    ``/``, ``?`` or ``#`` after it?"""
    before = parts[i - 1] if i > 0 else None
    after = parts[i + 1] if i + 1 < len(parts) else None
    opens = isinstance(before, ast.Constant) and str(before.value).endswith("/")
    closes = isinstance(after, ast.Constant) and str(after.value)[:1] in ("/", "?", "#")
    return opens and closes


def _in_query(parts: list[ast.expr], i: int) -> bool:
    """Does a ``?`` or ``#`` precede ``parts[i]`` — is it in the query string, not the path?"""
    return any(
        isinstance(p, ast.Constant) and ("?" in str(p.value) or "#" in str(p.value))
        for p in parts[:i]
    )


def _single_bindings(scope: ast.AST) -> Bindings:
    """Names assigned exactly once, at this scope's own level, to a plain expression.

    A name assigned twice, augmented, unpacked or annotated-without-value is left out
    and stays opaque; a nested function body is its own scope.
    """
    seen: dict[str, list[ast.expr]] = {}
    for node in _own_nodes(scope):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                seen.setdefault(target.id, []).append(node.value)
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            if isinstance(node.target, ast.Name):
                seen.setdefault(node.target.id, []).append(node.value)
        elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
            seen.setdefault(node.target.id, []).extend((node.value, node.value))
    return {name: values[0] for name, values in seen.items() if len(values) == 1}


def _scope_bindings(scope: ast.AST, outer: Bindings) -> Bindings:
    """A scope's own single bindings shadowing the enclosing ones."""
    return {**outer, **_single_bindings(scope)}


def _splat_targets(call: ast.Call, rel: str, bindings: Bindings) -> list[HxTarget]:
    """``**{"hx-post": url}`` dict splats — the attribute spelled as a dict key.

    A key that is itself computed (``"hx-" + method``) is opaque: the verb is unknown
    and so is the target, and the pin is what makes it visible.
    """
    found: list[HxTarget] = []
    for kw in call.keywords:
        if kw.arg is not None or not isinstance(kw.value, ast.Dict):
            continue
        for key, value in zip(kw.value.keys, kw.value.values, strict=True):
            if key is None:
                continue
            key_text = _resolve(key, {})
            if key_text is None:
                if "hx" in ast.dump(key):
                    found.append(HxTarget(rel, key.lineno, "?", None, "computed-key"))
                continue
            verb = HX_ATTR_VERBS.get(key_text[0])
            if verb is None:
                continue
            found.append(HxTarget(rel, value.lineno, verb, _resolve(value, bindings), key_text[0]))
    return found


def _call_targets(call: ast.Call, rel: str, bindings: Bindings) -> list[HxTarget]:
    found: list[HxTarget] = []
    for kw in call.keywords:
        verb = HX_KWARG_VERBS.get(kw.arg or "")
        if verb is None:
            continue
        found.append(
            HxTarget(rel, kw.value.lineno, verb, _resolve(kw.value, bindings), kw.arg or "")
        )
    found.extend(_splat_targets(call, rel, bindings))
    return found


def _walk_scope(scope: ast.AST, rel: str, outer: Bindings, out: list[HxTarget]) -> None:
    """Visit a scope's calls with its bindings, then each nested scope with its own."""
    bindings = _scope_bindings(scope, outer)
    for node in _own_nodes(scope):
        if isinstance(node, ast.Call):
            out.extend(_call_targets(node, rel, bindings))
        elif isinstance(node, SCOPE_NODES):
            _walk_scope(node, rel, bindings, out)


def collect_hx_targets_in(tree: ast.AST, rel: str) -> list[HxTarget]:
    """Every ``hx_<verb>`` keyword and ``**{"hx-<verb>": …}`` key in one module."""
    found: list[HxTarget] = []
    _walk_scope(tree, rel, {}, found)
    return found


def collect_hx_targets(root: Path = ROOT) -> list[HxTarget]:
    """Every ``hx_<verb>`` keyword and ``**{"hx-<verb>": …}`` key under the scan roots."""
    targets: list[HxTarget] = []
    for scan_root in SCAN_ROOTS:
        for py in sorted((root / scan_root).rglob("*.py")):
            rel = py.relative_to(root).as_posix()
            tree = ast.parse(py.read_text(encoding="utf-8"))
            targets.extend(collect_hx_targets_in(tree, rel))
    return targets


def unregistered(targets: list[HxTarget], catalog: rc.RouteCatalog) -> list[HxTarget]:
    """Literal absolute targets the catalog does not serve for their verb.

    Query strings are stripped before matching (``?uid=…`` rides on a registered
    path); a relative target (no leading ``/``) is outside the catalog's vocabulary
    and is not judged here.
    """
    missing: list[HxTarget] = []
    for t in targets:
        if t.targets is None:
            continue
        for target in t.targets:
            if not target.startswith("/"):
                continue
            norm = rc.normalize(target)
            if norm is not None and not catalog.is_registered(norm, t.verb):
                missing.append(t)
                break
    return missing


@pytest.fixture(scope="module")
def catalog() -> rc.RouteCatalog:
    return rc.runtime_catalog()


@pytest.fixture(scope="module")
def targets() -> list[HxTarget]:
    return collect_hx_targets()


def test_every_literal_hx_target_is_registered(
    targets: list[HxTarget], catalog: rc.RouteCatalog
) -> None:
    missing = unregistered(targets, catalog)
    assert not missing, "hx_* targets no route serves:\n" + "\n".join(f"  {t}" for t in missing)


def test_opaque_hx_targets_are_pinned(targets: list[HxTarget]) -> None:
    """A target the scan cannot read is reported, and its count is a reviewed number."""
    opaque = [t for t in targets if t.targets is None]
    listing = "\n".join(f"  {t}" for t in opaque)
    print(f"\nopaque hx_* targets ({len(opaque)}):\n{listing}")
    assert len(opaque) == OPAQUE_TARGETS_PINNED, (
        f"{len(opaque)} opaque hx_* targets, pinned {OPAQUE_TARGETS_PINNED} — a computed "
        f"target is invisible to this scan; prefer a literal kwarg, then re-pin:\n{listing}"
    )


def test_the_walker_reads_every_spelling() -> None:
    """Kwargs, dict-splat keys, f-strings, conditionals and once-bound names — from source."""
    src = (
        'BASE = "/api/base"\n'
        "def page(uid, mode, next_url):\n"
        '    url = f"/api/exercises/update?uid={uid}" if mode == "edit" else "/api/exercises/create"\n'
        '    Button(hx_post=f"/api/tasks/{uid}/status")\n'
        '    Form(**{"hx-delete": "/api/x/delete?uid=1", "hx-target": "#t"})\n'
        "    Div(hx_get=next_url)\n"
        '    Form(**{"hx-" + mode: url})\n'
        "    Form(hx_post=url)\n"
        "    Div(hx_get=BASE)\n"
        "    twice = '/a'\n"
        "    twice = '/b'\n"
        "    Div(hx_get=twice)\n"
        '    Div(hx_get=f"{BASE}/lines?offset={uid}")\n'
        '    Div(hx_delete=f"/api/{uid}/{tail(uid)}")\n'
        '    Div(hx_get=f"/today/{day.isoformat()}/habits")\n'
        '    Div(hx_get=f"/api/picker/search?{urlencode(qs)}")\n'
    )
    found = {t.line: t for t in collect_hx_targets_in(ast.parse(src), "src")}
    assert found[4].targets == ("/api/tasks/{x}/status",) and found[4].verb == "POST"
    assert found[5].targets == ("/api/x/delete?uid=1",) and found[5].verb == "DELETE"
    assert found[6].targets is None and found[6].kwarg == "hx_get"  # a parameter
    assert found[7].targets is None and found[7].kwarg == "computed-key"
    assert found[8].targets == ("/api/exercises/update?uid={x}", "/api/exercises/create")
    assert found[9].targets == ("/api/base",)  # a module constant
    assert found[12].targets is None  # rebound in scope: which one is unknowable here
    assert found[13].targets == ("/api/base/lines?offset={x}",)  # the constant splices in
    assert found[14].targets is None  # a trailing call may span segments
    assert found[15].targets == ("/today/{x}/habits",)  # a call boxed in by `/` is one
    assert found[16].targets == ("/api/picker/search?{x}",)  # past the `?` the path is fixed


@pytest.mark.parametrize(
    ("target", "verb", "expected"),
    [
        ("/api/tasks/{x}/status", "POST", True),  # factory route the static view cannot see
        ("/api/exercises/delete?uid=abc", "POST", True),  # CRUD delete is a POST
        ("/api/exercises/delete?uid=abc", "DELETE", False),  # …and never the DELETE verb
        ("/api/admin/users/{x}/role", "POST", False),  # a path-uid door the admin API never had
        ("/admin/users/partial", "GET", True),
    ],
)
def test_positive_controls(
    catalog: rc.RouteCatalog, target: str, verb: str, expected: bool
) -> None:
    t = HxTarget("control", 0, verb, (target,), "hx_x")
    assert (unregistered([t], catalog) == []) is expected
