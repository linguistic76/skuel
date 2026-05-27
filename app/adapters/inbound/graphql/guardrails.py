"""
GraphQL Guardrail Extensions
============================

Custom Strawberry extensions that enforce two ``GraphQLConfig`` limits with no
native Strawberry equivalent (depth / token / alias limits use the built-ins):

- :class:`QueryComplexityLimiter` — an ``AddValidationRules`` extension that
  walks each operation's selection set (resolving fragment spreads, like
  Strawberry's own ``QueryDepthLimiter``) and rejects operations whose summed
  field cost exceeds ``max_query_complexity``. Cost is **additive and
  type-weighted**: a leaf field costs ``basic_field_cost``, a list field
  ``list_field_cost``, a nested object field ``nested_object_cost``, scaled by
  ``field_complexity_multiplier``. Multiplicative list-size blow-up is bounded
  separately by the depth and list-size limits — this rule caps query *breadth*.

- :class:`ResolverTimeoutExtension` — a ``SchemaExtension`` whose global
  ``resolve`` hook wraps every async resolver in ``asyncio.wait_for`` so a
  single runaway field is bounded (the whole-operation ceiling is enforced
  separately at the adapter boundary, see ``graphql_routes.py``).

See: adapters/inbound/graphql/config.py (the limits), adapters/inbound/graphql/schema.py (wiring).
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from graphql import (
    GraphQLError,
    GraphQLList,
    GraphQLNonNull,
    OperationType,
    get_named_type,
    is_interface_type,
    is_object_type,
    is_union_type,
)
from graphql.language import (
    FieldNode,
    FragmentDefinitionNode,
    FragmentSpreadNode,
    InlineFragmentNode,
    OperationDefinitionNode,
)
from graphql.validation import ValidationRule
from strawberry.extensions import AddValidationRules, SchemaExtension

if TYPE_CHECKING:
    from collections.abc import Callable

    from graphql import GraphQLNamedType, GraphQLOutputType, GraphQLSchema
    from graphql.language import SelectionSetNode
    from graphql.validation import ValidationContext


@dataclass(frozen=True)
class _FieldCosts:
    """Per-field-shape cost weights (from GraphQLConfig)."""

    basic: int
    list: int
    nested: int
    multiplier: float


def _is_composite(type_: GraphQLNamedType | None) -> bool:
    """True if the named type can carry a sub-selection (object/interface/union)."""
    return is_object_type(type_) or is_interface_type(type_) or is_union_type(type_)


def _wraps_list(type_: GraphQLOutputType) -> bool:
    """True if the (possibly non-null-wrapped) output type is a list.

    Uses isinstance (not graphql's is_*_type guards) so the type checker can
    narrow before reading ``.of_type`` — only GraphQLNonNull/GraphQLList carry it.
    """
    inner = type_.of_type if isinstance(type_, GraphQLNonNull) else type_
    return isinstance(inner, GraphQLList)


def _field_def(parent_type: GraphQLNamedType | None, name: str) -> Any:
    """Look up a field definition on an object/interface parent (None otherwise)."""
    if is_object_type(parent_type) or is_interface_type(parent_type):
        return parent_type.fields.get(name)  # type: ignore[union-attr]
    return None


def _selection_set_cost(
    selection_set: SelectionSetNode,
    parent_type: GraphQLNamedType | None,
    schema: GraphQLSchema,
    fragments: dict[str, FragmentDefinitionNode],
    costs: _FieldCosts,
    visited_fragments: frozenset[str],
) -> float:
    """Sum the additive cost of every field reachable from a selection set."""
    total = 0.0
    for selection in selection_set.selections:
        if isinstance(selection, FieldNode):
            total += _field_cost(
                selection, parent_type, schema, fragments, costs, visited_fragments
            )
        elif isinstance(selection, InlineFragmentNode):
            frag_type = parent_type
            if selection.type_condition is not None:
                frag_type = schema.get_type(selection.type_condition.name.value) or parent_type
            total += _selection_set_cost(
                selection.selection_set, frag_type, schema, fragments, costs, visited_fragments
            )
        elif isinstance(selection, FragmentSpreadNode):
            name = selection.name.value
            if name in visited_fragments:
                continue  # cycle guard (matches Strawberry's depth limiter)
            fragment = fragments.get(name)
            if fragment is None:
                continue
            frag_type = schema.get_type(fragment.type_condition.name.value)
            total += _selection_set_cost(
                fragment.selection_set,
                frag_type,
                schema,
                fragments,
                costs,
                visited_fragments | {name},
            )
    return total


def _field_cost(
    node: FieldNode,
    parent_type: GraphQLNamedType | None,
    schema: GraphQLSchema,
    fragments: dict[str, FragmentDefinitionNode],
    costs: _FieldCosts,
    visited_fragments: frozenset[str],
) -> float:
    """Cost of one field: its own weight plus the cost of its sub-selection."""
    if node.name.value.startswith("__"):
        return 0.0  # introspection fields are free (mirrors depth limiter)

    field_definition = _field_def(parent_type, node.name.value)
    if node.selection_set is None or field_definition is None:
        return float(costs.basic)  # leaf field (or unresolvable — charge minimal)

    own_cost = costs.list if _wraps_list(field_definition.type) else costs.nested
    named_type = get_named_type(field_definition.type)
    child_cost = (
        _selection_set_cost(
            node.selection_set, named_type, schema, fragments, costs, visited_fragments
        )
        if _is_composite(named_type)
        else 0.0
    )
    return float(own_cost) + child_cost


def _create_complexity_validator(max_complexity: int, costs: _FieldCosts) -> type[ValidationRule]:
    """Build a ValidationRule that rejects over-budget operations.

    Mirrors the structure of Strawberry's ``QueryDepthLimiter`` — the whole
    computation runs in ``__init__`` (fragments resolved up front) and reports a
    ``GraphQLError`` via the validation context when the budget is exceeded.
    """

    class ComplexityValidator(ValidationRule):
        def __init__(self, validation_context: ValidationContext) -> None:
            document = validation_context.document
            schema = validation_context.schema
            fragments = {
                d.name.value: d
                for d in document.definitions
                if isinstance(d, FragmentDefinitionNode)
            }
            root_types = {
                OperationType.QUERY: schema.query_type,
                OperationType.MUTATION: schema.mutation_type,
                OperationType.SUBSCRIPTION: schema.subscription_type,
            }
            for definition in document.definitions:
                if not isinstance(definition, OperationDefinitionNode):
                    continue
                root_type = root_types.get(definition.operation)
                if root_type is None:
                    continue
                raw_cost = _selection_set_cost(
                    definition.selection_set, root_type, schema, fragments, costs, frozenset()
                )
                total = raw_cost * costs.multiplier
                if total > max_complexity:
                    op_name = definition.name.value if definition.name else "anonymous"
                    validation_context.report_error(
                        GraphQLError(
                            f"'{op_name}' exceeds maximum query complexity of "
                            f"{max_complexity} (got {total:.0f})",
                            [definition],
                        )
                    )
            super().__init__(validation_context)

    return ComplexityValidator


class QueryComplexityLimiter(AddValidationRules):
    """Reject GraphQL operations whose summed field cost exceeds a budget.

    Example::

        schema = strawberry.Schema(
            query=Query,
            extensions=[functools.partial(QueryComplexityLimiter, max_complexity=1000, ...)],
        )
    """

    def __init__(
        self,
        *,
        max_complexity: int,
        basic_field_cost: int,
        list_field_cost: int,
        nested_object_cost: int,
        multiplier: float,
    ) -> None:
        costs = _FieldCosts(
            basic=basic_field_cost,
            list=list_field_cost,
            nested=nested_object_cost,
            multiplier=multiplier,
        )
        super().__init__([_create_complexity_validator(max_complexity, costs)])


class ResolverTimeoutExtension(SchemaExtension):
    """Bound every async resolver with a per-field timeout.

    Strawberry invokes ``resolve`` for each field; we wrap awaitable resolver
    results in ``asyncio.wait_for`` so one slow field cannot hang the request.
    Synchronous (already-resolved) values pass straight through. The
    whole-operation ceiling is enforced separately at the adapter boundary.
    """

    def __init__(self, *, seconds: float) -> None:
        self._seconds = seconds

    async def resolve(
        self,
        _next: Callable[..., Any],
        root: Any,  # boundary: GraphQL resolver root is structurally heterogeneous
        info: Any,  # boundary: GraphQLResolveInfo
        *args: str,
        **kwargs: Any,  # boundary: arbitrary GraphQL field arguments
    ) -> Any:
        result = _next(root, info, *args, **kwargs)
        if inspect.isawaitable(result):
            return await asyncio.wait_for(result, timeout=self._seconds)
        return result


__all__ = ["QueryComplexityLimiter", "ResolverTimeoutExtension"]
