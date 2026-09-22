"""
Hardening: field-key validation in the Cypher-fragment allowlists
=================================================================

Closes 2026-05-26 security audit item #3 ("field-key validation gaps in
optimization/builder layers — not exploitable today"). Covers the two gates
below: `validate_field_name`, the identifier allowlist, and
`ModelQueryBuilder.filter`, which drops an unsafe key rather than passing it on.

That is a claim about these two, not about the persistence layer as a whole.
Some backends interpolate a property name their caller hands them without a
check — `_relationship_ordered_mixin`'s `order_by_property`,
`PsBackend.list_steps_raw`'s `order_field` — and a third gate,
`_ALLOWED_ORDER_BY` in `_backend_helpers.py`, guards two further sites with an
explicit frozenset. Every one of those callers passes a literal or a registry
constant, so the audit's classification holds; the coverage gap is real and
ruled a separate concern.

Comparison operators and sort directions are guarded a stronger way and so have
no validator here: no builder interpolates a caller's operator or direction at
all. Operators are chosen by structural dispatch (`build_search_query`'s
if/elif chain, `intelligence_queries`' guarded `op_map`, `batch_cypher_builder`'s
`_FILTER_OP_MAP`), which emits a literal and cannot emit an unknown one.
Directions resolve to `"ASC"`/`"DESC"` from a bool, from the developer-authored
`RelationshipSpec.order_direction`, or from a literal at the call site. A
validator for either would check a value that never varies.

These tests guard the latent seam: a caller that hands user input to either
gate below gets it rejected or dropped, not interpolated.
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
