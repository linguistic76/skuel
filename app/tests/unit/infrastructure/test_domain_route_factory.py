"""
Tests for Domain Route Factory — Config-Driven Registration
============================================================

Groups:
  A. Sub-config instantiation
  B. register_domain_routes config-driven dispatch
  C. Configs without sub-configs
  D. Factory function create_activity_domain_route_config
  E. Integration round-trips
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from adapters.inbound.route_factories.domain_route_factory import (
    CRUDRouteConfig,
    DomainRouteConfig,
    IntelligenceRouteConfig,
    QueryRouteConfig,
    create_activity_domain_route_config,
    register_domain_routes,
)
from tests.helpers.route_collector import route_collector

# ============================================================================
# Helpers
# ============================================================================


class _FakeCreateSchema:
    pass


class _FakeUpdateSchema:
    pass


def _noop_api_factory(rt: object, primary: object, **kwargs: object) -> None:
    pass


def _noop_ui_factory(rt: object, primary: object, **kwargs: object) -> None:
    pass


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
# Group A — Sub-config instantiation
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


def test_intelligence_route_config_defaults():
    """IntelligenceRouteConfig defaults to USER_OWNED scope."""
    from core.models.enums import ContentScope

    cfg = IntelligenceRouteConfig()
    assert cfg.scope == ContentScope.USER_OWNED

    with pytest.raises(AttributeError):
        cfg.anything = 1  # type: ignore[attr-defined]


# ============================================================================
# Group B — register_domain_routes config-driven dispatch
# ============================================================================


@patch("adapters.inbound.route_factories.crud_route_factory.CRUDRouteFactory")
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

    rt, _ = route_collector()

    register_domain_routes(rt, services, config)

    mock_crud.assert_called_once()
    kwargs = mock_crud.call_args[1]
    assert kwargs["service"] is primary
    assert kwargs["domain_name"] == "tasks"
    assert kwargs["create_schema"] is _FakeCreateSchema
    assert kwargs["update_schema"] is _FakeUpdateSchema
    assert kwargs["uid_prefix"] == "task"
    assert kwargs["prometheus_metrics"] is None
    mock_crud.return_value.register_routes.assert_called_once_with(rt)


@patch("adapters.inbound.route_factories.query_route_factory.CommonQueryRouteFactory")
def test_query_config_triggers_factory(mock_query: MagicMock):
    """query config → CommonQueryRouteFactory takes its services from the container.

    The api mapping is empty: the query routes' user and goal services do not
    travel in it, and the habit service stays out while the habit filter is off.
    """
    user_svc = MagicMock()
    goals_svc = MagicMock()
    habits_svc = MagicMock()
    services = _make_services(extras={"user": user_svc, "goals": goals_svc, "habits": habits_svc})
    primary = services.tasks
    config = DomainRouteConfig(
        domain_name="tasks",
        primary_service_attr="tasks",
        api_factory=_noop_api_factory,
        query=QueryRouteConfig(supports_goal_filter=True, supports_habit_filter=False),
    )

    rt, _ = route_collector()

    register_domain_routes(rt, services, config)

    mock_query.assert_called_once()
    kwargs = mock_query.call_args[1]
    assert kwargs["service"] is primary
    assert kwargs["user_service"] is user_svc
    assert kwargs["goals_service"] is goals_svc
    assert kwargs["habits_service"] is None
    assert kwargs["supports_goal_filter"] is True
    assert kwargs["supports_habit_filter"] is False
    mock_query.return_value.register_routes.assert_called_once_with(rt)


@patch("adapters.inbound.route_factories.intelligence_route_factory.IntelligenceRouteFactory")
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

    rt, _ = route_collector()

    register_domain_routes(rt, services, config)

    mock_intel.assert_called_once()
    kwargs = mock_intel.call_args[1]
    assert kwargs["intelligence_service"] is primary.intelligence
    assert kwargs["ownership_service"] is primary
    mock_intel.return_value.register_routes.assert_called_once_with(rt)


@patch("adapters.inbound.route_factories.intelligence_route_factory.IntelligenceRouteFactory")
@patch("adapters.inbound.route_factories.query_route_factory.CommonQueryRouteFactory")
@patch("adapters.inbound.route_factories.crud_route_factory.CRUDRouteFactory")
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

    rt, _ = route_collector()

    register_domain_routes(rt, services, config)

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


@patch("adapters.inbound.route_factories.crud_route_factory.CRUDRouteFactory")
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

    rt, _ = route_collector()

    register_domain_routes(rt, services, config)

    kwargs = mock_crud.call_args[1]
    assert kwargs["prometheus_metrics"] is prom


# ============================================================================
# Group C — Configs without sub-configs
# ============================================================================


def test_no_sub_configs_only_api_factory_called():
    """DomainRouteConfig with NO sub-configs → only api_factory is called."""
    called: list[str] = []

    def api_factory(*_a, **_kw):
        called.append("api_factory")

    services = _make_services()
    config = DomainRouteConfig(
        domain_name="tasks",
        primary_service_attr="tasks",
        api_factory=api_factory,
    )

    rt, _ = route_collector()

    register_domain_routes(rt, services, config)
    assert called == ["api_factory"]


def test_none_primary_service_early_return():
    """None primary service → early return, no factories or api_factory called."""
    called: list[str] = []

    def api_factory(*_a, **_kw):
        called.append("api_factory")

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

    rt, _ = route_collector()

    register_domain_routes(rt, services, config)
    assert called == []


# ============================================================================
# Group D — Factory function
# ============================================================================


def test_factory_produces_correct_structure():
    """create_activity_domain_route_config returns a fully populated DomainRouteConfig."""
    cfg = create_activity_domain_route_config(
        domain_name="tasks",
        request_create_method="create_task",
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
    assert cfg.crud.request_create_method == "create_task"
    assert cfg.crud.prometheus_metrics_attr == "prometheus_metrics"

    # Query sub-config
    assert cfg.query is not None
    assert cfg.query.supports_goal_filter is True
    assert cfg.query.supports_habit_filter is False

    # Intelligence sentinel
    assert cfg.intelligence is not None


def test_factory_passes_the_api_mapping_through_unchanged():
    """The api mapping is exactly the caller's — nothing is added for the query routes."""
    cfg = create_activity_domain_route_config(
        domain_name="habits",
        request_create_method="create_habit",
        primary_service_attr="habits",
        api_factory=_noop_api_factory,
        create_schema=_FakeCreateSchema,
        update_schema=_FakeUpdateSchema,
        uid_prefix="habit",
        api_related_services={"principles_service": "principles"},
    )

    assert cfg.api_related_services == {"principles_service": "principles"}


