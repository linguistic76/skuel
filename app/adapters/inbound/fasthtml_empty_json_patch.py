"""Interim patch: tolerate an empty ``application/json`` body in FastHTML's ``parse_form``.

FastHTML's ``parse_form`` (``fasthtml/core.py``) runs for **every** route via
``_wrap_req`` to turn the request body into the param dict — *before* any handler or
decorator. It already guards an empty ``multipart/form-data`` body (returns
``FormData()``), but the ``application/json`` branch calls ``await req.json()``
directly, and Starlette's ``request.json()`` does ``json.loads(b"")`` →
``JSONDecodeError`` on an empty body. So a bodyless POST sent with
``Content-Type: application/json`` (common from HTTP clients/SDKs) 500s at the
framework level before reaching the route — e.g. ``POST /api/ps/{uid}/engage``,
which takes no body.

This shim mirrors FastHTML's *own* empty-multipart guard for the json case: an empty
json body becomes ``{}``. It delegates everything else to the original ``parse_form``.

It is the **same change proposed upstream** — see
``docs/upstream/FASTHTML_EMPTY_JSON_PARSE_FORM.md``. This is a deliberately temporary
monkeypatch of a dependency internal: **remove it once a FastHTML release carrying the
upstream fix is pinned**. ``tests/unit/test_fasthtml_empty_json_patch.py`` exercises the
real FastHTML request path, so if an upgrade changes that internal the test fails loudly
rather than silently reintroducing the 500.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import fasthtml.core as _fhcore

from core.utils.logging import get_logger

if TYPE_CHECKING:
    from starlette.requests import Request

logger = get_logger("skuel.fasthtml_patch")

# Captured at import time, before any patch is applied, so delegation hits the real one.
_original_parse_form = _fhcore.parse_form


async def _parse_form_empty_json_safe(req: Request) -> Any:
    """``parse_form`` with FastHTML's empty-body grace extended to ``application/json``."""
    ctype = req.headers.get("Content-Type", "")
    if ctype == "application/json" and not await req.body():
        return {}
    return await _original_parse_form(req)


def apply_empty_json_parse_form_patch() -> None:
    """Idempotently install the empty-json guard on ``fasthtml.core.parse_form``.

    ``_wrap_req`` resolves ``parse_form`` from the ``fasthtml.core`` module namespace at
    call time, so reassigning the module attribute is sufficient.
    """
    if _fhcore.parse_form is _parse_form_empty_json_safe:
        return
    _fhcore.parse_form = _parse_form_empty_json_safe
    logger.info(
        "Applied FastHTML parse_form empty-json guard (interim; see docs/upstream/"
        "FASTHTML_EMPTY_JSON_PARSE_FORM.md)"
    )
