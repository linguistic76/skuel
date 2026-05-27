# mypy: disable-error-code="call-arg,misc"
# Strawberry decorators generate __init__ dynamically; mypy can't see the
# inferred constructor args. Mirrors the routes.graphql.* override.
"""
Unit tests for GraphQL guardrail extensions (routes/graphql/guardrails.py).

Covers the two custom extensions with no native Strawberry equivalent:
- QueryComplexityLimiter — additive, type-weighted field-cost budget
- ResolverTimeoutExtension — per-resolver execution ceiling

Plus a regression test that the real schema wires its extensions as factory
callables (no instance-deprecation warning).

No Neo4j required — minimal Strawberry schemas are built inline.
"""

from __future__ import annotations

import asyncio
import functools
import warnings

import pytest
import strawberry

from routes.graphql.guardrails import QueryComplexityLimiter, ResolverTimeoutExtension


@strawberry.type
class _Inner:
    a: str
    b: str


@strawberry.type
class _ComplexityQuery:
    @strawberry.field
    def scalar(self) -> str:
        return "x"

    @strawberry.field
    def obj(self) -> _Inner:
        return _Inner(a="1", b="2")

    @strawberry.field
    def items(self) -> list[_Inner]:
        return [_Inner(a="1", b="2")]


def _complexity_schema(max_complexity: int) -> strawberry.Schema:
    """Schema with costs basic=1, nested=5, list=10, multiplier=1."""
    return strawberry.Schema(
        query=_ComplexityQuery,
        extensions=[
            functools.partial(
                QueryComplexityLimiter,
                max_complexity=max_complexity,
                basic_field_cost=1,
                list_field_cost=10,
                nested_object_cost=5,
                multiplier=1.0,
            )
        ],
    )


class TestQueryComplexityLimiter:
    def test_scalar_under_budget_passes(self) -> None:
        # { scalar } -> basic(1) = 1
        result = _complexity_schema(max_complexity=10).execute_sync("{ scalar }")
        assert result.errors is None
        assert result.data == {"scalar": "x"}

    def test_nested_object_under_budget_passes(self) -> None:
        # { obj { a b } } -> nested(5) + 2*basic(1) = 7
        result = _complexity_schema(max_complexity=10).execute_sync("{ obj { a b } }")
        assert result.errors is None

    def test_list_field_over_budget_rejected(self) -> None:
        # { items { a b } } -> list(10) + 2*basic(1) = 12 > 10
        result = _complexity_schema(max_complexity=10).execute_sync("{ items { a b } }")
        assert result.errors is not None
        assert "complexity" in result.errors[0].message.lower()

    def test_fragment_spread_is_counted(self) -> None:
        # Fragment spread must be expanded, not free: list(10) + 2*basic = 12 > 10
        query = "query { items { ...f } } fragment f on _Inner { a b }"
        result = _complexity_schema(max_complexity=10).execute_sync(query)
        assert result.errors is not None
        assert "complexity" in result.errors[0].message.lower()

    def test_generous_budget_allows_everything(self) -> None:
        result = _complexity_schema(max_complexity=1000).execute_sync("{ items { a b } obj { a } }")
        assert result.errors is None


@strawberry.type
class _TimeoutQuery:
    @strawberry.field
    async def slow(self) -> str:
        await asyncio.sleep(1.0)
        return "done"

    @strawberry.field
    async def fast(self) -> str:
        return "quick"


def _timeout_schema(seconds: float) -> strawberry.Schema:
    return strawberry.Schema(
        query=_TimeoutQuery,
        extensions=[functools.partial(ResolverTimeoutExtension, seconds=seconds)],
    )


class TestResolverTimeoutExtension:
    @pytest.mark.asyncio
    async def test_slow_resolver_times_out(self) -> None:
        result = await _timeout_schema(seconds=0.05).execute("{ slow }")
        assert result.errors is not None  # wait_for raised TimeoutError -> field error

    @pytest.mark.asyncio
    async def test_fast_resolver_passes(self) -> None:
        result = await _timeout_schema(seconds=5.0).execute("{ fast }")
        assert result.errors is None
        assert result.data == {"fast": "quick"}


class TestSchemaExtensionWiring:
    def test_create_graphql_schema_has_no_instance_deprecation(self) -> None:
        """Extensions must be factory callables, not instances (Strawberry deprecation)."""
        from routes.graphql.schema import create_graphql_schema

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            create_graphql_schema()

        offending = [str(w.message) for w in caught if "extension instance" in str(w.message)]
        assert not offending, offending
