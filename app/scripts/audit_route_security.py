#!/usr/bin/env python3
"""
Route Security Audit
====================

Static audit of every ``@rt(...)`` route handler in ``adapters/inbound/`` for
three classes of gap on **state-changing** endpoints:

1. **CSRF** — a mutation handler that lacks the ``@csrf_protected`` decorator.
2. **Auth** — a mutation handler with no authentication marker (no ``@require_*``
   role decorator and no call to ``require_authenticated_user`` /
   ``verify_entity_ownership`` / ``require_owned_entity`` in its body). A
   ``current_user`` parameter is not a marker: it is the slot the role
   decorator fills, and on a handler without the decorator it holds nothing.
3. **Method** — a write that a safe method reaches. ``@rt(path)`` with no
   ``methods=`` answers GET, HEAD and POST, and ``@csrf_protected`` lets GET /
   HEAD / OPTIONS through unchecked by design — so a write registered that way
   runs on a link, an image URL or a prefetch, with the viewer's session and no
   token. A ``@csrf_protected`` handler, and any registration whose path ends in
   ``/create``, ``/update`` or ``/delete`` (the CRUD factory's writes, applied as
   ``rt(path, methods=["POST"])(handler)``), must name its methods and name no
   safe one — named as a list of string literals: a ``methods=`` the scanner
   cannot read (a name, a call) is a gap, not a pass. Enforced on both spellings —
   the decorator and the call. A UI page
   at ``/{domain}/create`` (the form, ``methods=["GET"]``) is outside ``/api/``
   and is a read.

**Why this exists.** Route factories (CRUD / Status / Analytics / lateral) bake
in both ``@csrf_protected`` and auth, so the risk lives in hand-written ``@rt``
handlers. An earlier ad-hoc sweep keyed mutation detection on the
``methods=["POST"]`` kwarg and silently skipped the ~335 handlers registered as
bare ``@rt(path)`` (no ``methods=``) — yet those still accept form POSTs. This
script fixes that blind spot.

**What counts as a mutation (the gate).** A handler declares a mutating HTTP
method (``POST``/``PUT``/``DELETE``/``PATCH``) **or** reads a request body —
form (``request.form()`` / ``parse_form_body``)
**or** JSON (``request.json()`` / ``parse_json_body``) — regardless of the
``methods=`` kwarg. JSON endpoints are harder to exploit via classic form-CSRF
(a cross-site ``<form>`` can't set ``application/json``), but Starlette parses a
JSON body regardless of content-type, and SKUEL's convention is defense-in-depth
(factories CSRF-protect JSON mutations too), so they are gated. Genuinely
programmatic JSON endpoints (CLI/service-to-service clients that can't send a
token) are listed in ``CSRF_EXEMPT`` with a reason.

**``--form-only``** narrows the scan to form+methods mutations (excludes
``request.json()``/``parse_json_body``) — the classic-CSRF-exploitable subset.

**Limitations.** Auth detection is intra-procedural: a handler that authenticates
only via a *helper* it calls (rather than a direct ``require_authenticated_user``)
reads as a gap and must be listed in
``AUTH_EXEMPT``. Genuinely anonymous mutations (login, register) and public
reads-via-POST (curriculum filters) likewise live in the exemption tables with a
stated reason, so CI stays green without hiding real regressions.

Usage:
    uv run python scripts/audit_route_security.py            # CI gate: exit 1 on any gap
    uv run python scripts/audit_route_security.py --verbose  # list every mutation handler
    uv run python scripts/audit_route_security.py --form-only # narrow to form+methods
    uv run python scripts/audit_route_security.py --list-exempt

Exit codes: 0 = clean, 1 = one or more non-exempt gaps found.
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

from core.utils.terminal_colors import Colors

ROOT = Path(__file__).resolve().parent.parent  # /home/mike/skuel/app
SCAN_DIR = ROOT / "adapters" / "inbound"

MUT_METHODS = {"POST", "PUT", "DELETE", "PATCH"}
# The methods csrf_protected passes through unchecked — a write must answer none of them.
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
# An API path ending here is a write whatever decorates its handler (the CRUD
# factory's create / update / delete are applied as calls, so no decorator marks
# them). A UI page at /{domain}/create is a GET-only read — the form — not a write.
WRITE_SUFFIXES = ("/create", "/update", "/delete")
API_PREFIX = "/api/"
ROUTE_DECORATORS = {"rt", "route"}
CSRF_DECORATOR = "csrf_protected"
ROLE_DECORATORS = {"require_admin", "require_teacher", "require_role"}
AUTH_CALLS = {"require_authenticated_user", "verify_entity_ownership", "require_owned_entity"}
FORM_HELPERS = {"parse_form_body"}
JSON_HELPERS = {"parse_json_body"}

# ── Intentional exemptions ───────────────────────────────────────────────────
# (filename, function_name) -> reason. Keep these few and justified; an entry
# whose handler no longer exists is reported as stale so the tables don't rot.

AUTH_EXEMPT: dict[tuple[str, str], str] = {
    ("auth_ui.py", "register_submit"): "registration must be anonymous",
    ("auth_ui.py", "login_submit"): "login must be anonymous",
    ("auth_ui.py", "forgot_password_submit"): "password-reset request must be anonymous",
    ("auth_ui.py", "reset_password_submit"): "reset is authorized by a token, not a session",
    ("pathways_ui.py", "filter_learning_paths"): "public-curriculum read (LP browse filter)",
    ("device_routes.py", "enroll_device_api"): (
        "agent enrollment is sessionless by design — the one-time pairing code "
        "IS the credential (hashed, 10-min TTL, single-use burn; ADR-075)"
    ),
}

# These programmatic clients can't send a CSRF token. The device-pairing entry is
# permanent by design (sessionless one-time pairing code, ADR-075); any NEW
# programmatic client takes the bearer-token path instead of an entry here — see
# docs/roadmap/programmatic-client-auth-csrf.md. test_route_security_audit.py
# asserts the exact table contents, so adding an entry is a deliberate ruling
# (update the tripwire in the same change), never a drive-by.
CSRF_EXEMPT: dict[tuple[str, str], str] = {
    ("device_routes.py", "enroll_device_api"): (
        "programmatic JSON endpoint for the vault agent: no session, no cookies, "
        "so there is nothing for cross-site requests to ride on; authenticated by "
        "the one-time pairing code + IP rate-limited (ADR-075)"
    ),
}


@dataclass(frozen=True)
class Handler:
    file: str
    lineno: int
    name: str
    has_csrf: bool
    has_auth: bool
    signal: str  # why we consider it a mutation (empty string = not a mutation)
    path: str | None  # the @rt(...) path string, when a string literal
    claims_post: bool  # True if this registration accepts POST (explicit or by default)
    has_methods_kwarg: bool  # True if the @rt(...) call names methods= at all
    methods: frozenset[str]  # the methods named (empty when none are)
    methods_literal: bool  # True if methods= is a list/tuple of string literals the scanner reads

    @property
    def is_mutation(self) -> bool:
        return bool(self.signal)

    @property
    def is_write_by_path(self) -> bool:
        return (
            self.path is not None
            and self.path.startswith(API_PREFIX)
            and self.path.endswith(WRITE_SUFFIXES)
        )

    @property
    def reachable_by_safe_method(self) -> bool:
        """A write a GET reaches: no ``methods=``, one the scanner cannot read (a name,
        a call — fail closed), an empty one (the default registration), or one naming
        a safe method in any case."""
        return _reachable_by_safe_method(self.has_methods_kwarg, self.methods_literal, self.methods)


def _reachable_by_safe_method(
    has_methods_kwarg: bool, methods_literal: bool, methods: frozenset[str]
) -> bool:
    # An empty literal is FastHTML's default registration (GET, HEAD and POST) —
    # ``if methods:`` — so it is a gap like no kwarg at all.
    return (
        not has_methods_kwarg or not methods_literal or not methods or bool(methods & SAFE_METHODS)
    )


@dataclass(frozen=True)
class CallRegistration:
    """A route applied as a call — ``rt(path)(handler)`` — rather than a decorator."""

    file: str
    lineno: int
    path_source: str  # the first argument as written (an f-string stays an f-string)
    has_methods_kwarg: bool
    methods: frozenset[str]
    methods_literal: bool

    @property
    def is_write_by_path(self) -> bool:
        """A computed path ending in a write suffix (``f"{base_path}/delete"``) is a factory write."""
        return self.path_source.rstrip("\"'").endswith(WRITE_SUFFIXES)

    @property
    def reachable_by_safe_method(self) -> bool:
        return _reachable_by_safe_method(self.has_methods_kwarg, self.methods_literal, self.methods)


def _by_location(h: Handler) -> tuple[str, int]:
    """Sort key: order handlers by file, then line number."""
    return (h.file, h.lineno)


def _decorator_name(
    d: ast.expr,
) -> tuple[str | None, bool, list[ast.keyword], list[ast.expr]]:
    if isinstance(d, ast.Call):
        f = d.func
        name = f.id if isinstance(f, ast.Name) else getattr(f, "attr", None)
        return name, True, d.keywords, d.args
    if isinstance(d, ast.Name):
        return d.id, False, [], []
    if isinstance(d, ast.Attribute):
        return d.attr, False, [], []
    return None, False, [], []


def _route_path(args: list[ast.expr]) -> str | None:
    """Return the first positional arg of an @rt(...) call when it is a string."""
    if args and isinstance(args[0], ast.Constant) and isinstance(args[0].value, str):
        return args[0].value
    return None


def _methods_kwarg(keywords: list[ast.keyword]) -> frozenset[str]:
    """The string literals named, uppercased as FastHTML registers them (``"get"`` is GET)."""
    for kw in keywords:
        if kw.arg == "methods" and isinstance(kw.value, ast.List | ast.Tuple):
            return frozenset(
                e.value.upper()
                for e in kw.value.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            )
    return frozenset()


def _methods_literal(keywords: list[ast.keyword]) -> bool:
    """True when ``methods=`` is a list/tuple of string literals — the one spelling the
    scanner reads. A name or a call (``methods=WRITE_METHODS``) is unread, and a write
    carrying it is judged a gap rather than trusted."""
    for kw in keywords:
        if kw.arg == "methods":
            return isinstance(kw.value, ast.List | ast.Tuple) and all(
                isinstance(e, ast.Constant) and isinstance(e.value, str) for e in kw.value.elts
            )
    return False


def _body_signal(node: ast.AST, include_json: bool) -> str | None:
    """Return a short reason if the function reads a request body, else None."""
    for x in ast.walk(node):
        if not isinstance(x, ast.Call):
            continue
        f = x.func
        if (
            isinstance(f, ast.Attribute)
            and isinstance(f.value, ast.Name)
            and f.value.id == "request"
        ):
            if f.attr == "form":
                return "reads request.form()"
            if f.attr == "json" and include_json:
                return "reads request.json()"
        name = f.id if isinstance(f, ast.Name) else getattr(f, "attr", None)
        if name in FORM_HELPERS:
            return f"calls {name}()"
        if name in JSON_HELPERS and include_json:
            return f"calls {name}()"
    return None


def _has_auth(node: ast.AsyncFunctionDef | ast.FunctionDef) -> bool:
    for x in ast.walk(node):
        if isinstance(x, ast.Call):
            f = x.func
            name = f.id if isinstance(f, ast.Name) else getattr(f, "attr", None)
            if name in AUTH_CALLS:
                return True
    return False


def _analyze(
    node: ast.AsyncFunctionDef | ast.FunctionDef, filename: str, include_json: bool
) -> Handler | None:
    has_rt = False
    has_methods_kwarg = False
    methods_literal = False
    methods: frozenset[str] = frozenset()
    path: str | None = None
    has_csrf = False
    has_role = False
    for d in node.decorator_list:
        name, is_call, kwargs, args = _decorator_name(d)
        if name in ROUTE_DECORATORS and is_call:
            has_rt = True
            methods = _methods_kwarg(kwargs)
            has_methods_kwarg = any(kw.arg == "methods" for kw in kwargs)
            methods_literal = _methods_literal(kwargs)
            path = _route_path(args)
        elif name == CSRF_DECORATOR:
            has_csrf = True
        elif name in ROLE_DECORATORS:
            has_role = True
    if not has_rt:
        return None

    if methods & MUT_METHODS:
        signal = "methods=" + ",".join(sorted(methods & MUT_METHODS))
    else:
        signal = _body_signal(node, include_json) or ""

    # A registration accepts POST if it names POST explicitly, OR if it carries
    # no methods= kwarg at all (FastHTML's @rt default is GET+POST). Two POST-
    # claiming registrations on the same path shadow each other (Starlette
    # first-match wins) — see _collision_gaps.
    claims_post = ("POST" in methods) if has_methods_kwarg else True

    return Handler(
        file=filename,
        lineno=node.lineno,
        name=node.name,
        has_csrf=has_csrf,
        has_auth=has_role or _has_auth(node),
        signal=signal,
        path=path,
        claims_post=claims_post,
        has_methods_kwarg=has_methods_kwarg,
        methods=methods,
        methods_literal=methods_literal,
    )


def collect_handlers(scan_dir: Path, include_json: bool) -> list[Handler]:
    handlers: list[Handler] = []
    for path in sorted(scan_dir.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            # Fail closed: a syntax-broken module must not be silently skipped,
            # or the audit (and its unit guard) would pass on a partial tree.
            print(f"{Colors.RED}parse error: {path}: {exc}{Colors.RESET}", file=sys.stderr)
            raise
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
                h = _analyze(node, path.name, include_json)
                if h is not None:
                    handlers.append(h)
    return handlers


def collect_call_registrations(scan_dir: Path) -> list[CallRegistration]:
    """Every ``rt(path, ...)(handler)`` registration — the route factories' spelling."""
    found: list[CallRegistration] = []
    for path in sorted(scan_dir.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Call):
                continue
            inner = node.func
            name = inner.func.id if isinstance(inner.func, ast.Name) else None
            if name not in ROUTE_DECORATORS or not inner.args:
                continue
            found.append(
                CallRegistration(
                    file=path.name,
                    lineno=node.lineno,
                    path_source=ast.unparse(inner.args[0]),
                    has_methods_kwarg=any(kw.arg == "methods" for kw in inner.keywords),
                    methods=_methods_kwarg(inner.keywords),
                    methods_literal=_methods_literal(inner.keywords),
                )
            )
    return found


