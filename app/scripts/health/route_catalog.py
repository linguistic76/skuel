"""
Route catalog — the application's registered URL paths, for the docs health checks.

ONE catalog, two readers: ``dead_doc_links.py`` (is this leading-slash citation an
application URL rather than a missing repo file?) and ``route_claims.py`` (does this
route the doc describes exist?). Both consume :func:`runtime_catalog`; neither keeps a
URL list of its own, because a catalog copy is a catalog that rots.

Why the catalog is read from the RUNTIME route table
-----------------------------------------------------
The routes tree registers most of its paths through factories and f-strings —
``@rt(f"/{domain}")``, ``@rt(f"{self.base_path}/create")``, every lateral / hierarchy /
CRUD / query / intelligence factory. A static pass over ``adapters/inbound/`` sees only
the string literals — barely half the table — and what it cannot see includes
``/tasks``, ``/api/tasks/create`` and every ``/api/{domain}/{uid}/lateral/*``. A scanner
built on the static view reports each of those as fiction.

So :func:`runtime_route_table` wires the real route tree onto a bare ``fast_app()`` with
every service replaced by a ``MagicMock`` and the ``SystemService`` initialisation
stubbed — no Neo4j, no credentials, no ``.env``; a few seconds, once per process. **It
is the union over intelligence tiers**: every service attribute on the mock is truthy,
so every ``if services.x is not None`` branch registers. That is the right catalog for
docs, which may legitimately describe a FULL-tier route from a CORE-tier checkout. Each
path carries the HTTP methods its registrations accept, so a claim that names a verb
(``PUT /api/events/{uid}/status``) is held to it — a route served only for ``POST`` does
not make that claim true.

The static extractor survives as :func:`ast_route_paths`, kept ONLY so
``tests/unit/scripts/test_route_catalog.py`` can assert it is a subset of the runtime
table and print the size of the gap on every run — never as a reader's source.

⚠️ The root static catch-all
----------------------------
``fast_app()`` installs ``/{fname:path}.{ext:static}`` at root scope; bootstrap strips
it before wiring (``scripts/dev/bootstrap.py`` ``_create_web_app``) and so does this
probe, by the same predicate. Normalised, that route is ``/{}`` and matches EVERY
single-segment claim — ``/ku``, ``/home``, ``/sel`` all read as registered while it is
present. The catalog test pins its absence by name, and holds positive controls in
both directions: known-dead paths must NOT be registered, known-live factory paths MUST
be. A catalog that admits a dead route hides real rot; one that refuses a live route
turns the sweep queue into noise.

Matching
--------
:func:`normalize` strips query and anchor, a trailing slash, and turns any segment
containing ``{`` into the wildcard ``{}`` (a Starlette converter ``{x:path}`` included).
``RouteCatalog.is_registered`` matches segment by segment, and a wildcard is wild in
ONE direction per match: either the claim is an *instance* of the registration (the
registration's parameters may cover the claim's literals — ``/api/tasks/{uid}/status``
serves ``/api/tasks/abc/status``) or the claim is a *family* the registration belongs
to (the claim's placeholders may cover the registration's literals — a doc's
``/api/{domain}/create`` names ``/api/tasks/create``). Never both at once: with wildcards
crossing, ``/api/ku/related/{uid}`` would read as served by ``/api/ku/{uid}/mark-studying``
— the registration's parameter eating ``related`` while the claim's placeholder eats
``mark-studying`` — and no such route exists. The two near-miss relations are exposed as
their own predicates (``is_family_prefix``, ``is_relative_suffix``) because the claims
scanner reports them as CLASSES rather than skipping them: each hides real fiction when
treated as a match.
"""

from __future__ import annotations

import ast
import asyncio
import contextlib
import io
from collections.abc import Mapping
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

if TYPE_CHECKING:
    from collections.abc import Iterable

ROOT = Path(__file__).parent.parent.parent  # /home/mike/skuel/app

# `ROUTE_DECORATORS` mirrors `scripts/audit_route_security.py`'s definition of a route
# decorator rather than inventing a second one.
ROUTE_DECORATORS = frozenset({"rt", "route"})

