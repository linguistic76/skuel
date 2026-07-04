"""Regression tests for header hygiene at the Result[T] → HTTP boundary.

Pins the Arc-Care/Arc-F fixes in ``adapters/inbound/boundary.py``:

* ``_header_safe`` — X-Toast-Message values containing newlines (multi-line
  Pydantic validation messages) used to make uvicorn drop the connection
  with NO response ("Invalid HTTP header value"). CR/LF and other control
  characters must collapse to spaces (tab is allowed per RFC 9110).
* Non-latin-1 characters (em-dash class, emoji) must degrade via
  ``'replace'`` instead of raising — one em-dash in an error message must
  cost a toast character, not the whole response.
* ``result_to_response`` — the end-to-end contract: a failed Result with a
  hostile message still produces a valid, single-line, latin-1-safe
  X-Toast-Message header plus X-Toast-Type=error and a 400-class status.
"""

from __future__ import annotations

from adapters.inbound.boundary import _header_safe, result_to_response
from core.utils.result_simplified import Errors, Result

# ============================================================================
# _header_safe — line folding + charset coercion
# ============================================================================


class TestHeaderSafeLineCollapse:
    def test_multiline_input_collapses_to_single_line(self) -> None:
        out = _header_safe("line1\nline2\r\nline3")

        assert "\n" not in out
        assert "\r" not in out
        # Content survives — only the separators are rewritten.
        assert "line1" in out
        assert "line2" in out
        assert "line3" in out

    def test_lone_carriage_return_collapses(self) -> None:
        out = _header_safe("before\rafter")

        assert "\r" not in out
        assert out == "before after"

    def test_control_chars_collapse_to_space(self) -> None:
        # \x0b (vertical tab) is a control char uvicorn also rejects.
        assert _header_safe("a\x0bb") == "a b"
        assert _header_safe("a\x00b\x1fc") == "a b c"

    def test_del_collapses_to_space(self) -> None:
        # DEL (\x7f) sits ABOVE space so a plain `ch >= " "` filter lets it
        # through, but it's a CTL in HTTP field-content (Kody #505).
        assert _header_safe("a\x7fb") == "a b"

    def test_tab_is_preserved(self) -> None:
        # RFC 9110 allows horizontal tab in field values; the implementation
        # deliberately keeps it.
        assert _header_safe("a\tb") == "a\tb"

    def test_plain_single_line_passes_through_unchanged(self) -> None:
        assert _header_safe("Task created successfully") == "Task created successfully"


class TestHeaderSafeLatin1Coercion:
    def test_em_dash_degrades_without_raising(self) -> None:
        out = _header_safe("cap reached — mark one as read")

        # Must be latin-1 encodable now (Starlette encodes headers latin-1).
        out.encode("latin-1")
        assert "cap reached" in out
        assert "mark one as read" in out

    def test_emoji_degrades_without_raising(self) -> None:
        out = _header_safe("done 🎉 nice")

        out.encode("latin-1")
        assert "done" in out
        assert "nice" in out

    def test_latin1_characters_survive(self) -> None:
        # Characters INSIDE latin-1 must not be mangled by the coercion.
        assert _header_safe("café naïve") == "café naïve"


# ============================================================================
# result_to_response — end-to-end toast-header contract
# ============================================================================


class TestResultToResponseToastHeaders:
    def test_multiline_non_latin1_validation_error_yields_safe_headers(self) -> None:
        result: Result[None] = Result.fail(Errors.validation("msg with\nnewline — dash"))

        response = result_to_response(result)

        toast = response.headers["X-Toast-Message"]
        assert "\n" not in toast
        assert "\r" not in toast
        # The raw header value must encode to latin-1 without error — this is
        # exactly what uvicorn does before writing the response.
        toast.encode("latin-1")
        # Message content survives the sanitization.
        assert "msg with" in toast
        assert "newline" in toast

        assert response.headers["X-Toast-Type"] == "error"
        assert 400 <= response.status_code < 500
        assert response.status_code == 400  # VALIDATION → 400

    def test_success_path_custom_headers_are_sanitized_too(self) -> None:
        result = Result.ok(
            {
                "ok": True,
                "_headers": {"X-Toast-Message": "saved\nwith — flair", "X-Toast-Type": "success"},
            }
        )

        response = result_to_response(result)

        toast = response.headers["X-Toast-Message"]
        assert "\n" not in toast
        toast.encode("latin-1")
        assert response.status_code == 200
