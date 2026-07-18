"""
Unit tests for QueryTemplateRegistry template rendering.

Covers the structural-parameter design: ``{name}`` slots (labels, relationship
types) are validated and spliced into the query text, while ``$name`` slots
stay driver parameters. Guards the regression where structural placeholders
were left in the query as un-parameterizable ``$label`` / ``$property`` tokens.
"""

from datetime import datetime

import pytest

from adapters.persistence.neo4j.query_builders.query_template_registry import (
    QueryTemplateRegistry,
)
from core.infrastructure.database.schema import Neo4jIndex, SchemaContext
from core.models.query_types import IndexStrategy
from core.utils.result_simplified import Result


def _make_schema(indexes: list[Neo4jIndex]) -> SchemaContext:
    """Build a minimal but valid SchemaContext for template optimization."""
    return SchemaContext(
        node_labels=["Entity", "Task", "Goal"],
        relationship_types=["RELATED_TO"],
        indexes=indexes,
        constraints=[],
        node_label_info={},
        relationship_type_info={},
        property_names={"uid", "title"},
        indexed_properties={},
        unique_properties={},
        introspection_timestamp=datetime(2026, 1, 1),
        schema_hash="hash",
    )


class _FakeSchemaService:
    """Stand-in for Neo4jSchemaService — returns a fixed SchemaContext."""

    def __init__(self, schema: SchemaContext) -> None:
        self.schema = schema

    async def get_schema_context(self) -> Result[SchemaContext]:
        return Result.ok(self.schema)


def _registry(indexes: list[Neo4jIndex] | None = None) -> QueryTemplateRegistry:
    return QueryTemplateRegistry(_FakeSchemaService(_make_schema(indexes or [])))


def _fulltext_index(name: str = "entity_fulltext") -> Neo4jIndex:
    return Neo4jIndex(
        name=name,
        type="FULLTEXT",
        entity_type="NODE",
        labels=["Entity"],
        properties=["title", "content"],
        state="ONLINE",
    )


# ============================================================================
# Structural substitution — base templates
# ============================================================================


@pytest.mark.asyncio
async def test_text_search_base_path_substitutes_label():
    """Without a fulltext index, the base template must splice the label into
    the query text and keep property lookup + search term as driver params."""
    result = await _registry().from_template(
        "text_search",
        {"label": "Task", "property": "title", "search_term": "hello", "limit": 10},
    )

    assert not result.is_error
    plan = result.value.primary_plan
    assert "MATCH (n:Task)" in plan.cypher
    assert "n[$property] CONTAINS $search_term" in plan.cypher
    # No structural placeholder may survive rendering
    assert "$label" not in plan.cypher
    assert "{label}" not in plan.cypher
    assert plan.parameters == {"property": "title", "search_term": "hello", "limit": 10}
    assert plan.strategy == IndexStrategy.NO_INDEX


@pytest.mark.asyncio
async def test_count_by_label_substitutes_label_and_binds_nothing():
    result = await _registry().from_template("count_by_label", {"label": "Goal"})

    assert not result.is_error
    plan = result.value.primary_plan
    assert "MATCH (n:Goal)" in plan.cypher
    assert plan.parameters == {}


@pytest.mark.asyncio
async def test_group_by_property_uses_dynamic_property_access():
    result = await _registry().from_template(
        "group_by_property", {"label": "Task", "property": "status"}
    )

    assert not result.is_error
    plan = result.value.primary_plan
    assert "MATCH (n:Task)" in plan.cypher
    assert "n[$property] as value" in plan.cypher
    assert plan.parameters == {"property": "status"}


@pytest.mark.asyncio
async def test_find_related_substitutes_relationship_type():
    result = await _registry().from_template(
        "find_related", {"uid": "task_123", "rel_type": "RELATED_TO"}
    )

    assert not result.is_error
    plan = result.value.primary_plan
    assert "-[r:RELATED_TO]-" in plan.cypher
    assert plan.parameters == {"uid": "task_123"}


@pytest.mark.asyncio
async def test_create_entity_substitutes_label_keeps_properties_param():
    result = await _registry().from_template(
        "create_entity", {"label": "Task", "properties": {"uid": "task_123"}}
    )

    assert not result.is_error
    plan = result.value.primary_plan
    assert "CREATE (n:Task $properties)" in plan.cypher
    assert plan.parameters == {"properties": {"uid": "task_123"}}


# ============================================================================
# Injection guards
# ============================================================================


