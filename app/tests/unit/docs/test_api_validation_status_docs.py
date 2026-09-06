"""Pin API_VALIDATION_PATTERNS.md's HTTP-status claims to the live boundary.

Why this exists
---------------
A status column is a contract a client integrator branches on, so a wrong cell
sends someone to handle a status the app never emits. The guide's claims rest
on one fact: ``_get_status_for_error`` maps ``ErrorCategory.VALIDATION`` to 400,
and 422 belongs to ``BUSINESS`` — a well-formed request that breaks a domain
rule, which this guide does not cover.

So the columns are derived-checked, and by *driving the helper* rather than
reading its source: each documented row runs its real parser over input it must
reject and asserts the response ``result_to_response`` builds carries the
status the table claims. A row with no driver declares its documented status in
``_UNDRIVEN`` instead, which is checked the same way; a row that does neither
breaks the build.

``app/docs/patterns/API_VALIDATION_PATTERNS.md`` is in CI's ``py`` path filter
so a docs-only edit to a status cell still runs this module.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel, Field

from adapters.inbound.boundary import _get_status_for_error, result_to_response
from adapters.inbound.form_helpers import parse_form_body, parse_json_body
from adapters.inbound.route_factories import (
    parse_bool_query_param,
    parse_date_param_strict,
)
from core.utils.result_simplified import Errors, Result

_DOC = Path(__file__).resolve().parents[3] / "docs" / "patterns" / "API_VALIDATION_PATTERNS.md"
_TABLE_HEADING = "## When to Use Each Pattern"

# Rows the table documents but this module does not drive, each with the reason.
# A NEW row is neither driven nor listed, so it fails until someone decides which.
_UNDRIVEN = {
    # A classmethod on one search model, not a shared helper — nothing generic to drive.
    "HTML Form Params (GET)": "400",
    # "Avoid (SKUEL uses query params)" — the row exists to say the pattern is unused.
    "Path Params": "N/A",
}


class _Body(BaseModel):
    """Minimal schema whose only field rejects the input every driver sends."""

    reflection: str = Field(max_length=5)


class _JsonRequest:
    """Stands in for the JSON half of a Starlette request."""

    async def json(self) -> dict[str, str]:
        return {"reflection": "x" * 10}


class _FormRequest:
    """Stands in for the form half of a Starlette request."""

    async def form(self) -> dict[str, str]:
        return {"reflection": "x" * 10}


def _documented_rows() -> dict[str, str]:
    """Parse the guide's table into {input type: documented HTTP status}."""
    text = _DOC.read_text(encoding="utf-8")
    body = text[text.index(_TABLE_HEADING) :]
    rows: dict[str, str] = {}
    for line in body.splitlines():
        if not line.startswith("|"):
            if rows:
                break  # the table ended
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 4 or cells[0] in {"Input Type", ""} or set(cells[1]) <= {"-"}:
            continue
        rows[cells[0].strip("*").strip()] = cells[2]
    return rows


async def _status_of[T](result: Result[T]) -> int:
    """The HTTP status a failed Result actually reaches the client with."""
    assert result.is_error, "driver input was accepted — it must be rejected to have a status"
    return result_to_response(result).status_code


def test_status_map_reserves_422_for_business() -> None:
    """The premise the whole guide rests on: validation is 400, 422 is BUSINESS."""
    assert _get_status_for_error(Errors.validation("bad input")) == 400
    assert _get_status_for_error(Errors.business("rule", "rule violated")) == 422


def test_every_table_row_is_driven_or_declared_undriven() -> None:
    """A new row must arrive with a driver or an explicit reason it has none."""
    documented = _documented_rows()
    assert documented, "the When to Use Each Pattern table went missing or changed shape"

    driven = {
        "Query Params (GET)",
        "Required Params (GET)",
        "JSON Bodies (POST/PUT)",
        "Form Data Bodies (POST)",
    }
    assert set(documented) == driven | set(_UNDRIVEN)

    # An undriven row still has a documented status, and nothing else pins it —
    # the 422 scan passes on a 401 just as happily. Its declared value is the pin.
    assert {row: documented[row] for row in _UNDRIVEN} == _UNDRIVEN


@pytest.mark.parametrize("row", ["JSON Bodies (POST/PUT)", "Form Data Bodies (POST)"])
@pytest.mark.asyncio
async def test_body_helpers_return_the_documented_status(row: str) -> None:
    """Both body doors reject into the status the table claims — not 422."""
    parse = parse_json_body if row.startswith("JSON") else parse_form_body
    request = _JsonRequest() if row.startswith("JSON") else _FormRequest()

    status = await _status_of(await parse(request, _Body))  # type: ignore[arg-type]

    assert str(status) == _documented_rows()[row]


@pytest.mark.asyncio
async def test_strict_query_helper_returns_the_documented_status() -> None:
    """The strict helpers' row — a rejected required param."""
    status = await _status_of(parse_date_param_strict("not-a-date", "start_date"))

    assert str(status) == _documented_rows()["Required Params (GET)"]


def test_silent_query_helper_never_errors() -> None:
    """The silent helpers' row claims 200: unparseable input yields a value, not an error.

    Not the *default* — an unrecognised string is falsy, and only a missing or
    blank param falls back. Either way nothing reaches ``result_to_response``,
    which is what the row's "200" is claiming.
    """
    assert parse_bool_query_param({"flag": "garbage"}, "flag", default=True) is False
    assert parse_bool_query_param({}, "flag", default=True) is True
    assert _documented_rows()["Query Params (GET)"] == "200 (default)"


def _units(text: str) -> list[str]:
    """Prose paragraphs, with each table row its own unit.

    Line granularity is wrong here: a sentence that names 422 and the category
    that owns it wraps across two lines, so a line scan reports its own
    correction as an offence. A table row is scanned alone because the rows
    around it make no claim about it.
    """
    units: list[str] = []
    buffer: list[str] = []
    for line in text.splitlines():
        if line.startswith("|"):
            if buffer:
                units.append(" ".join(buffer))
                buffer = []
            units.append(line)
        elif line.strip():
            buffer.append(line.strip())
        elif buffer:
            units.append(" ".join(buffer))
            buffer = []
    if buffer:
        units.append(" ".join(buffer))
    return units


def test_guide_claims_no_422_for_a_validation_failure() -> None:
    """The regression this module exists for: no 422 attached to a rejected input.

    The guide covers validation only, so its every legitimate mention of 422
    is the sentence naming the category that owns it instead.
    """
    offenders = [
        u for u in _units(_DOC.read_text(encoding="utf-8")) if "422" in u and "BUSINESS" not in u
    ]

    assert offenders == [], f"422 claimed outside a BUSINESS context: {offenders}"
