"""Shared query-set field parsing for the eval instruments (``scripts/eval_*.py``).

Two hand-edited, reviewable YAML query sets gate two different measurements —
chunk retrieval (``eval_chunk_retrieval_queries.yaml``) and intent
classification (``eval_intent_classification_queries.yaml``) — and both carry
the same ratification contract: a run is DRAFT until ``ratified:`` holds a date,
and the FIRST ratified run IS the baseline.

Two field parses are therefore load-bearing in both files and must not drift
apart, so they live here once rather than as a copy:

- ``ratified`` must be UNFORGEABLE by a typo. ``ratified: yes`` is a YAML bool,
  and a lenient parse would coerce it into a truthy "ratified" string — quietly
  promoting a draft run to a baseline.
- an integer field must reject ``true``. ``bool`` subclasses ``int``, so
  ``k: true`` would otherwise pass an ``isinstance(raw, int)`` check and measure
  hit@1 (``best_rank <= True``) under the name of hit@5 (Codex, #1197).

Both raise ``ValueError`` with the offending file named — these sets are edited
by hand under review, and this validation is their only structural gate.
"""

from __future__ import annotations

from datetime import date

_RATIFIED_EXPECTATION = "must be null or an ISO date (YYYY-MM-DD)"


def parse_ratified_field(raw: object, where: str) -> str | None:
    """Parse a query set's ``ratified:`` field into an ISO date string or None.

    Only three inputs pass: null, a bare YAML date (which ``yaml.safe_load``
    hands over as ``datetime.date``), and a quoted ISO date string. Everything
    else — notably the YAML bools ``yes``/``true``/``on`` — is a loud error
    rather than a truthy value that would ratify a draft set.
    """
    if raw is None:
        return None
    if isinstance(raw, date):
        return raw.isoformat()
    if isinstance(raw, str):
        try:
            date.fromisoformat(raw)
        except ValueError:
            raise ValueError(f"{where}: 'ratified' {_RATIFIED_EXPECTATION}, got {raw!r}") from None
        return raw
    raise ValueError(f"{where}: 'ratified' {_RATIFIED_EXPECTATION}, got {raw!r}")


def parse_int_field(raw: object, where: str, name: str, *, minimum: int | None = None) -> int:
    """Parse an integer query-set field, rejecting bools and out-of-range values.

    ``minimum=1`` is spelled "a positive integer" in the message because that is
    what both sets' size fields mean; any other floor is stated numerically.
    """
    if minimum is None:
        expectation = "an integer"
    elif minimum == 1:
        expectation = "a positive integer"
    else:
        expectation = f"an integer >= {minimum}"

    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError(f"{where}: '{name}' must be {expectation}")
    if minimum is not None and raw < minimum:
        raise ValueError(f"{where}: '{name}' must be {expectation}")
    return raw
