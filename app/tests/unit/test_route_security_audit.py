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
collect_call_registrations = _audit.collect_call_registrations
collect_handlers = _audit.collect_handlers
collision_gaps = _audit.collision_gaps
write_method_gaps = _audit.write_method_gaps


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


# ── A write answers no safe method ───────────────────────────────────────────
# @rt(path) with no methods= answers GET, HEAD and POST, and @csrf_protected lets
# GET / HEAD / OPTIONS through unchecked — so a write registered that way runs
# on a link, an image URL or a prefetch with the viewer's session and no token.
# write_method_gaps() flags a @csrf_protected handler, a literal /api/ path ending
# in /create, /update or /delete, a computed factory path ending in one, or a call
# registration wrapping csrf_protected(...), that names no methods=, names one the
# scanner cannot read, or names a safe method.


def _gaps_in(tmp_path: Path, source: str) -> list[str]:
    (tmp_path / "mod.py").write_text(textwrap.dedent(source), encoding="utf-8")
    handlers = collect_handlers(tmp_path, include_json=True)
    registrations = collect_call_registrations(tmp_path)
    return [what for _file, _lineno, what in write_method_gaps(handlers, registrations)]


def test_no_write_reachable_by_safe_method_in_tree() -> None:
    gaps = write_method_gaps(
        collect_handlers(SCAN_DIR, include_json=True), collect_call_registrations(SCAN_DIR)
    )
    assert not gaps, f"writes a GET reaches (declare methods=['POST']): {gaps}"


def test_scanner_sees_the_crud_factory_writes() -> None:
    # Positive control for the call spelling: the CRUD factory applies its three
    # writes as rt(f"{base_path}/<write>", methods=["POST"])(handler). A scanner
    # that stopped seeing them would pass the tree test vacuously.
    writes = [r for r in collect_call_registrations(SCAN_DIR) if r.is_write_by_path]
    assert {r.path_source.rsplit("/", 1)[1].rstrip("'\"") for r in writes} >= {
        "create",
        "update",
        "delete",
    }
    assert all(r.methods == frozenset({"POST"}) for r in writes), writes


def test_scanner_sees_the_csrf_wrapped_call_registrations() -> None:
    # Positive control for the wrapped spelling — rt(path, methods=["POST"])
    # (csrf_protected(handler)) — the AI, field, link and hierarchy factories use.
    wrapped = {r.file for r in collect_call_registrations(SCAN_DIR) if r.has_csrf}
    assert wrapped >= {
        "ai_routes.py",
        "activity_field_api_factory.py",
        "activity_link_api_factory.py",
        "hierarchy_api_factory.py",
    }


def test_csrf_wrapped_call_registration_without_methods_is_a_gap(tmp_path: Path) -> None:
    # A variable path says nothing; the csrf_protected(...) wrap says write.
    assert _gaps_in(
        tmp_path,
        """
        def register(rt, path, handler):
            rt(path)(csrf_protected(handler))
            rt(path, methods=["GET", "POST"])(csrf_protected(boundary_handler()(handler)))
            rt(path, methods=["POST"])(csrf_protected(handler))
            rt(path)(boundary_handler()(handler))
        """,
    ) == ["rt(path)(...)", "rt(path)(...)"]


def test_csrf_handler_without_methods_is_a_gap(tmp_path: Path) -> None:
    assert _gaps_in(
        tmp_path,
        """
        def make(rt):
            @rt("/settings/save")
            @csrf_protected
            async def save_settings(request):
                return "saved"
        """,
    ) == ["save_settings"]


def test_csrf_handler_naming_a_safe_method_is_a_gap(tmp_path: Path) -> None:
    assert _gaps_in(
        tmp_path,
        """
        def make(rt):
            @rt("/settings/save", methods=["GET", "POST"])
            @csrf_protected
            async def save_settings(request):
                return "saved"
        """,
    ) == ["save_settings"]


def test_csrf_handler_with_unread_methods_is_a_gap(tmp_path: Path) -> None:
    # Fail closed: a methods= the scanner cannot read (a name, a call) is not a pass.
    assert _gaps_in(
        tmp_path,
        """
        def make(rt):
            @rt("/settings/save", methods=WRITE_METHODS)
            @csrf_protected
            async def save_settings(request):
                return "saved"

            @rt("/settings/reset", methods=[verb])
            @csrf_protected
            async def reset_settings(request):
                return "reset"

        class Factory:
            def register(self, rt):
                rt(f"{self.base_path}/delete", methods=self.write_methods)(self.delete)
        """,
    ) == ["save_settings", "reset_settings", "rt(f'{self.base_path}/delete')(...)"]


def test_csrf_handler_with_empty_or_lowercase_methods_is_a_gap(tmp_path: Path) -> None:
    # FastHTML registers methods=[] as its default (GET, HEAD and POST) and
    # uppercases names — "get" is GET. Both spellings are gaps.
    assert _gaps_in(
        tmp_path,
        """
        def make(rt):
            @rt("/settings/save", methods=[])
            @csrf_protected
            async def save_settings(request):
                return "saved"

            @rt("/settings/reset", methods=["get", "post"])
            @csrf_protected
            async def reset_settings(request):
                return "reset"

            @rt("/settings/clear", methods=["post"])
            @csrf_protected
            async def clear_settings(request):
                return "cleared"
        """,
    ) == ["save_settings", "reset_settings"]


def test_csrf_handler_on_post_is_clean(tmp_path: Path) -> None:
    assert (
        _gaps_in(
            tmp_path,
            """
            def make(rt):
                @rt("/settings/save", methods=["POST"])
                @csrf_protected
                async def save_settings(request):
                    return "saved"

                @rt("/api/path-steps/tags", methods=["DELETE", "POST"])
                @csrf_protected
                async def tags_route(request):
                    return "ok"
            """,
        )
        == []
    )


def test_api_write_path_without_methods_is_a_gap_even_without_csrf(tmp_path: Path) -> None:
    # The path says write; a missing @csrf_protected is the CSRF gap's business,
    # the missing methods= is this one's.
    assert _gaps_in(
        tmp_path,
        """
        def make(rt):
            @rt("/api/things/delete")
            async def delete_thing(request, uid: str):
                return "gone"
        """,
    ) == ["delete_thing"]


def test_ui_create_page_on_get_is_a_read(tmp_path: Path) -> None:
    # /tasks/create is the new-task FORM — a GET-only read outside /api/.
    assert (
        _gaps_in(
            tmp_path,
            """
            def make(rt):
                @rt("/tasks/create", methods=["GET"])
                def task_create_page(request):
                    return "form"
            """,
        )
        == []
    )


def test_factory_call_write_without_methods_is_a_gap(tmp_path: Path) -> None:
    assert _gaps_in(
        tmp_path,
        """
        class Factory:
            def register(self, rt):
                rt(f"{self.base_path}/delete")(self.delete)
                rt(f"{self.base_path}/list")(self.list)
        """,
    ) == ["rt(f'{self.base_path}/delete')(...)"]


def test_factory_call_write_on_post_is_clean(tmp_path: Path) -> None:
    assert (
        _gaps_in(
            tmp_path,
            """
            class Factory:
                def register(self, rt):
                    rt(f"{self.base_path}/delete", methods=["POST"])(self.delete)
                    rt(f"{self.base_path}/update", methods=["POST"])(self.update)
                    rt(f"{self.base_path}/create", methods=["POST"])(self.create)
            """,
        )
        == []
    )
