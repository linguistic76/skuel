# Intelligence Protocols and the Route Factory

Three protocols touch the intelligence services: one in `core/ports`, and the route factory's
pair on the other side of the hexagonal boundary.

| Protocol | Location | Satisfied by |
|----------|----------|--------------|
| `KnowledgeIntelligenceOperations` | `core/ports/intelligence_protocols.py` | `ActivityKnowledgeIntelligenceService` — one shared instance |
| `IntelligenceOperations[T]` | `adapters/inbound/route_factories/intelligence_route_factory.py` | The nine per-domain services — none names it as a base |
| `PerformanceAnalyticsOperations` | `adapters/inbound/route_factories/intelligence_route_factory.py` | The six Activity services — none names it as a base |

The per-domain services share no `core/ports` protocol. Their common contract is the route
factory's.

---

## `KnowledgeIntelligenceOperations`

```python
@runtime_checkable
class KnowledgeIntelligenceOperations(Protocol):
    async def get_knowledge_suggestions(
        self, user_uid: UserUID, entity_uid: EntityUID | None = None
    ) -> Result[KnowledgeSuggestionsResult]: ...

    async def get_knowledge_prerequisites(
        self, entity_uid: EntityUID
    ) -> Result[KnowledgePrerequisitesResult]: ...

    async def generate_knowledge_from_entities(
        self, user_uid: UserUID, period_days: int = 30
    ) -> Result[KnowledgeGenerationResult]: ...

    async def get_learning_opportunities(
        self, user_uid: UserUID
    ) -> Result[LearningOpportunitiesResult]: ...
```

`ActivityKnowledgeIntelligenceService` is built once in `compose_services` and passed to each
Activity facade, which holds it as `self.knowledge_intelligence`. The four facade methods come
from `KnowledgeIntelligenceDelegationMixin` (`core/services/mixins/`), inherited by all six
facades.

Its backend is `UniversalNeo4jBackend[Entity]` on the `:Entity` label, so it reads across entity
types. `find_by(user_uid=...)` matches the `user_uid` property; shared curriculum carries none
and drops out of a user-scoped read.

---

## `IntelligenceOperations[T]` and `PerformanceAnalyticsOperations`

```python
class IntelligenceOperations(Protocol[T]):
    async def get_with_context(
        self, uid: str, depth: int = 2
    ) -> Result[tuple[T, GraphContext]]: ...

    async def get_domain_insights(
        self, uid: str, min_confidence: float = 0.7
    ) -> Result[IntelligencePayload]: ...


class PerformanceAnalyticsOperations(Protocol):
    async def get_performance_analytics(
        self, user_uid: UserUID, period_days: int = 30
    ) -> Result[IntelligencePayload]: ...
```

`IntelligencePayload = dict[str, Any]  # boundary: route-factory erased-T` — one factory serves
each routed domain, so the payload's shape varies per domain and the factory reads none of its
keys. A service may declare a TypedDict for its own payload (`PsDomainInsights`,
`LpDomainInsights`).

The split follows who has a per-user set to aggregate. The per-entity reads exist for a
domain at either scope; the per-user aggregate exists for a user-owned domain. KU, PS and LP
are shared curriculum and implement `IntelligenceOperations` alone.

### `get_with_context` — inherited

```python
# core/services/intelligence/_core_intelligence_mixin.py
class _CoreIntelligenceMixin[T]:
    @requires_graph_intelligence("get_with_context")
    async def get_with_context(self, uid: str, depth: int = 2) -> Result[tuple[T, GraphContext]]:
        if self.relationships is None:
            return Result.fail(
                Errors.system(
                    message="relationship_service required for get_with_context",
                    operation="get_with_context",
                )
            )
        return await self.relationships.get_with_context(uid, depth)
```

Two dependencies, two failures: without `graph_intel` the decorator returns `Result.fail`;
without a relationship service the inline check does.

### `GraphContext`

`core/models/graph_context.py`. The context is nodes and relationships, not typed entity lists:

| Field | Type |
|-------|------|
| `origin_uid`, `origin_domain`, `query_intent` | `str`, `Domain`, `str` |
| `all_nodes` | `list[GraphNode]` |
| `all_relationships` | `list[GraphRelationship]` |
| `domain_contexts` | `dict[Domain, DomainContext]` |
| `cross_domain_insights` | `list[dict[str, Any]]` |
| `relationship_patterns` | `dict[str, int]` — relationship type to count |
| `total_nodes`, `total_relationships`, `max_depth_reached` | `int` |
| `domains_involved` | `list[Domain]` |
| `query_timestamp` | `datetime` |
| `neo4j_query_time_ms`, `processing_time_ms` | `float \| None` |

Methods: `get_nodes_by_domain(domain)`, `get_published_knowledge_nodes()`,
`get_relationships_by_type(rel_type)`, `get_strongest_relationships(limit=10)`,
`get_connected_domains()`, `has_cross_domain_connections()` and `get_summary()`.

`get_published_knowledge_nodes()` decides kind by the stored `entity_type` and withholds a node
whose `publication_state` is `draft`. Because the traversal is not owner-scoped, that filter is
also what keeps another user's entities out of a knowledge read — use it, rather than filtering
`all_nodes` by hand, when showing curriculum to a learner.

For typed, per-domain entity lists use `_analyze_entity_with_typed_context` (see
[SKILL.md](SKILL.md)), not `GraphContext`.

---

## `IntelligenceRouteFactory`

```python
from adapters.inbound.route_factories import IntelligenceRouteFactory
```

```python
IntelligenceRouteFactory(
    intelligence_service=...,          # satisfies IntelligenceOperations
    domain_name="tasks",
    base_path=None,                    # default: /api/{domain_name}
    enable_analytics=True,
    enable_context=True,
    enable_insights=True,
    scope=ContentScope.USER_OWNED,     # or ContentScope.SHARED
    ownership_service=...,             # required when scope is USER_OWNED
).register_routes(app, rt)
```

