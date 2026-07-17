"""
Request-Scoped CSRF Token Context
==================================

The render surface of the double-submit CSRF defense. The inbound middleware
(`adapters/inbound/csrf.py`) sets the token here once per request; UI form
builders read it back without a plumbed ``request`` argument.

Lives in ``core/utils`` so the dependency arrows stay inward — the middleware
(adapters → core) writes, form components (ui → core) read. The enforcement
half (cookie minting, constant-time verify, ``@csrf_protected``,
``CSRFMiddleware``) stays at the inbound boundary; the hidden-input renderer
lives in ``ui/patterns/csrf.py``.

See: ``adapters/inbound/csrf.py`` module docstring for the full defense model.
"""

from contextvars import ContextVar

# Form field name mirrored by the enforcement side's form-body read
# (adapters/inbound/csrf.py::_read_submitted_token) and the HTMX header hook
# (static/js/skuel.js).
CSRF_FORM_FIELD = "csrf_token"

# Scope is per request/task — set (and reset) by CSRFMiddleware.dispatch.
csrf_token_var: ContextVar[str | None] = ContextVar("csrf_token_var", default=None)


def current_csrf_token() -> str | None:
    """Return the CSRF token for the in-flight request, or None if no middleware."""
    return csrf_token_var.get()
