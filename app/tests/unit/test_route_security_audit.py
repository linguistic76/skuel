"""Route-security invariant guard.

Mirrors what ``scripts/audit_route_security.py`` gates in ``./dev quality``:
every hand-written ``@rt`` mutation handler (declares a mutating method, or
reads a form body) must be ``@csrf_protected`` and authenticated — unless it is
listed, with a reason, in the script's exemption tables.

This keeps the invariant enforced in the unit suite too, so a regression is
caught even if someone bypasses the quality runner. New intentional exceptions
go in ``AUTH_EXEMPT`` / ``CSRF_EXEMPT`` in the script (with a reason), not here.
"""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path

# scripts/ is not an importable package, so load the audit module by path.
_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "audit_route_security.py"
_spec = importlib.util.spec_from_file_location("audit_route_security", _SCRIPT)
assert _spec is not None and _spec.loader is not None
_audit = importlib.util.module_from_spec(_spec)
# Register before exec so the module's dataclasses can resolve their annotations
# (dataclasses looks the module up in sys.modules under __future__ annotations).
sys.modules[_spec.name] = _audit
_spec.loader.exec_module(_audit)

AUTH_EXEMPT = _audit.AUTH_EXEMPT
CSRF_EXEMPT = _audit.CSRF_EXEMPT
SCAN_DIR = _audit.SCAN_DIR
collect_handlers = _audit.collect_handlers
collision_gaps = _audit.collision_gaps


def _mutations():
    return [h for h in collect_handlers(SCAN_DIR, include_json=True) if h.is_mutation]


def test_finds_mutation_handlers() -> None:
    # Sanity: the scanner is actually seeing handlers (guards against a silent
    # detection regression that would make the audit vacuously pass).
    assert len(_mutations()) > 50


def test_no_csrf_gaps_on_mutation_handlers() -> None:
    gaps = [
        f"{h.file}:{h.lineno} {h.name}"
        for h in _mutations()
        if not h.has_csrf and (h.file, h.name) not in CSRF_EXEMPT
    ]
    assert not gaps, f"mutation handlers missing @csrf_protected: {gaps}"


def test_no_auth_gaps_on_mutation_handlers() -> None:
    gaps = [
        f"{h.file}:{h.lineno} {h.name}"
        for h in _mutations()
        if not h.has_auth and (h.file, h.name) not in AUTH_EXEMPT
    ]
    assert not gaps, f"mutation handlers missing authentication: {gaps}"


def test_no_stale_exemptions() -> None:
    # Every exemption must point at a real handler, so the tables don't rot.
    seen = {(h.file, h.name) for h in collect_handlers(SCAN_DIR, include_json=True)}
    stale = sorted(k for k in (AUTH_EXEMPT.keys() | CSRF_EXEMPT.keys()) if k not in seen)
    assert not stale, f"exemptions for handlers that no longer exist: {stale}"


def test_csrf_exempt_holds_exactly_the_by_design_entries() -> None:
    # Device-pairing enrollment is the SOLE sanctioned CSRF exemption — kept
    # exempt by design (sessionless one-time pairing code, ADR-075). A new
    # programmatic endpoint takes the bearer-token path instead
    # (docs/roadmap/programmatic-client-auth-csrf.md); adding an entry here
    # without that ruling converts an interim escape hatch back into the norm.
    assert set(CSRF_EXEMPT) == {("device_routes.py", "enroll_device_api")}


# ── POST shadowing-collision guard ───────────────────────────────────────────
# FastHTML's @rt(path) with no methods= registers BOTH GET and POST; Starlette
# matches the first-registered route, so a page handler declared first as bare
# @rt(path) shadows a later @rt(path, methods=["POST"]) + @csrf_protected submit
# (the submit never runs and its CSRF gate is bypassed). collision_gaps() flags
# any path with >1 POST-claiming registration.


def test_no_post_shadowing_collisions_in_tree() -> None:
    # The real adapters/inbound tree must have exactly one POST-claiming
    # registration per path — no page/reader handler shadowing a POST submit.
    collisions = collision_gaps(collect_handlers(SCAN_DIR, include_json=True))
    pretty = [f"{path}: {[f'{h.file}:{h.lineno} {h.name}' for h in hs]}" for path, hs in collisions]
    assert not collisions, f"shadowed POST registrations: {pretty}"


def _scan_source(tmp_path: Path, source: str) -> list:
    (tmp_path / "mod.py").write_text(textwrap.dedent(source), encoding="utf-8")
    return collect_handlers(tmp_path, include_json=True)


def test_collision_flagged_for_colliding_pair(tmp_path: Path) -> None:
    # Bare page handler registered first (defaults to GET+POST) + a real POST
    # submit on the SAME path → both claim POST → flagged.
    handlers = _scan_source(
        tmp_path,
        """
        def make(rt):
            @rt("/x/create")
            async def x_page(request):
                return "page"

            @rt("/x/create", methods=["POST"])
            @csrf_protected
            async def x_submit(request):
                return "submit"
        """,
    )
    collisions = collision_gaps(handlers)
    assert len(collisions) == 1
    path, hs = collisions[0]
    assert path == "/x/create"
    assert {h.name for h in hs} == {"x_page", "x_submit"}


def test_no_collision_for_clean_get_post_split(tmp_path: Path) -> None:
    # Page handler is explicitly GET-only → only the submit claims POST → clean.
    handlers = _scan_source(
        tmp_path,
        """
        def make(rt):
            @rt("/x/create", methods=["GET"])
            async def x_page(request):
                return "page"

            @rt("/x/create", methods=["POST"])
            @csrf_protected
            async def x_submit(request):
                return "submit"
        """,
    )
    assert collision_gaps(handlers) == []


def test_no_collision_for_distinct_paths(tmp_path: Path) -> None:
    # A GET page and a POST submit on DIFFERENT paths (login → /login/submit
    # pattern) never collide, even though the page handler defaults to GET+POST.
    handlers = _scan_source(
        tmp_path,
        """
        def make(rt):
            @rt("/login")
            async def login_page(request):
                return "page"

            @rt("/login/submit", methods=["POST"])
            @csrf_protected
            async def login_submit(request):
                return "submit"
        """,
    )
    assert collision_gaps(handlers) == []