@pytest.mark.asyncio
async def test_unknown_label_is_rejected():
    result = await _registry().from_template("count_by_label", {"label": "Task) DETACH DELETE (m"})

    assert result.is_error
    assert "not a valid NeoLabel" in result.expect_error().message


@pytest.mark.asyncio
async def test_unsafe_relationship_type_is_rejected():
    result = await _registry().from_template(
        "find_related", {"uid": "task_123", "rel_type": "X]->() DETACH DELETE n //"}
    )

    assert result.is_error
    assert "not a valid RelationshipName" in result.expect_error().message


@pytest.mark.asyncio
async def test_unregistered_relationship_type_is_rejected():
    """A syntactically safe but unknown edge type must not render into
    executable Cypher — rel_type slots validate against RelationshipName."""
    result = await _registry().from_template(
        "find_related", {"uid": "task_123", "rel_type": "MADE_UP_EDGE"}
    )

    assert result.is_error
    assert "not a valid RelationshipName" in result.expect_error().message


# ============================================================================
# Fulltext optimization variant
# ============================================================================


@pytest.mark.asyncio
async def test_text_search_fulltext_variant_uses_driver_parameters():
    """With a fulltext index, the label is compared as a value — it must stay
    a driver parameter, and the index name is spliced from trusted schema."""
    result = await _registry([_fulltext_index()]).from_template(
        "text_search",
        {"label": "Task", "property": "title", "search_term": "hello", "limit": 5},
    )

    assert not result.is_error
    plan = result.value.primary_plan
    assert "db.index.fulltext.queryNodes('entity_fulltext', $search_term)" in plan.cypher
    assert "$label IN labels(node)" in plan.cypher
    assert "{label}" not in plan.cypher
    # property is unused by the fulltext variant and must not be bound
    assert plan.parameters == {"label": "Task", "search_term": "hello", "limit": 5}
    assert plan.strategy == IndexStrategy.FULLTEXT_SEARCH
    assert plan.used_indexes == ["entity_fulltext"]


# ============================================================================
# Parameter validation
# ============================================================================


@pytest.mark.asyncio
async def test_missing_required_parameter_fails():
    result = await _registry().from_template("text_search", {"label": "Task"})

    assert result.is_error
    assert "Missing required parameters" in result.expect_error().message


@pytest.mark.asyncio
async def test_unbound_driver_parameter_fails_fast():
    """Optional $properties left unbound must fail at build time, not at the
    driver."""
    result = await _registry().from_template(
        "create_relationship",
        {"from_uid": "task_1", "to_uid": "task_2", "rel_type": "RELATED_TO"},
    )

    assert result.is_error
    assert "unbound" in result.expect_error().message
    assert "properties" in result.expect_error().message


@pytest.mark.asyncio
async def test_create_relationship_with_all_parameters_succeeds():
    result = await _registry().from_template(
        "create_relationship",
        {
            "from_uid": "task_1",
            "to_uid": "task_2",
            "rel_type": "RELATED_TO",
            "properties": {"weight": 1},
        },
    )

    assert not result.is_error
    plan = result.value.primary_plan
    assert "CREATE (a)-[r:RELATED_TO $properties]->(b)" in plan.cypher
    assert plan.parameters == {
        "from_uid": "task_1",
        "to_uid": "task_2",
        "properties": {"weight": 1},
    }


@pytest.mark.asyncio
async def test_unknown_template_fails():
    result = await _registry().from_template("does_not_exist", {})

    assert result.is_error
    assert "not found" in result.expect_error().message


# ============================================================================
# Library composition
# ============================================================================


def test_no_registered_template_contains_dollar_structural_placeholders():
    """Every structural slot must use {name} syntax; $name in a template must
    be a real driver parameter (guards against re-introducing the conflation)."""
    registry = _registry()
    for name, registration in registry._template_library.items():
        spec = registration.spec
        for key in spec.structural_parameters:
            assert f"${key}" not in spec.base_template, (
                f"Template '{name}' uses ${key} for structural slot '{key}'"
            )
            assert key in spec.required_parameters, (
                f"Template '{name}' structural slot '{key}' must be required"
            )


def test_facet_aggregation_template_removed():
    """facet_aggregation carried a raw-Cypher $base_conditions injection slot
    and had no consumers — deleted per One Path Forward."""
    from adapters.persistence.neo4j.query_builders import QueryBuilder

    qb = QueryBuilder(schema_service=None)
    library = qb.get_template_library()
    all_templates = [name for names in library.values() for name in names]
    assert "facet_aggregation" not in all_templates
    assert "faceted_knowledge_search" in all_templates
