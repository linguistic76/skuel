"""
Tests for Domain Route Factory — Config-Driven Registration
============================================================

16 tests covering:
  A. Sub-config instantiation (3)
  B. register_domain_routes config-driven dispatch (5)
  C. Backward compatibility (2)
  D. Factory function create_activity_domain_route_config (4)
  E. Integration round-trips (2)
"""

from dataclasses import fields as dc_fields
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from core.infrastructure.routes.domain_route_factory import (
    CRUDRouteConfig,
    DomainRouteConfig,
    IntelligenceRouteConfig,
    QueryRouteConfig,
    create_activity_domain_route_config,
    register_domain_routes,
)

# ============================================================================
# Helpers
# ============================================================================


class _FakeCreateSchema:
    pass


class _FakeUpdateSchema:
    pass


def _noop_api_factory(app: Any, rt: Any, primary: Any, **kwargs: Any) -> list[Any]:
    return []


def _noop_ui_factory(app: Any, rt: Any, primary: Any, **kwargs: Any) -> list[Any]:
    return []


def _make_services(
    primary_name: str = "tasks",
    primary_value: Any = "primary-svc",
    extras: dict[str, Any] | None = None,
) -> MagicMock:
    """Return a services container mock with the given attributes."""
    svc = MagicMock()
    setattr(svc, primary_name, primary_value)
    for k, v in (extras or {}).items():
        setattr(svc, k, v)
    return svc


# ============================================================================
# Group A — Sub-config instantiation (3 tests)
# ============================================================================


def test_crud_route_config_frozen_and_defaults():
    """CRUDRouteConfig is frozen; prometheus_metrics_attr defaults to None."""
    cfg = CRUDRouteConfig(
        create_schema=_FakeCreateSchema,
        update_schema=_FakeUpdateSchema,
        uid_prefix="task",
    )
    assert cfg.create_schema is _FakeCreateSchema
    assert cfg.update_schema is _FakeUpdateSchema
    assert cfg.uid_prefix == "task"
    assert cfg.prometheus_metrics_attr is None

    # Frozen — assignment must raise
    with pytest.raises(AttributeError):
        cfg.uid_prefix = "goal"  # type: ignore[misc]


def test_query_route_config_frozen_and_defaults():
    """QueryRouteConfig is frozen; both booleans default False."""
    cfg = QueryRouteConfig()
    assert cfg.supports_goal_filter is False
    assert cfg.supports_habit_filter is False

    cfg2 = QueryRouteConfig(supports_goal_filter=True)
    assert cfg2.supports_goal_filter is True
    assert cfg2.supports_habit_filter is False

    with pytest.raises(AttributeError):
        cfg2.supports_goal_filter = False  # type: ignore[misc]


def test_intelligence_route_config_frozen_sentinel():
    """IntelligenceRouteConfig is a frozen sentinel with no fields."""
    cfg = IntelligenceRouteConfig()
    # No user-defined fields — only the implicit ones from frozen dataclass
    user_fields = [f for f in dc_fields(cfg)]
    assert len(user_fields) == 0

    with pytest.raises(AttributeError):
        cfg.anything = 1  # type: ignore[attr-defined]


# ============================================================================
# Group B — register_domain_routes config-driven dispatch (5 tests)
# ============================================================================


@patch("core.infrastructure.routes.crud_route_factory.CRUDRouteFactory")
def test_crud_config_triggers_factory(mock_crud: MagicMock):
    """crud config → CRUDRouteFactory instantiated and .register_routes called."""
    services = _make_services()
    primary = services.tasks
    crud_cfg = CRUDRouteConfig(
        create_schema=_FakeCreateSchema,
        update_schema=_FakeUpdateSchema,
        uid_prefix="task",
    )
    config = DomainRouteConfig(
        domain_name="tasks",
        primary_service_attr="tasks",
        api_factory=_noop_api_factory,
        crud=crud_cfg,
    )

    register_domain_routes("app", "rt", services, config)

    mock_crud.assert_called_once()
    kwargs = mock_crud.call_args[1]
    assert kwargs["service"] is primary
    assert kwargs["domain_name"] == "tasks"
    assert kwargs["create_schema"] is _FakeCreateSchema
    assert kwargs["update_schema"] is _FakeUpdateSchema
    assert kwargs["uid_prefix"] == "task"
    assert kwargs["prometheus_metrics"] is None
    mock_crud.return_value.register_routes.assert_called_once_with("app", "rt")


