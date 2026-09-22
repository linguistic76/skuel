"""
Hardening: field-name guarding in the persistence layer
=======================================================

Closes 2026-05-26 security audit item #3 ("field-key validation gaps in
optimization/builder layers — not exploitable today") and the ruling that
followed it (docs/roadmap/field-name-guarding-in-cypher.md).

Neo4j cannot parameterize a property name, so every sort key and every property
name in a pattern is interpolated. Three guarantees are in use, and they are not
interchangeable:

- **Syntactic** — ``validate_field_name`` (``core/utils``, returns bool, ≤64
  chars) and ``validate_identifier`` (``query/cypher/_helpers``, raises). One
  regex, two contracts: callers that should drop a bad name use the first,
  callers for which a bad name is a programming error use the second. The
  schema manager's DDL and all five query-builder modules share the second.
- **Model-derived** — the name must be a field on the entity class. Every
  builder in ``crud_queries`` uses this for a sort key (warn and drop) and for
  an interpolated property name in a pattern (raise, because dropping it would
  change which rows match rather than only their order).
- **Named allowlist** — ``_ALLOWED_ORDER_BY`` in ``_backend_helpers.py``, an
  explicit frozenset, at two sites.

Syntactic is the weakest of the three, and measurably so: ``ORDER BY n.secret``
where ``secret`` is never projected is permitted by Neo4j, returns rows in that
hidden property's order, and survives ``SKIP``/``LIMIT`` as a paginated oracle
(``DISTINCT`` and aggregation refuse it). It cannot cross a ``WHERE`` clause, so
it discloses un-rendered properties of already-authorized rows, not other users'
rows. That is why no HTTP route publishes a sort key: the list route takes
pagination only.

Some backends still interpolate a property name their caller hands them without
any of the three — ``_relationship_ordered_mixin``'s ``order_by_property``,
``sequence_property`` and ``get_hierarchical_children_deep``'s whole
``match_pattern``; ``PsBackend.list_steps_raw``'s ``order_field``. Every one of
those callers passes a literal, a registry constant, or sits behind a PLANNED
surface, and the ruling above records why they stay that way and what would
change it. Those sites are deliberately not covered here.

Comparison operators and sort directions are guarded a stronger way and so have
no validator: no builder interpolates a caller's operator or direction at all.
Operators are chosen by structural dispatch (``build_search_query``'s if/elif
chain, ``intelligence_queries``' guarded ``op_map``, ``batch_cypher_builder``'s
``_FILTER_OP_MAP``), which emits a literal and cannot emit an unknown one.
Directions resolve to ``"ASC"``/``"DESC"`` from a bool, from the
developer-authored ``RelationshipSpec.order_direction``, or from a literal at
the call site. A validator for either would check a value that never varies.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from core.utils.validation_helpers import validate_field_name

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


# ----------------------------------------------------------------------------
# Array builders: model-derived, like the sort builders beside them
# ----------------------------------------------------------------------------


class TestArrayBuilderFieldGuards:
    """The two array builders check what they interpolate against the model.

    They are the pair that used to interpolate both ``field`` and ``order_by``
    unchecked while three sort builders in the same module checked ``order_by``
    against the model and warned-and-dropped a miss. One module, one policy.

    The two names are guarded differently on purpose: ``field`` lands in the
    WHERE-clause pattern, so dropping it silently would change which rows match;
    ``order_by`` only changes their order.
    """

    def test_array_contains_rejects_field_the_model_does_not_declare(self):
        import pytest

        from adapters.persistence.neo4j.query.cypher import build_array_contains_query
        from core.models.enums.neo_labels import NeoLabel
        from core.models.task.task import Task

        with pytest.raises(ValueError, match="array field"):
            build_array_contains_query(Task, label=NeoLabel.TASK, field="password", value="x")

    def test_array_contains_rejects_injection_in_field(self):
        import pytest

        from adapters.persistence.neo4j.query.cypher import build_array_contains_query
        from core.models.enums.neo_labels import NeoLabel
        from core.models.task.task import Task

        with pytest.raises(ValueError):
            build_array_contains_query(Task, label=NeoLabel.TASK, field="tags) OR (1=1", value="x")

    def test_array_any_match_rejects_field_the_model_does_not_declare(self):
        import pytest

        from adapters.persistence.neo4j.query.cypher import build_array_any_match_query
        from core.models.enums.neo_labels import NeoLabel
        from core.models.task.task import Task

        with pytest.raises(ValueError, match="array field"):
            build_array_any_match_query(Task, label=NeoLabel.TASK, field="password", values=["x"])

    def test_order_by_off_the_model_is_dropped_not_interpolated(self):
        from adapters.persistence.neo4j.query.cypher import (
            build_array_any_match_query,
            build_array_contains_query,
        )
        from core.models.enums.neo_labels import NeoLabel
        from core.models.task.task import Task

        cypher, _ = build_array_contains_query(
            Task, label=NeoLabel.TASK, field="tags", value="x", order_by="password_hash"
        )
        assert "ORDER BY" not in cypher
        cypher, _ = build_array_any_match_query(
            Task, label=NeoLabel.TASK, field="tags", values=["x"], order_by="password_hash"
        )
        assert "ORDER BY" not in cypher

    def test_order_by_on_the_model_still_sorts(self):
        from adapters.persistence.neo4j.query.cypher import build_array_contains_query
        from core.models.enums.neo_labels import NeoLabel
        from core.models.task.task import Task

        cypher, _ = build_array_contains_query(
            Task, label=NeoLabel.TASK, field="tags", value="x", order_by="created_at"
        )
        assert "ORDER BY n.created_at DESC" in cypher


# ----------------------------------------------------------------------------
# The list route publishes no caller-supplied sort key
# ----------------------------------------------------------------------------


class TestListRouteExposesNoSortKey:
    """``GET /api/{domain}/list`` takes pagination, never an ORDER BY property.

    Neo4j cannot parameterize a property name, so a request-supplied sort key is
    interpolated; ordering rows by a property the response never renders then
    discloses that property one comparison at a time, and survives SKIP/LIMIT as
    a paginated oracle (measured on the pinned kernel — see
    docs/roadmap/field-name-guarding-in-cypher.md). No client ever sent the
    parameter, so the fix was to stop publishing it.
    """

    def test_handler_signature_has_no_sort_parameters(self):
        import inspect

        from adapters.inbound.route_factories.crud_route_factory import CRUDRouteFactory

        registered: dict[str, object] = {}

        def fake_rt(path: str):
            def decorate(handler):
                registered[path] = handler
                return handler

            return decorate

        factory = CRUDRouteFactory(
            service=MagicMock(),
            domain_name="tasks",
            create_schema=MagicMock(),
            update_schema=MagicMock(),
        )
        factory._register_list_route(fake_rt)

        handler = registered["/api/tasks/list"]
        params = set(inspect.signature(handler).parameters)
        assert "order_by" not in params
        assert "order_desc" not in params
        assert {"limit", "offset"} <= params


# ----------------------------------------------------------------------------
# A pagination window is always ordered
# ----------------------------------------------------------------------------


class TestListAlwaysCarriesASortKey:
    """``list()`` never hands the backend a null sort beside SKIP/LIMIT.

    Over an unordered result Neo4j may return the rows in a different order per
    call, so an offset window can repeat or skip a row between pages.
    """

    def test_both_branches_receive_a_sort_key(self):
        import asyncio
        from unittest.mock import AsyncMock

        from core.services.mixins.crud_operations_mixin import CrudOperationsMixin
        from core.utils.result_simplified import Result

        class _Svc(CrudOperationsMixin):  # type: ignore[type-arg]  # boundary: test double
            def __init__(self) -> None:
                self.backend = MagicMock()
                self.backend.list = AsyncMock(return_value=Result.ok(([], 0)))
                self.backend.get_user_entities = AsyncMock(return_value=Result.ok(([], 0)))

        svc = _Svc()
        asyncio.run(svc.list(limit=10, offset=10))
        assert svc.backend.list.call_args.kwargs["sort_by"] == "created_at"

        asyncio.run(svc.list(limit=10, offset=10, user_uid="u1"))
        assert svc.backend.get_user_entities.call_args.kwargs["sort_by"] == "created_at"


# ----------------------------------------------------------------------------
# One identifier guard in the persistence layer, not two
# ----------------------------------------------------------------------------


class TestPersistenceLayerSharesOneIdentifierGuard:
    """DDL and the read builders refuse the same strings because it is one function.

    ``neo4j_schema_manager`` carried private copies of ``validate_label`` and
    ``validate_identifier`` — byte-identical bodies and error messages to
    ``query/cypher/_helpers``' — behind their own copies of the label frozenset
    and the identifier regex. ``crud_queries`` then imported the shared pair
    under the ``_``-prefixed spellings the schema manager used for its own, so
    one name meant two functions depending on the module you were reading.
    """

    def test_schema_manager_uses_the_shared_guards(self):
        from adapters.persistence.neo4j import neo4j_schema_manager as sm
        from adapters.persistence.neo4j.query.cypher import _helpers

        assert sm.validate_identifier is _helpers.validate_identifier
        assert sm.validate_label is _helpers.validate_label

    def test_schema_manager_declares_no_private_copy(self):
        from adapters.persistence.neo4j import neo4j_schema_manager as sm

        for gone in ("_validate_identifier", "_validate_label", "_VALID_IDENTIFIER_RE"):
            assert not hasattr(sm, gone), f"{gone} is back — the copy re-diverged"

    def test_crud_queries_does_not_shadow_the_shared_names(self):
        from adapters.persistence.neo4j.query.cypher import _helpers, crud_queries

        assert crud_queries.validate_identifier is _helpers.validate_identifier
        assert crud_queries.validate_label is _helpers.validate_label
        assert not hasattr(crud_queries, "_validate_identifier")
        assert not hasattr(crud_queries, "_validate_label")