def test_factory_threads_prometheus_metrics_attr():
    """prometheus_metrics_attr is threaded through to CRUDRouteConfig."""
    cfg = create_activity_domain_route_config(
        domain_name="habits",
        request_create_method="create_task",
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
# Group E — Integration
# ============================================================================


@patch("adapters.inbound.route_factories.intelligence_route_factory.IntelligenceRouteFactory")
@patch("adapters.inbound.route_factories.query_route_factory.CommonQueryRouteFactory")
@patch("adapters.inbound.route_factories.crud_route_factory.CRUDRouteFactory")
def test_full_roundtrip_factory_to_register(mock_crud, mock_query, mock_intel):
    """Factory function → register_domain_routes → all 3 factories called."""
    primary = MagicMock()
    primary.intelligence = MagicMock()
    services = _make_services(
        primary_value=primary,
        extras={
            "user": MagicMock(),
            "goals": MagicMock(),
            "habits": MagicMock(),
            "prometheus_metrics": MagicMock(),
        },
    )

    api_called: list[bool] = []

    def api_factory(*_a, **_kw):
        api_called.append(True)

    config = create_activity_domain_route_config(
        domain_name="tasks",
        request_create_method="create_task",
        primary_service_attr="tasks",
        api_factory=api_factory,
        create_schema=_FakeCreateSchema,
        update_schema=_FakeUpdateSchema,
        uid_prefix="task",
        supports_goal_filter=True,
        supports_habit_filter=True,
        prometheus_metrics_attr="prometheus_metrics",
    )

    rt, _ = route_collector()

    register_domain_routes(rt, services, config)

    # All three factories instantiated
    mock_crud.assert_called_once()
    mock_query.assert_called_once()
    mock_intel.assert_called_once()
    # api_factory also ran
    assert api_called == [True]


def test_api_factory_receives_its_mapping_as_keywords():
    """Each mapping key arrives as the keyword of the same name, resolved on the container."""
    received_kwargs: dict[str, object] = {}

    def api_factory(
        rt: object,
        primary: object,
        *,
        user_service: object,
        goals_service: object,
        habits_service: object,
    ) -> None:
        received_kwargs.update(
            user_service=user_service, goals_service=goals_service, habits_service=habits_service
        )

    services = _make_services(
        extras={
            "user": "user_svc",
            "goals": "goals-svc",
            "habits": "habits-svc",
        }
    )
    config = DomainRouteConfig(
        domain_name="tasks",
        primary_service_attr="tasks",
        api_factory=api_factory,
        api_related_services={
            "user_service": "user",
            "goals_service": "goals",
            "habits_service": "habits",
        },
    )

    # No sub-configs — goes straight to api_factory with its related services
    rt, _ = route_collector()
    register_domain_routes(rt, services, config)

    assert received_kwargs["user_service"] == "user_svc"
    assert received_kwargs["goals_service"] == "goals-svc"
    assert received_kwargs["habits_service"] == "habits-svc"
