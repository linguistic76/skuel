"""
Hardening: field-key validation in query optimizer + unified query builder
==========================================================================

Closes 2026-05-26 security audit item #3 ("field-key validation gaps in
optimization/builder layers — not exploitable today"). Every value
interpolated into a Cypher fragment (property name, comparison operator,
sort direction) now passes through an allowlist before it can reach the
plan-builders.

Today's callers are all internal and pass trusted values. The audit's
"not exploitable today" classification holds. These tests guard the latent
seam — any future caller that hands user input straight to QueryConstraint
or QuerySort is rejected at `_validate_request`, not interpolated.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from adapters.persistence.neo4j.query import (
    QueryBuildRequest,
    QueryConstraint,
    QuerySort,
)
from adapters.persistence.neo4j.query_builders.query_optimizer import QueryOptimizer
from core.utils.result_simplified import Result
from core.utils.validation_helpers import (
    validate_cypher_operator,
    validate_field_name,
    validate_sort_direction,
)

# ----------------------------------------------------------------------------
# Validator allowlist coverage
# ----------------------------------------------------------------------------


class TestValidateFieldName:
    def test_accepts_simple_identifier(self):
        assert validate_field_name("priority") is True

    def test_accepts_double_underscore_operator_suffix(self):
        # ModelQueryBuilder supports `due_date__gte` etc.; the full key must validate.
        assert validate_field_name("due_date__gte") is True
        assert validate_field_name("title__contains") is True

    def test_rejects_cypher_injection_attempt(self):
        assert validate_field_name("title; DROP CONSTRAINT") is False
        assert validate_field_name("title} WITH") is False
        assert validate_field_name("title.password") is False
        assert validate_field_name("") is False

    def test_rejects_overlong(self):
        assert validate_field_name("a" * 65) is False
        assert validate_field_name("a" * 64) is True


class TestValidateCypherOperator:
    def test_accepts_known_operators(self):
        for op in (
            "=",
            "<>",
            "!=",
            "<",
            ">",
            "<=",
            ">=",
            "CONTAINS",
            "STARTS WITH",
            "ENDS WITH",
            "IN",
        ):
            assert validate_cypher_operator(op) is True, op

    def test_rejects_lowercase_variants(self):
        # Allowlist is case-sensitive — QueryConstraint values always upper-case.
        assert validate_cypher_operator("contains") is False
        assert validate_cypher_operator("in") is False

    def test_rejects_injection_attempts(self):
        assert validate_cypher_operator("= 1 OR 1") is False
        assert validate_cypher_operator("UNION") is False
        assert validate_cypher_operator("") is False


class TestValidateSortDirection:
    def test_accepts_asc_desc_any_case(self):
        for direction in ("ASC", "DESC", "asc", "desc", "Asc"):
            assert validate_sort_direction(direction) is True, direction

    def test_rejects_injection(self):
        assert validate_sort_direction("ASC; DROP TABLE") is False
        assert validate_sort_direction("--") is False
        assert validate_sort_direction("") is False


# ----------------------------------------------------------------------------
# QueryOptimizer._validate_request gate
# ----------------------------------------------------------------------------


def _make_optimizer(node_labels: set[str] | None = None) -> QueryOptimizer:
    """Build a QueryOptimizer whose schema service returns a schema with the given labels."""
    schema = MagicMock()
    schema.node_labels = node_labels or {"Task", "Goal"}
    schema.constraints = []
    schema.indexes = []

    schema_service = MagicMock()
    schema_service.get_schema_context = AsyncMock(return_value=Result.ok(schema))
    return QueryOptimizer(schema_service)


@pytest.mark.asyncio
async def test_well_formed_request_passes():
    opt = _make_optimizer()
    req = QueryBuildRequest(
        labels={"Task"},
        constraints=[QueryConstraint(property_name="priority", operator="=", value="high")],
        sort_by=[QuerySort(property_name="due_date", direction="DESC")],
    )

    result = await opt.build_optimized_query(req)

    assert not result.is_error, result.expect_error() if result.is_error else ""


@pytest.mark.asyncio
async def test_rejects_unsafe_constraint_property():
    opt = _make_optimizer()
    req = QueryBuildRequest(
        labels={"Task"},
        constraints=[
            QueryConstraint(property_name="priority; DROP CONSTRAINT", operator="=", value="x")
        ],
    )

    result = await opt.build_optimized_query(req)

    assert result.is_error
    err = result.expect_error()
    assert err.details["field"] == "constraint_property"


@pytest.mark.asyncio
async def test_rejects_unknown_constraint_operator():
    opt = _make_optimizer()
    req = QueryBuildRequest(
        labels={"Task"},
        constraints=[QueryConstraint(property_name="priority", operator="INJECT", value="x")],
    )

    result = await opt.build_optimized_query(req)

    assert result.is_error
    assert result.expect_error().details["field"] == "constraint_operator"


@pytest.mark.asyncio
async def test_rejects_unsafe_sort_property():
    opt = _make_optimizer()
    req = QueryBuildRequest(
        labels={"Task"},
        sort_by=[QuerySort(property_name="due_date; --", direction="ASC")],
    )

    result = await opt.build_optimized_query(req)

    assert result.is_error
    assert result.expect_error().details["field"] == "sort_property"


@pytest.mark.asyncio
async def test_rejects_unsafe_sort_direction():
    opt = _make_optimizer()
    req = QueryBuildRequest(
        labels={"Task"},
        sort_by=[QuerySort(property_name="due_date", direction="ASC; DROP CONSTRAINT")],
    )

    result = await opt.build_optimized_query(req)

    assert result.is_error
    assert result.expect_error().details["field"] == "sort_direction"


# ----------------------------------------------------------------------------
# ModelQueryBuilder.filter silent-drop policy
# ----------------------------------------------------------------------------


class TestUnifiedQueryBuilderFilter:
    """ModelQueryBuilder.filter mirrors order_by's silent-drop-with-warning policy."""

    def _builder(self):
        from adapters.persistence.neo4j.query.unified_query_builder import ModelQueryBuilder

        model = MagicMock()
        model.__name__ = "Task"
        return ModelQueryBuilder(model=model, label="Task", executor=None)

    def test_accepts_safe_keys(self):
        b = self._builder()
        b.filter(priority="high", due_date__gte="2026-01-01")
        assert b._filters == {"priority": "high", "due_date__gte": "2026-01-01"}

    def test_drops_injection_key(self):
        b = self._builder()
        b.filter(priority="high", **{"title; DROP CONSTRAINT": "x"})
        assert "priority" in b._filters
        assert "title; DROP CONSTRAINT" not in b._filters

    def test_drops_dotted_key(self):
        b = self._builder()
        b.filter(**{"user.password": "leaked"})
        assert b._filters == {}