# The predicate bootstrap uses to drop fast_app()'s root static catch-all. One
# spelling, shared by construction with `_create_web_app`'s comprehension.
CATCH_ALL_MARKER = "{fname:path}"


def normalize(path: str) -> str | None:
    """A claim or registration as the catalog compares it, or ``None`` if not a path.

    Query string and anchor are dropped, a trailing slash is dropped (``/`` itself
    stays), and every segment containing ``{`` becomes the wildcard ``{}``.
    """
    path = path.split("#")[0].split("?")[0].strip()
    if not path.startswith("/"):
        return None
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    return "/".join("{}" if "{" in seg else seg for seg in path.split("/"))


def _segments_match(claim: list[str], registration: list[str]) -> bool:
    """Same length, every position equal or covered by a wildcard — in ONE direction.

    The claim may be an instance of the registration (registration wildcards over
    claim literals) or a family it belongs to (claim wildcards over registration
    literals); a match that needs both readings at once is two different routes.
    """
    if len(claim) != len(registration):
        return False
    instance = True  # registration parameters cover claim literals
    family = True  # claim placeholders cover registration literals
    for c, r in zip(claim, registration, strict=True):
        if c == r:
            continue
        if c == "{}" and r == "{}":
            continue
        if c == "{}":
            instance = False
        elif r == "{}":
            family = False
        else:
            return False
    return instance or family


# Methods per normalised path; ``None`` means the source carried no method information
# (a bare path set), and any verb is accepted for that path.
_Methods = frozenset[str] | None


def _allows(methods: _Methods, verb: str) -> bool:
    return not verb or methods is None or verb in methods


class RouteCatalog:
    """The normalised route table with its three relations.

    Built once from registered paths — a mapping ``{path: methods}`` (the runtime
    table) or a bare iterable of paths (a test's ``frozenset``, method-blind) — so every
    reader matches the same way.
    """

    def __init__(self, raw: Mapping[str, Iterable[str]] | Iterable[str]) -> None:
        methods: dict[str, _Methods] = {}
        entries: Iterable[tuple[str, _Methods]]
        if isinstance(raw, Mapping):
            entries = ((p, frozenset(m.upper() for m in ms)) for p, ms in raw.items())
        else:
            entries = ((p, None) for p in raw)
        for path, verbs in entries:
            norm = normalize(path)
            if norm is None:
                continue
            # Two registrations can normalise to one path (`/x/{a}` and `/x/{b}`); the
            # union of their verbs is what the path serves, and one unknown makes the
            # whole path verb-blind.
            known = methods.get(norm)
            if norm in methods and (known is None or verbs is None):
                methods[norm] = None
            elif known is not None and verbs is not None:
                methods[norm] = known | verbs
            else:
                methods[norm] = verbs
        self._methods: dict[str, _Methods] = methods
        self.paths: frozenset[str] = frozenset(methods)
        self._segments: list[tuple[list[str], _Methods]] = [
            (p.split("/"), methods[p]) for p in self.paths
        ]
        # Last segments of routes at least two segments deep: `/api/tasks/create` →
        # `create`. A single-segment claim that names one of these is a RELATIVE
        # citation of a deeper route, not a root route.
        self._deep_last_segments: frozenset[str] = frozenset(
            s[-1] for s, _m in self._segments if len(s) > 2
        )

    def __len__(self) -> int:
        return len(self.paths)

    def methods_for(self, norm: str) -> _Methods:
        """The verbs a normalised path is registered for; ``None`` when unknown."""
        return self._methods.get(norm)

    def is_registered(self, norm: str, method: str = "") -> bool:
        """Is this path served — and, when a verb is claimed, served for that verb?

        Exact match first, then the directional wildcard match against every
        registration. A claimed method must be among the verbs of a registration that
        matches; a method-blind catalog (built from bare paths) accepts any verb.
        """
        verb = method.upper()
        if norm in self._methods and _allows(self._methods[norm], verb):
            return True
        segs = norm.split("/")
        return any(_segments_match(segs, c) and _allows(ms, verb) for c, ms in self._segments)

    def is_family_prefix(self, norm: str) -> bool:
        """Is this unmatched path a strict prefix of at least one registered route?

        ``/api/context`` names the door to ``/api/context/*``; ``/profile`` names the
        family under ``/profile/inbox``. Reported as a class, never a skip: ``POST
        /api/knowledge`` is a strict prefix of ``/api/knowledge/ai/*`` and does not exist.
        """
        segs = norm.split("/")
        return any(
            len(c) > len(segs) and _segments_match(segs, c[: len(segs)]) for c, _m in self._segments
        )

    def is_relative_suffix(self, norm: str) -> bool:
        """Is this a single-segment path that ends at least one deeper registered route?

        ``/create``, ``/delete``, ``/upload`` cited relative to a base the prose named
        earlier. Reported as a class, never a skip: ``/ku`` lands here through
        ``/library/ku`` and there is no ``/ku`` route.
        """
        segs = norm.split("/")
        return len(segs) == 2 and segs[1] in self._deep_last_segments