@patch("core.infrastructure.routes.query_route_factory.CommonQueryRouteFactory")
def test_query_config_triggers_factory(mock_query: MagicMock):
    """query config → CommonQueryRouteFactory instantiated and registered."""
    user_svc = MagicMock()
    goals_svc = MagicMock()
    services = _make_services(extras={"user_service": user_svc, "goals": goals_svc})
    primary = services.tasks
    config = DomainRouteConfig(
        domain_name="tasks",
        primary_service_attr="tasks",
        api_factory=_noop_api_factory,
        api_related_services={"user_service": "user_service", "goals_service": "goals"},
        query=QueryRouteConfig(supports_goal_filter=True, supports_habit_filter=False),
    )

    register_domain_routes("app", "rt", services, config)

    mock_query.assert_called_once()
    kwargs = mock_query.call_args[1]
    assert kwargs["service"] is primary
    assert kwargs["user_service"] is user_svc
    assert kwargs["goals_service"] is goals_svc
    assert kwargs["supports_goal_filter"] is True
    assert kwargs["supports_habit_filter"] is False
    mock_query.return_value.register_routes.assert_called_once_with("app", "rt")


@patch("core.infrastructure.routes.intelligence_route_factory.IntelligenceRouteFactory")
def test_intelligence_config_triggers_factory(mock_intel: MagicMock):
    """intelligence sentinel → IntelligenceRouteFactory instantiated and registered."""
    primary = MagicMock()
    primary.intelligence = MagicMock()
    services = _make_services(primary_value=primary)
    config = DomainRouteConfig(
        domain_name="tasks",
        primary_service_attr="tasks",
        api_factory=_noop_api_factory,
        intelligence=IntelligenceRouteConfig(),
    )

    register_domain_routes("app", "rt", services, config)

    mock_intel.assert_called_once()
    kwargs = mock_intel.call_args[1]
    assert kwargs["intelligence_service"] is primary.intelligence
    assert kwargs["ownership_service"] is primary
    mock_intel.return_value.register_routes.assert_called_once_with("app", "rt")


@patch("core.infrastructure.routes.intelligence_route_factory.IntelligenceRouteFactory")
@patch("core.infrastructure.routes.query_route_factory.CommonQueryRouteFactory")
@patch("core.infrastructure.routes.crud_route_factory.CRUDRouteFactory")
def test_all_three_configs_called_in_order(mock_crud, mock_query, mock_intel):
    """All 3 sub-configs → factories called, then api_factory."""
    call_order: list[str] = []

    def track_crud(*_a, **_kw):
        call_order.append("crud")
        m = MagicMock()
        m.register_routes = lambda *_args: call_order.append("crud.register")
        return m

    def track_query(*_a, **_kw):
        call_order.append("query")
        m = MagicMock()
        m.register_routes = lambda *_args: call_order.append("query.register")
        return m

    def track_intel(*_a, **_kw):
        call_order.append("intel")
        m = MagicMock()
        m.register_routes = lambda *_args: call_order.append("intel.register")
        return m

    mock_crud.side_effect = track_crud
    mock_query.side_effect = track_query
    mock_intel.side_effect = track_intel

    primary = MagicMock()
    primary.intelligence = MagicMock()
    services = _make_services(primary_value=primary)

    def api_factory(*_a, **_kw):
        call_order.append("api_factory")
        return []

    config = DomainRouteConfig(
        domain_name="tasks",
        primary_service_attr="tasks",
        api_factory=api_factory,
        crud=CRUDRouteConfig(
            create_schema=_FakeCreateSchema, update_schema=_FakeUpdateSchema, uid_prefix="task"
        ),
        query=QueryRouteConfig(),
        intelligence=IntelligenceRouteConfig(),
    )

    register_domain_routes("app", "rt", services, config)

    # CRUD → Query → Intelligence → api_factory
    assert call_order == [
        "crud",
        "crud.register",
        "query",
        "query.register",
        "intel",
        "intel.register",
        "api_factory",
    ]