def write_method_gaps(
    handlers: list[Handler], registrations: list[CallRegistration]
) -> list[tuple[str, int, str]]:
    """Writes a safe method reaches, as ``(file, lineno, what)`` rows.

    A write is a ``@csrf_protected`` handler, a literal ``/api/`` path ending in a
    ``WRITE_SUFFIXES`` entry, or a computed factory path ending in one; it gaps
    when it names no ``methods=``, names one the scanner cannot read, or names a
    ``SAFE_METHODS`` member.
    """
    decorated = [
        (h.file, h.lineno, h.name)
        for h in handlers
        if (h.has_csrf or h.is_write_by_path) and h.reachable_by_safe_method
    ]
    applied = [
        (r.file, r.lineno, f"rt({r.path_source})(...)")
        for r in registrations
        if r.is_write_by_path and r.reachable_by_safe_method
    ]
    return sorted(decorated + applied)


def collision_gaps(handlers: list[Handler]) -> list[tuple[str, list[Handler]]]:
    """Find paths where two or more @rt registrations both claim POST.

    FastHTML's ``@rt(path)`` with no ``methods=`` registers BOTH GET and POST.
    Starlette matches the first-registered route for a given path+method, so a
    page/reader handler declared first as bare ``@rt(path)`` silently SHADOWS a
    later ``@rt(path, methods=["POST"])`` + ``@csrf_protected`` submit handler:
    the submit never runs and its CSRF gate is bypassed. The fix is to make the
    page/reader handler GET-only (``methods=["GET"]``) so exactly one
    registration per path claims POST.

    Structural (registration-based), no flow analysis: group by path string,
    flag any path with >1 POST-claiming registration.
    """
    by_path: dict[str, list[Handler]] = {}
    for h in handlers:
        if h.path is not None and h.claims_post:
            by_path.setdefault(h.path, []).append(h)
    return sorted((p, hs) for p, hs in by_path.items() if len(hs) > 1)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit @rt route handlers for CSRF, auth and write-method gaps."
    )
    parser.add_argument("--verbose", action="store_true", help="List every mutation handler.")
    parser.add_argument(
        "--form-only",
        action="store_true",
        help="Narrow to form+methods mutations (exclude request.json()/parse_json_body).",
    )
    parser.add_argument("--list-exempt", action="store_true", help="Print the exemption tables.")
    args = parser.parse_args()

    if args.list_exempt:
        print(f"{Colors.BOLD}AUTH_EXEMPT{Colors.RESET}")
        for (f, fn), why in sorted(AUTH_EXEMPT.items()):
            print(f"  {f}:{fn} — {why}")
        print(f"{Colors.BOLD}CSRF_EXEMPT{Colors.RESET}")
        for (f, fn), why in sorted(CSRF_EXEMPT.items()):
            print(f"  {f}:{fn} — {why}")
        return 0

    handlers = collect_handlers(SCAN_DIR, include_json=not args.form_only)
    mutations = [h for h in handlers if h.is_mutation]

    csrf_gaps = [h for h in mutations if not h.has_csrf and (h.file, h.name) not in CSRF_EXEMPT]
    auth_gaps = [h for h in mutations if not h.has_auth and (h.file, h.name) not in AUTH_EXEMPT]
    collisions = collision_gaps(handlers)
    method_gaps = write_method_gaps(handlers, collect_call_registrations(SCAN_DIR))

    seen = {(h.file, h.name) for h in handlers}
    stale = sorted(k for k in (AUTH_EXEMPT.keys() | CSRF_EXEMPT.keys()) if k not in seen)

    mode = "form+methods" if args.form_only else "form+methods+json"
    print(
        f"{Colors.BOLD}{Colors.CYAN}Route Security Audit{Colors.RESET}  ({SCAN_DIR.relative_to(ROOT)}, mode={mode})"
    )
    print(
        f"  scanned {len(handlers)} @rt handlers · "
        f"{len(mutations)} mutations · "
        f"{len(AUTH_EXEMPT) + len(CSRF_EXEMPT)} exemptions"
    )

    if args.verbose:
        print(f"\n{Colors.BOLD}Mutation handlers:{Colors.RESET}")
        for h in sorted(mutations, key=_by_location):
            csrf = (
                f"{Colors.GREEN}csrf{Colors.RESET}"
                if h.has_csrf
                else f"{Colors.RED}NO-csrf{Colors.RESET}"
            )
            auth = (
                f"{Colors.GREEN}auth{Colors.RESET}"
                if h.has_auth
                else f"{Colors.YELLOW}no-auth{Colors.RESET}"
            )
            print(f"  {h.file}:{h.lineno} {h.name}  [{h.signal}]  {csrf} {auth}")

    if csrf_gaps:
        print(
            f"\n{Colors.RED}{Colors.BOLD}✗ CSRF gaps ({len(csrf_gaps)}):{Colors.RESET} add @csrf_protected"
        )
        for h in sorted(csrf_gaps, key=_by_location):
            print(f"  {h.file}:{h.lineno} {h.name}  [{h.signal}]")

    if auth_gaps:
        print(
            f"\n{Colors.RED}{Colors.BOLD}✗ Auth gaps ({len(auth_gaps)}):{Colors.RESET} add auth, or exempt with a reason"
        )
        for h in sorted(auth_gaps, key=_by_location):
            print(f"  {h.file}:{h.lineno} {h.name}  [{h.signal}]")

    if collisions:
        print(
            f"\n{Colors.RED}{Colors.BOLD}✗ POST shadowing collisions ({len(collisions)}):{Colors.RESET} "
            'make the page/reader handler GET-only (methods=["GET"])'
        )
        for path, hs in collisions:
            who = ", ".join(f"{h.file}:{h.lineno} {h.name}" for h in sorted(hs, key=_by_location))
            print(f"  {path}  ←  {who}")

    if method_gaps:
        print(
            f"\n{Colors.RED}{Colors.BOLD}✗ Writes a safe method reaches ({len(method_gaps)}):{Colors.RESET} "
            'declare methods=["POST"] (or the route\'s unsafe verb) — never GET / HEAD / OPTIONS'
        )
        for file, lineno, what in method_gaps:
            print(f"  {file}:{lineno} {what}")

    if stale:
        print(
            f"\n{Colors.YELLOW}⚠ stale exemptions (handler renamed/removed — clean up the table):{Colors.RESET}"
        )
        for f, fn in stale:
            print(f"  {f}:{fn}")

    if csrf_gaps or auth_gaps or collisions or method_gaps:
        print(
            f"\n{Colors.RED}{Colors.BOLD}FAILED{Colors.RESET} — fix the handler, or if intentional add it to the "
            f"exemption table in {Path(__file__).name} with a reason."
        )
        return 1

    print(
        f"\n{Colors.GREEN}{Colors.BOLD}✓ PASSED{Colors.RESET} — every {mode} mutation handler is "
        "CSRF-protected and authenticated, no path has shadowed POST registrations, "
        "and no write answers a safe method."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
