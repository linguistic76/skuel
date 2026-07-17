"""CSRF hidden-input renderer for hand-built forms.

Presentation half of the double-submit defense: renders the request's token
(from ``core/utils/csrf_token_context``) as a hidden field. Enforcement lives
at the inbound boundary (``adapters/inbound/csrf.py``).
"""

from typing import Any

from fasthtml.common import Input

from core.utils.csrf_token_context import CSRF_FORM_FIELD, current_csrf_token


def csrf_hidden_input() -> Any:
    """Return a hidden <input name="csrf_token"> populated from the request context.

    Drop this as the first child of any hand-built ``Form()`` that posts to a
    ``@csrf_protected`` route. Forms routed through ``FormGenerator`` receive
    the field automatically — only hand-built forms (e.g., login/register)
    need this helper.
    """
    token = current_csrf_token() or ""
    return Input(type="hidden", name=CSRF_FORM_FIELD, value=token)
