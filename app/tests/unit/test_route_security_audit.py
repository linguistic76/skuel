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