@patch("core.infrastructure.routes.crud_route_factory.CRUDRouteFactory")
def test_prometheus_metrics_attr_resolves_from_services(mock_crud: MagicMock):
    """prometheus_metrics_attr resolves the attribute from the services container."""
    prom = MagicMock(name="prometheus")
    services = _make_services(extras={"prometheus_metrics": prom})
    config = DomainRouteConfig(
        domain_name="tasks",
        primary_service_attr="tasks",
        api_factory=_noop_api_factory,
        crud=CRUDRouteConfig(
            create_schema=_FakeCreateSchema,
            update_schema=_FakeUpdateSchema,
            uid_prefix="task",
            prometheus_metrics_attr="prometheus_metrics",
        ),
    )

    register_domain_routes("app", "rt", services, config)

    kwargs = mock_crud.call_args[1]
    assert kwargs["prometheus_metrics"] is prom


# ============================================================================
# Group C — Backward compatibility (2 tests)
# ============================================================================


def test_no_sub_configs_only_api_factory_called():
    """DomainRouteConfig with NO sub-configs → only api_factory is called."""
    called: list[str] = []

    def api_factory(*_a, **_kw):
        called.append("api_factory")
        return []

    services = _make_services()
    config = DomainRouteConfig(
        domain_name="tasks",
        primary_service_attr="tasks",
        api_factory=api_factory,
    )

    register_domain_routes("app", "rt", services, config)
    assert called == ["api_factory"]


def test_none_primary_service_early_return():
    """None primary service → early return, no factories or api_factory called."""
    called: list[str] = []

    def api_factory(*_a, **_kw):
        called.append("api_factory")
        return []

    # services has no 'tasks' attr
    services = MagicMock(spec=[])
    config = DomainRouteConfig(
        domain_name="tasks",
        primary_service_attr="tasks",
        api_factory=api_factory,
        crud=CRUDRouteConfig(
            create_schema=_FakeCreateSchema, update_schema=_FakeUpdateSchema, uid_prefix="task"
        ),
    )

    result = register_domain_routes("app", "rt", services, config)
    assert result == []
    assert called == []


# ============================================================================
# Group D — Factory function (4 tests)
# ============================================================================


def test_factory_produces_correct_structure():
    """create_activity_domain_route_config returns a fully populated DomainRouteConfig."""
    cfg = create_activity_domain_route_config(
        domain_name="tasks",
        primary_service_attr="tasks",
        api_factory=_noop_api_factory,
        ui_factory=_noop_ui_factory,
        create_schema=_FakeCreateSchema,
        update_schema=_FakeUpdateSchema,
        uid_prefix="task",
        supports_goal_filter=True,
        supports_habit_filter=False,
        api_related_services={"goals_service": "goals"},
        prometheus_metrics_attr="prometheus_metrics",
    )

    assert isinstance(cfg, DomainRouteConfig)
    assert cfg.domain_name == "tasks"
    assert cfg.primary_service_attr == "tasks"
    assert cfg.api_factory is _noop_api_factory
    assert cfg.ui_factory is _noop_ui_factory

    # CRUD sub-config
    assert cfg.crud is not None
    assert cfg.crud.create_schema is _FakeCreateSchema
    assert cfg.crud.update_schema is _FakeUpdateSchema
    assert cfg.crud.uid_prefix == "task"
    assert cfg.crud.prometheus_metrics_attr == "prometheus_metrics"

    # Query sub-config
    assert cfg.query is not None
    assert cfg.query.supports_goal_filter is True
    assert cfg.query.supports_habit_filter is False

    # Intelligence sentinel
    assert cfg.intelligence is not None