- `scope=ContentScope.USER_OWNED` without an `ownership_service` raises `ValueError` at
  construction. A misconfigured factory does not start.
- `scope=ContentScope.USER_OWNED` with analytics enabled, over a service that has no
  `get_performance_analytics`, raises `ValueError` at construction.
- `scope=ContentScope.SHARED` registers no analytics route, whatever `enable_analytics` says
  and whatever the service offers.
- `ownership_service` is anything with `verify_ownership(uid, user_uid) -> Result[...]` — in
  practice the domain facade.
- There is no `verify_ownership=` keyword; `scope` decides.

### Routes

Each is registered with `methods=["GET"]`.

| Route | Calls | Query parameters | Scope |
|-------|-------|------------------|-------|
| `GET {base_path}/context` | `get_with_context(uid, depth)` | `uid` (required), `depth=2` | either |
| `GET {base_path}/insights` | `get_domain_insights(uid, min_confidence)` | `uid` (required), `min_confidence=0.7` | either |
| `GET {base_path}/analytics` | `get_performance_analytics(user_uid, period_days)` | `period_days=30` | `USER_OWNED` |

`user_uid` always comes from the session. A `user_uid` query parameter is ignored.

The context route answers `{"entity": <the entity>, "context": <GraphContext.get_summary()>}`;
the HTTP boundary serializes the entity as it does a CRUD read's. The analytics and insights
routes return the service's payload unchanged.

### Measured behavior

Reproduced with a `TestClient` against the factory:

| Request | Status |
|---------|--------|
| Any registered route, no session — either scope | 401 |
| `POST`, `PUT` or `DELETE` to any registered route | 405 |
| `SHARED`: `GET {base_path}/analytics` | 404 — not registered |
| `context` / `insights` with no `uid` | 400 |
| `depth=abc` (a value the annotation cannot coerce) | 404 |
| `USER_OWNED`: a uid the user does not own | 404 |
| `USER_OWNED`: a uid that does not exist | 404 |
| `SHARED`: any existing uid | 200 — no ownership check |

A foreign uid and a missing uid answer identically, so the route is not an existence oracle.
`SHARED` still requires a signed-in user.

### How a domain gets the routes

Through its `DomainRouteConfig`, not by constructing the factory in a route file:

```python
# Activity domains — create_activity_domain_route_config() sets this default
intelligence=IntelligenceRouteConfig()

# Shared curriculum
intelligence=IntelligenceRouteConfig(scope=ContentScope.SHARED)
```

`register_domain_routes` then builds the factory with the facade's `.intelligence` as the
service and the facade itself as `ownership_service`.

| Domain | `domain_name` | Routes |
|--------|---------------|--------|
| Tasks, Goals, Habits, Events, Choices, Principles | `tasks`, `goals`, … | context, insights, analytics — `USER_OWNED` |
| PathStep | `path-steps` | context, insights — `SHARED` |
| LearningPath | `pathways` | context, insights — `SHARED` |
| KU | — | **no** — `KU_CONFIG` sets no `IntelligenceRouteConfig` |

`KuIntelligenceService` is still reached over HTTP for mastery check-ins:
`POST /explore/ku/{uid}/mastery-checkin` calls `assess_mastery_dual_track`.

See the [domain-route-config](../domain-route-config/SKILL.md) skill.

---

## Adding a Domain

1. Write the service: `_CoreIntelligenceMixin[Model]` first, then
   `BaseAnalyticsService[BackendProtocol, Model]`. Give it `get_domain_insights`, and — for a
   user-owned domain — `get_performance_analytics`.
2. Build it where the facade is built and store it on the facade's `intelligence` slot.
3. Pass both `graph_intel` and the domain's relationship service (`relationship_service`).
   `get_with_context` returns a failed `Result` without either, so the generated context route
   cannot answer.
4. Set `intelligence=IntelligenceRouteConfig(...)` on the domain's route config. Choose the
   scope by who owns the entity: `USER_OWNED` needs `verify_ownership` on the facade.
5. Add the per-domain guide under `docs/intelligence/`.

In the walkthrough below, `Widget` and `WidgetOperations` are placeholders for the new domain's
model and backend protocol:

```python
class WidgetIntelligenceService(
    _CoreIntelligenceMixin[Widget],
    BaseAnalyticsService[WidgetOperations, Widget],
):
    _service_name = "widgets.intelligence"
    _require_relationships = True

    async def get_performance_analytics(
        self, user_uid: UserUID, period_days: int = 30
    ) -> Result[dict[str, Any]]:  # boundary: per-domain analytics payload
        widgets_result = await find_all_by(
            self.backend, self.logger, "Widget performance analytics", user_uid=user_uid
        )
        if widgets_result.is_error:
            return Result.fail(widgets_result)

        widgets = widgets_result.value or []
        return Result.ok({"user_uid": user_uid, "period_days": period_days, "total": len(widgets)})
```

---

## Testing

| What | Where |
|------|-------|
| The factory | `tests/unit/infrastructure/test_intelligence_route_factory.py` |
| The route set per scope, over real HTTP with the composed services | `tests/integration/routes/test_intelligence_route_set.py` |
| The services, on a real graph | `tests/integration/intelligence/` |

The factory tests patch `require_authenticated_user` in the factory's module and pass a stub
service and a stub ownership verifier. A stub `GraphContext` needs only `get_summary()`.

To test `get_with_context` on a service, give it a relationship service whose
`get_with_context` returns `Result.ok((entity, graph_context))` and a non-`None` `graph_intel`;
assert on the `Result`, then unpack the tuple.