async def _wire_onto_bare_app() -> dict[str, frozenset[str]]:
    # Imported here, not at module top: the routes tree pulls in the whole
    # composition root, and the readers that import this module must stay cheap
    # until a catalog is actually asked for.
    from fasthtml.common import fast_app

    from scripts.dev import bootstrap

    app, rt = fast_app(pico=False, live=False)
    services = MagicMock()
    init_ok = AsyncMock(return_value=MagicMock(is_error=False))
    sink = io.StringIO()
    # The route modules log every registration at INFO through structlog's default
    # print logger, and this catalog is built inside scripts whose stdout IS the
    # report — so the wiring runs with both streams captured.
    with (
        patch.object(bootstrap, "initialize_system_service", init_ok),
        contextlib.redirect_stdout(sink),
        contextlib.redirect_stderr(sink),
    ):
        await bootstrap._wire_all_routes(app, rt, services, MagicMock(), MagicMock())
    table: dict[str, frozenset[str]] = {}
    for route in app.routes:
        path = getattr(route, "path", None)
        if not path or CATCH_ALL_MARKER in path:
            continue
        verbs = frozenset(m.upper() for m in (getattr(route, "methods", None) or ()))
        table[path] = table.get(path, frozenset()) | verbs
    return table


@cache
def runtime_route_table() -> dict[str, frozenset[str]]:
    """Every path the application registers, with its HTTP methods, by wiring the
    real route tree.

    Union over intelligence tiers (every service is a truthy mock), root static
    catch-all stripped as bootstrap strips it, cached for the process. No database,
    no credentials, no environment: the wiring needs none of them.
    """
    return asyncio.run(_wire_onto_bare_app())


def runtime_route_paths() -> frozenset[str]:
    """The registered paths alone — the subset test's view of the table."""
    return frozenset(runtime_route_table())


@cache
def runtime_catalog() -> RouteCatalog:
    """The one catalog both readers consume."""
    return RouteCatalog(runtime_route_table())


def _decorator_callee(func: ast.expr) -> str:
    """Name of the thing being called — `rt` in `@rt(...)`, `route` in `@app.route(...)`."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def ast_route_paths(inbound_dir: Path | None = None) -> frozenset[str]:
    """String-literal route paths under a routes tree — the STATIC view.

    Kept for one consumer: the subset assertion in ``test_route_catalog.py``. A reader
    that consulted this would report every factory-registered route as fiction (the
    module docstring has the measured gap). AST rather than grep because the other
    ``@rt(`` occurrences in the repo are docstring examples and test fixtures.
    """
    inbound_dir = inbound_dir if inbound_dir is not None else ROOT / "adapters" / "inbound"
    paths: set[str] = set()
    if not inbound_dir.exists():
        return frozenset()
    for py_file in sorted(inbound_dir.rglob("*.py")):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except OSError, SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _decorator_callee(node.func) not in ROUTE_DECORATORS:
                continue
            first = node.args[0] if node.args else None
            if (
                isinstance(first, ast.Constant)
                and isinstance(first.value, str)
                and first.value.startswith("/")
            ):
                paths.add(first.value)
    return frozenset(paths)
