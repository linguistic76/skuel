"""
Regression: `build_weighted_path_query` ORDER BY honours `weight_mode`
======================================================================

The ORDER BY operand was the quoted Cypher string literal ``'$weight_mode'``
instead of the f-string interpolation ``'{weight_mode}'``. `weight_mode` is
never bound as a parameter (the builder binds only `start_uid`/`end_uid`), so
the CASE operand was the constant text ``$weight_mode``, which matches neither
WHEN arm — the ELSE arm always won and every mode ordered by ``-path_weight``.

For ``weight_mode="sum"`` the intended ordering is ``path_weight`` (lower
aggregate cost is better), so sum-mode results came back reversed. The other
three modes coincide with the ELSE arm, which is why it went unnoticed.

Two independent guards below, either of which catches the original defect:

1. `TestOrderByResolvesPerMode` — resolves the ORDER BY CASE the way Neo4j
   would and asserts the per-mode expression. Its resolver is pinned against
   the pre-fix text (`test_resolver_reports_the_original_defect`) so the guard
   cannot pass by being blind.
2. `TestEveryParameterReferenceIsBound` — the general form of the defect: a
   ``$name`` in the generated Cypher that the params dict does not bind.
"""

from __future__ import annotations

import re

import pytest

from adapters.persistence.neo4j.query import build_weighted_path_query

# The four modes the builder accepts, paired with the ORDER BY expression each
# is meant to sort by. Only "sum" is a cost (lower is better); the rest are
# quality scores where higher is better, hence the descending negation.
MODE_TO_ORDER_EXPR = {
    "multiply": "-path_weight",
    "sum": "path_weight",
    "min": "-path_weight",
    "avg": "-path_weight",
}

# The exact ORDER BY block as it read before the fix, kept verbatim as a
# positive control for the resolver below.
PRE_FIX_ORDER_BY = """
    ORDER BY
        CASE '$weight_mode'
            WHEN 'min' THEN -path_weight
            WHEN 'sum' THEN path_weight
            ELSE -path_weight
        END
    LIMIT 10
"""


def _order_by_block(cypher: str) -> str:
    """Slice out ORDER BY..LIMIT.

    Scoped deliberately: the `min` and `avg` weight expressions each contain
    their own searched CASE earlier in the query, which a whole-query scan
    would collide with.
    """
    match = re.search(r"\bORDER BY\b(?P<block>.*?)\bLIMIT\b", cypher, re.DOTALL)
    assert match is not None, "generated Cypher has no ORDER BY ... LIMIT block"
    return match.group("block")


def resolve_order_by_expression(cypher: str) -> str:
    """Evaluate the ORDER BY simple-CASE the way Neo4j would.

    Simple-CASE semantics: compare the operand against each WHEN value in
    order, first match wins, otherwise ELSE. Exact for this shape (a quoted
    literal operand and single-token arms) and asserts every part it depends
    on, so a change to the CASE shape fails loudly rather than silently
    resolving to the wrong arm.
    """
    block = _order_by_block(cypher)

    operand_match = re.search(r"\bCASE\s+'(?P<operand>[^']*)'", block)
    assert operand_match is not None, f"no quoted CASE operand in ORDER BY block: {block!r}"
    operand = operand_match.group("operand")

    arms = re.findall(r"\bWHEN\s+'(?P<value>[^']*)'\s+THEN\s+(?P<expr>-?\w+)", block)
    assert arms, f"no WHEN arms in ORDER BY block: {block!r}"

    for value, expr in arms:
        if value == operand:
            return expr

    else_match = re.search(r"\bELSE\s+(?P<expr>-?\w+)", block)
    assert else_match is not None, f"operand {operand!r} matched no arm and there is no ELSE"
    return else_match.group("expr")


def _build(weight_mode: str) -> tuple[str, dict[str, object]]:
    cypher, params = build_weighted_path_query(
        start_uid="task_start",
        end_uid="task_end",
        relationship_types=["BLOCKS", "DEPENDS_ON"],
        weight_mode=weight_mode,
    )
    return cypher, dict(params)


class TestOrderByResolvesPerMode:
    def test_resolver_reports_the_original_defect(self):
        """Positive control: the resolver must see the pre-fix text as broken.

        Without this, a resolver that always returned the expected expression
        would make every assertion below vacuous.
        """
        assert resolve_order_by_expression(PRE_FIX_ORDER_BY) == "-path_weight"

    @pytest.mark.parametrize(("weight_mode", "expected"), sorted(MODE_TO_ORDER_EXPR.items()))
    def test_orders_by_expected_expression(self, weight_mode: str, expected: str):
        cypher, _ = _build(weight_mode)
        assert resolve_order_by_expression(cypher) == expected

    def test_sum_is_the_only_mode_that_sorts_ascending(self):
        """The whole point of the CASE: sum must differ from the other three."""
        resolved = {
            mode: resolve_order_by_expression(_build(mode)[0]) for mode in MODE_TO_ORDER_EXPR
        }
        assert resolved["sum"] == "path_weight"
        assert {mode for mode, expr in resolved.items() if expr == "path_weight"} == {"sum"}

    @pytest.mark.parametrize("weight_mode", sorted(MODE_TO_ORDER_EXPR))
    def test_case_operand_is_the_mode_not_a_parameter_reference(self, weight_mode: str):
        cypher, _ = _build(weight_mode)
        block = _order_by_block(cypher)
        assert f"CASE '{weight_mode}'" in block
        assert "$weight_mode" not in block


class TestEveryParameterReferenceIsBound:
    """A `$name` the builder never binds is the general form of this defect."""

    @pytest.mark.parametrize("weight_mode", sorted(MODE_TO_ORDER_EXPR))
    def test_no_unbound_parameter_references(self, weight_mode: str):
        cypher, params = _build(weight_mode)
        referenced = set(re.findall(r"\$([A-Za-z_][A-Za-z0-9_]*)", cypher))
        assert referenced <= set(params), (
            f"unbound parameter reference(s) {sorted(referenced - set(params))} "
            f"for weight_mode={weight_mode!r}"
        )

    def test_the_builder_binds_only_the_two_uids(self):
        """Pins the premise the assertion above rests on."""
        _, params = _build("sum")
        assert set(params) == {"start_uid", "end_uid"}


class TestInvalidModeIsRejected:
    """`weight_mode` is interpolated into Cypher, so the allowlist is the guard.

    This is the premise the two `// noqa: CYP003` suppressions in the builder
    cite ("a weight_expr_map key; any other value raised ValueError above").
    """

    @pytest.mark.parametrize("weight_mode", ["", "SUM", "sum'--", "median"])
    def test_unknown_mode_raises_before_any_cypher_is_built(self, weight_mode: str):
        with pytest.raises(ValueError, match="Invalid weight_mode"):
            _build(weight_mode)