def test_factory_auto_adds_user_service():
    """user_service is auto-added to api_related_services when missing."""
    cfg = create_activity_domain_route_config(
        domain_name="goals",
        primary_service_attr="goals",
        api_factory=_noop_api_factory,
        create_schema=_FakeCreateSchema,
        update_schema=_FakeUpdateSchema,
        uid_prefix="goal",
        api_related_services={"goals_service": "goals"},
    )

    assert "user_service" in cfg.api_related_services
    assert cfg.api_related_services["user_service"] == "user_service"
    # Original key preserved
    assert cfg.api_related_services["goals_service"] == "goals"


def test_factory_does_not_duplicate_user_service():
    """user_service is NOT duplicated when already present."""
    cfg = create_activity_domain_route_config(
        domain_name="goals",
        primary_service_attr="goals",
        api_factory=_noop_api_factory,
        create_schema=_FakeCreateSchema,
        update_schema=_FakeUpdateSchema,
        uid_prefix="goal",
        api_related_services={"user_service": "custom_user_svc"},
    )

    # Caller's value wins (setdefault semantics)
    assert cfg.api_related_services["user_service"] == "custom_user_svc"


def test_factory_threads_prometheus_metrics_attr():
    """prometheus_metrics_attr is threaded through to CRUDRouteConfig."""
    cfg = create_activity_domain_route_config(
        domain_name="habits",
        primary_service_attr="habits",
        api_factory=_noop_api_factory,
        create_schema=_FakeCreateSchema,
        update_schema=_FakeUpdateSchema,
        uid_prefix="habit",
        prometheus_metrics_attr="prom",
    )

    assert cfg.crud is not None
    assert cfg.crud.prometheus_metrics_attr == "prom"


# ============================================================================
# Group E — Integration (2 tests)
# ============================================================================


@patch("core.infrastructure.routes.intelligence_route_factory.IntelligenceRouteFactory")
@patch("core.infrastructure.routes.query_route_factory.CommonQueryRouteFactory")
@patch("core.infrastructure.routes.crud_route_factory.CRUDRouteFactory")
def test_full_roundtrip_factory_to_register(mock_crud, mock_query, mock_intel):
    """Factory function → register_domain_routes → all 3 factories called."""
    primary = MagicMock()
    primary.intelligence = MagicMock()
    services = _make_services(
        primary_value=primary,
        extras={
            "user_service": MagicMock(),
            "goals": MagicMock(),
            "habits": MagicMock(),
            "prometheus_metrics": MagicMock(),
        },
    )

    api_called: list[bool] = []

    def api_factory(*_a, **_kw):
        api_called.append(True)
        return []

    config = create_activity_domain_route_config(
        domain_name="tasks",
        primary_service_attr="tasks",
        api_factory=api_factory,
        create_schema=_FakeCreateSchema,
        update_schema=_FakeUpdateSchema,
        uid_prefix="task",
        supports_goal_filter=True,
        supports_habit_filter=True,
        api_related_services={
            "user_service": "user_service",
            "goals_service": "goals",
            "habits_service": "habits",
        },
        prometheus_metrics_attr="prometheus_metrics",
    )

    register_domain_routes("app", "rt", services, config)

    # All three factories instantiated
    mock_crud.assert_called_once()
    mock_query.assert_called_once()
    mock_intel.assert_called_once()
    # api_factory also ran
    assert api_called == [True]


def test_api_factory_kwargs_absorbs_extra_related_services():
    """api_factory with **_kwargs absorbs extra related services without error."""
    received_kwargs: dict[str, Any] = {}

    def api_factory(app: Any, rt: Any, primary: Any, **kwargs: Any) -> list[Any]:
        received_kwargs.update(kwargs)
        return []

    services = _make_services(
        extras={
            "user_service": "user-svc",
            "goals": "goals-svc",
            "habits": "habits-svc",
        }
    )
    config = DomainRouteConfig(
        domain_name="tasks",
        primary_service_attr="tasks",
        api_factory=api_factory,
        api_related_services={
            "user_service": "user_service",
            "goals_service": "goals",
            "habits_service": "habits",
        },
    )

    # No sub-configs — goes straight to api_factory with all related services
    register_domain_routes("app", "rt", services, config)

    assert received_kwargs["user_service"] == "user-svc"
    assert received_kwargs["goals_service"] == "goals-svc"
    assert received_kwargs["habits_service"] == "habits-svc"
