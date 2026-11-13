---
updated: 2026-11-13
---

# Any Usage Policy

*Last updated: 2026-07-28*

SKUEL treats `Any` as a last resort, not a default. Every use of `Any` must belong to one
of the three categories below. Unlabelled `Any` annotations are technical debt and should
be refactored toward a specific type.

---

## Category A — Lazy Typing (Must Not Exist)

These are `Any` uses that exist out of habit or because no one got around to typing them.
They provide no value and actively undermine type safety.

**Examples of Category A (now fixed):**
- `logger: Any` — Should always be `logging.Logger`
- `driver: Any` (concrete `__init__` parameter) — Should be `neo4j.AsyncDriver`
- `prometheus_metrics: Any` — Should be `PrometheusMetrics | None`
- `services: Any` (in route factories) — Should be `Services | None`
- `priority: Any` in Protocol attributes — Should be the specific enum
- `UserOperations` return types — Were `Result[Any]`, now `Result[User]` / `Result[UserContext]` (no circular import existed)
- `get_active_learners` — Was `Result[list[Any]]`, now `Result[list[User]]`
- `bookmark_knowledge` `tags` param — Was `list | None`, now `list[str] | None`
- `SubmissionOperations.list_submissions()` params — Were `entity_type: Any`, `status: Any`, now `EntityType`, `EntityStatus`
- `SubmissionOperations.set_visibility()` — Was `visibility: Any`, now `Visibility`
- `EntryReportOperations.generate_report()` — Were `entry: Any`, `exercise: Any`, now the typed `AdmittedReport` proof (`UserEntry`, `Exercise`)
- `TeacherReviewService.__init__()` — Was `ku_interaction_service: Any`, now `LessonMasteryService`
- `ReviewQueueOperations.request_review()` — Was `Result[dict[str, Any]]`, now `Result[ReviewRequestResult]`
- `ReviewQueueOperations.get_pending_reviews()` — Was `Result[list[dict[str, Any]]]`, now `Result[list[PendingReviewItem]]`
- `TeacherReviewOperations.get_group_detail()` — Was `Result[list[dict[str, Any]]]`, now `Result[list[GroupMemberProgress]]`
- `PsBackend.get_step_with_knowledge()` / `get_standalone_steps()` — Were `Result[list[dict[str, Any]]]`, now `Result[PathStep | None]` / `Result[list[PathStep]]` (the typed model)
- `FormTemplateBackend.get_forms_for_path_step()` — Was `Result[list[dict[str, Any]]]`, now `Result[list[Neo4jProperties]]` (reuses existing alias)

If you encounter Category A `Any` during development, fix it immediately. There is no
architectural reason for these to exist.

---

## Category B — Reducible (Use Specific Types Below)

These `Any` uses can be replaced with more precise types that SKUEL defines.

### Neo4j Boundary Types

When handling raw data from the Neo4j driver, use these aliases instead of `dict[str, Any]`:

```python
from core.models.type_hints import Neo4jProperties, Neo4jValue

# For node property dicts from the driver
node_data: Neo4jProperties  # = dict[str, Neo4jValue]

# For individual values
value: Neo4jValue  # = str | int | float | bool | list[...] | None | datetime
```

**When to use:** `from_neo4j_node()`, any function that accepts raw Neo4j node data as input.

### Filter/Query Parameters

When accepting search or filter parameters with known value shapes:

```python
from core.models.type_hints import FilterParams, FilterValue

async def find_by_filters(filters: FilterParams) -> list[Entity]: ...
# FilterParams = dict[str, FilterValue]
# FilterValue = str | int | float | bool | list[str | int | float] | None
```

**When to use:** Search service methods, `find_by()` style functions.

### Relationship Metadata

The `RelationshipMetadata` TypedDict (in `core/ports/base_protocols.py`) covers 27 common
relationship edge properties. Use it instead of `Metadata` for relationship operations.

```python
from core.ports.base_protocols import RelationshipMetadata

async def create_relationship(
    from_uid: str, to_uid: str, properties: RelationshipMetadata | None = None
) -> Result[bool]: ...
```

### Generic Function Types

Instead of `Callable[[Any], bool]`, use the generic versions:

```python
from core.models.type_hints import EntityFilter, Validator, Scorer

sorter: EntityFilter[Task]   # = Callable[[Task], bool]
scorer: Scorer[Goal]         # = Callable[[Goal], Score]
validator: Validator[Habit]  # = Callable[[Habit], list[str]]
```

---

### Protocol Layer Adoption (March 2026)

**Phase 3 — Input parameters:** All protocol files now use typed aliases instead of `dict[str, Any]`:

- `CrudOperations.update()` → `updates: Neo4jProperties`
- `CrudOperations.list()`, `EntitySearchOperations.get_user_entities()` → `filters: FilterParams`
- `RelationshipCrudOperations`, `RelationshipQueryOperations` → `properties: Neo4jProperties`
- `RelationshipMetadataOperations.get_relationships_batch()` → returns `list[RelationshipMetadata]`
- Domain CRUD params (`create_goal`, `update_habit`, etc.) → `Metadata`

**Phase 4 — Return types:** ~170 protocol methods migrated from `Result[Any]` to specific types (0 `Result[Any]` remain in protocols, 2 intentional: `base_service_interface.py` and `OwnershipVerifier.verify_ownership` in `service_protocols.py` — the latter is a narrow internal callback protocol used by `LateralRelationshipService` and `LateralRelationshipsOrchestrator` to accept any domain facade's `verify_ownership(uid, user_uid) -> Result[T]`; `Result[T]` is invariant, each facade returns a different concrete `T`, and callers only branch on `.is_error`):

- **Domain model returns:** `Result[SubmissionEntity]`, `Result[EntryReport]`, `Result[Askesis]`,
  `Result[CalendarData]`, `Result[Group]`, `Result[UserEntry]`, `Result[Exercise]`,
  `Result[FormTemplate]`, `Result[FormSubmission]`, `Result[ActivityReport]`
- **110 output TypedDicts** in `query_types.py` for structured dict returns:

| TypedDict | Protocol / Field | Methods |
|-----------|-----------------|---------|
| `SignUpResult`, `SignInResult` | `GraphAuthOperations` | `sign_up`, `sign_in` |
| `ReviewQueueItem`, `SubmissionDetailResult`, `TeacherDashboardStats`, `GroupMemberProgress` | `TeacherReviewOperations` | `get_review_queue`, `get_submission_detail`, `get_dashboard_stats`, `get_group_detail` |
| `ReviewRequestResult`, `PendingReviewItem` | `ReviewQueueOperations` | `request_review`, `get_pending_request`, `get_pending_reviews` |
| `KnowledgeSuggestionsResult`, `KnowledgeGenerationResult`, `LearningOpportunitiesResult` | `KnowledgeIntelligenceOperations` | `get_knowledge_suggestions`, `generate_knowledge_from_entities`, `get_learning_opportunities` |
| `KnowledgePrerequisitesResult`, `KnowledgePrerequisiteItem` | `KnowledgeIntelligenceOperations` | `get_knowledge_prerequisites` |
| `LifePathStatus`, `VisionData`, `SavedVision`, `LpMatchResult`, `LpMatches`, `LifePathRecommendation`, `LifePathDesignation`, `LifePathAlignmentResult` | `LifePathOperations`, `LifePathAlignmentOperations` | `get_full_status`, `capture_vision`, `get_vision`, `match_learning_paths`, `capture_and_recommend`, `designate_and_calculate`, `get_alignment`, `calculate_alignment` |
| `LateralRelationshipItem`, `BlockingChainResult`, `RelationshipGraphData` | `LateralRelationshipOperations` | `get_lateral_relationships`, `get_blocking_chain`, `get_relationship_graph` |
| `AnnotationResult`, `AnnotationState`, `PrivacySummary` | `ActivityReportOperations` | `annotate`, `get_annotation`, `get_privacy_summary` |
| `SystemHealthStatus`, `HealthCheckValidation`, `ComponentHealthStatus`, `HealthCheckerValidationResult` | `SystemServiceOperations` | `get_health_status`, `validate_health_checkers` |
| `RichEntityItem`, `RichKnowledgeUnitItem`, `RichLearningPathItem`, `RichPathStepItem` | `UserContext` fields | `entities_rich`, `knowledge_units_rich`, `enrolled_paths_rich`, `active_path_steps_rich` |
| `UnsubmittedExerciseItem`, `PendingRevisedExerciseItem` | `UserContext` fields | `unsubmitted_exercises`, `pending_revised_exercises` |
| `CrossDomainInsightsData`, `CrossDomainInsightItem` | `UserContext` field | `cross_domain_insights` |
| `NextActionResult`, `AtRiskHabitsResult`, `AdaptiveLearningPathResult`, `FutureContextStateResult`, `ContextHealthResult` | `ContextAwareOperations` | `get_next_action`, `get_at_risk_habits`, `get_adaptive_learning_path`, `predict_future_context_state`, `get_context_health` |
| `GraphInfluenceItem`, `RelationshipSummaryResult` | `GraphEntity` | `get_upstream_influences`, `get_downstream_impacts`, `get_relationship_summary` |
| `PsKnowledgeSummaryResult`, `PsPracticeSummaryResult`, `UserProgressResult` | `CurriculumOperations`, `PsOperations` | `get_knowledge_summary`, `get_practice_summary`, `get_user_progress` |

**Phase 5 — Route handler returns:** All 27 `*_api.py` route files narrowed from `Result[Any]` to specific types (267 → 2). The 2 remaining are intentional `# boundary:` annotations for FastHTML FT components without type stubs. Cross-type error propagation sites fixed using `Result.fail(result)` instead of bare `return result`.

---

## Category C — Permanent Boundaries (Document with `# boundary:`)

These `Any` uses represent genuine limits of Python's type system or the capabilities of
third-party libraries. They cannot be eliminated without disproportionate effort or loss
of expressiveness. All must be annotated with a `# boundary:` comment.

### `# boundary: neo4j-primitives`

Neo4j node property *values* can be any Neo4j primitive (use `Neo4jProperties` for the
dict, but the values inside mapper internals may still be `Any` during conversion).
The `from_neo4j_node` mapper accepts `Neo4jProperties` at its entry point, but internally
handles conversions that require type narrowing with `Any`.

```python
node_data: dict[str, Any]  # boundary: neo4j-primitives — raw record from driver.data()
```

### FastHTML boundary surfaces

FastHTML/fastcore present these surfaces, and `Any` is justified at two of them — FT element internals, and the names the local stubs leave untyped. The others have typed alternatives — `Result[Any]`, `app: Any` / `rt: Any`, a tag name as an annotation and an `Any` in an ASGI signature show up there as regressions, not boundaries.

| Surface | Typed alternative | `# boundary:` tag |
|---------|-------------------|--------------------|
| `app` / `rt` route-factory params | `FastHTMLApp` / `RouteDecorator` protocols | *none — protocol IS the boundary* |
| Route handler return | its narrowest true type: `FT`, `HtmlDocument`, `FtResponse`, a `Response` class, `Result[T]` under `boundary_handler`, or a union of them, FT first | *none — the concrete type IS the contract* |
| A tag's result, a page | `FT` (every tag function returns one); `HtmlDocument` for a full page | *none — `typings/` types them* |
| FT element internals (`*c`, `**kwargs`) | none — HTML is structurally heterogeneous | `# boundary: fasthtml-elements` |
| A FastHTML name the stubs in `typings/` do not declare | declare it in the stub when first-party code needs its type | `# boundary: fasthtml-untyped` (in `typings/` only) |
| ASGI plumbing (`scope/receive/send`) | `Scope` / `Receive` / `Send` / `ASGIApp` from `starlette.types` | *none — Starlette's types ARE the boundary* |
| The role-decorator-injected `current_user: Any = None` | none that fails closed — see below | `# boundary: injected-user` (tagged once, at the contract in `roles.py`) |

#### `# boundary: fasthtml-elements`

FastHTML HTML element factories (`Div`, `Span`, `CardBody`, etc.) accept variadic children and arbitrary HTML attributes. HTML structure is inherently dynamic; a complete TypedDict for all HTML attributes would be impractical. The tag covers those parameters only: what a factory builds is an `FT`.

```python
def CardBody(*c: Any, cls: str = "", **kwargs: Any) -> FT:
    # boundary: fasthtml-elements — html children and attrs are structurally dynamic
```

The stubs in `typings/` carry the same tag on every `Any` that stands for a child, an
attribute or a renderable tree (`FT.children`, `FT.attrs`, each tag's `*c` / `**kwargs`).

#### `# boundary: fasthtml-untyped`

The stubs in `typings/` type only the FastHTML names first-party code imports. Each stub
module ends in `def __getattr__(name: str) -> Any`, so every other name stays `Any`
explicitly rather than failing to resolve; `NotStr`'s `__getattr__` (it delegates to the
`str` it wraps) is the same kind. These carry `# boundary: fasthtml-untyped`, and the tag
lives in `typings/` only. ruff's ANN401 is waived for `typings/`, so
`tests/unit/test_fasthtml_stubs.py` is what holds every stub line naming `Any` to one of the
two tags. When first-party code starts to use an untyped name, declare it in the stub:
the same test then holds the declaration to the installed package. `FtResponse`
(`typings/fasthtml/core.pyi`) is declared for that reason: the rendered-refusal helpers
(`refuse`, `refuse_not_found`, `refuse_unavailable`) return it,
and while a name is `Any`, a union that names it is `Any` too, so mypy checks nothing a
handler declared `-> FT | FtResponse` returns.

#### `# boundary: injected-user`

A role-gated handler declares the user the decorator injects as `current_user: Any = None`.
The value is always a `User`, but `User` is not a safe annotation at that boundary: FastHTML
binds a dataclass-annotated parameter from the request body, so `current_user: User` on a
handler that *lacks* the decorator would receive a `User` built from the caller's own form
fields — a caller-chosen `uid` — while `Any = None` on the same mistake leaves `None` and the
first attribute read fails. `require_role` keeps the name out of FastHTML's binding on decorated
handlers and refuses any other spelling at decoration, so the tag lives once, at that check in
`adapters/inbound/auth/roles.py`, not on each of the handler sites (ANN401 is bought out for
`adapters/**`). See [AUTH_PATTERNS.md § Pattern 3](AUTH_PATTERNS.md).

#### `# type: ignore[arg-type]  # fasthtml dynamic-attr splat`

A fifth, narrower case — an **`arg-type` ignore**, not an `Any` annotation. MonsterUI component factories (`Button`, `Input`, `Select`, …) declare typed keyword slots (`disabled: bool`, `size: Size | None`). Splatting a dynamic attribute dict — `**{"x-on:click": expr}` — spills its `str` values onto those typed slots, so mypy reports `arg-type` ("expected bool"). Most dynamic attrs have a kwarg form and must use it: plain-hyphen (`hx_get=`, not `**{"hx-get": …}`) and HTMX event handlers (`hx_on__after_request=`, since `__`→`--` and htmx treats `hx-on--evt` as `hx-on::evt`). Only **Alpine** colon / at / dot attributes (`x-on:click`, `:class`, `@click.outside`) cannot be expressed as a FastHTML kwarg — Alpine parses on the colon and has no dash alias, so the splat is the only correct render. Tag those, and only those:

```python
Button("Close", **{"x-on:click": close_expr})  # type: ignore[arg-type]  # fasthtml dynamic-attr splat
```

**Write data values with `ui.alpine.js_literal` / `alpine_call`.** An Alpine handler attribute is JS source — a runtime value spliced into it can break out of its string literal (or inject). Use `**{"x-on:click": alpine_call("setTag", tag)}`, never `f"setTag('{tag}')"` (a tag like `it's` ends the JS string → the click throws, or the rest runs). `js_literal` emits JSON, a properly-escaped JS literal, and FastHTML's attribute escaping handles the surrounding quotes. `tests/unit/ui/test_alpine_expression_census.py` lists every other interpolated value with the reason it cannot carry a quote (an enum value, a number, JavaScript written in the code).

**A colon / `@` Alpine attr written as an underscore-kwarg renders DEAD, silently.** `x_on_click="open()"` → `x-on-click="open()"`, which Alpine never binds — no error, the click just does nothing. Always splat colon / `@` / dot attrs. Detect regressions: `grep -rn "x_on_\|x_bind_" ui/ adapters/inbound/`.

⚠️ **Historical timing note:** the `# type: ignore[arg-type]` is only valid where `arg-type` is **enabled** for the module. During the sweep, adding it on a tree where `arg-type` was still globally disabled tripped `[unused-ignore]` (`warn_unused_ignores = true`), so each per-module flip landed its ignores together with the `enable_error_code`. `arg-type` is now enforced on all first-party trees, so this is no longer a live concern. See `.claude/skills/ui-browser/SKILL.md` § Splat vs underscore-kwarg for the full convert-vs-suppress decision table (incl. the `json.dumps` rule).

#### What does NOT need a `# boundary:` tag

- **`app` / `rt` parameters in route factories.** Use the protocols from `fasthtml_types.py` — `tests/unit/adapters/test_route_param_types.py` fails on an `rt` / `app` under `adapters/inbound` (or in `scripts/dev/bootstrap.py`, which builds them) typed `Any` or left bare, and checks each protocol member against a real `fast_app()`. ASGI middleware takes `app: ASGIApp` (`starlette.types`). `rt(path)` returns `Callable[[Callable[P, R]], Callable[P, R]]`: the name a decorated handler binds calls like the handler, and the same test checks that the real `rt` passes every argument on and returns the handler's own result. A wrapper between `rt` and the handler keeps only what its own annotation keeps — `csrf_protected` hands `rt` `Callable[..., Awaitable[Any]]`. No first-party code reads the name a decorated handler binds yet, so that erasure is [deferred to its first reader](../roadmap/route-wrappers-erase-handler-types.md). A test that calls registered handlers directly takes them from `route_collector()` (`tests/helpers/route_collector.py`), the one stand-in `rt`. It records one door per method FastHTML registers, a lookup names its method (`registered[path, "GET"]`), and its return annotation is where mypy checks it against the protocol — tests run with `arg-type` off, so a stand-in handed to a route function is checked nowhere else. `tests/unit/test_route_collector.py` fails on a hand-written stand-in, on a mock bound as `rt`, and on anything else handed to a route function it can name.
- **ASGI plumbing.** `FastHTMLApp.__call__` takes `Scope` / `Receive` / `Send` (`starlette.types`) and its `router` is a `starlette.routing.Router` — httpx's `ASGITransport`, Starlette's `TestClient` and uvicorn all accept it. A test holding the bootstrapped app (`skuel_app`, or an app a fixture builds) types it `FastHTMLApp`; `tests/unit/adapters/test_route_param_types.py` fails on one that does not, and on a boundary tag excusing an `Any` here anywhere in the repo.
- **Route handler returns rendering HTML.** `FT` is a real type to mypy and Pyright. FastHTML ships no types, so the local stubs in `typings/` (mypy's `mypy_path`, Pyright's `stubPath`) declare `fastcore.xml.FT` and every tag function as returning one: `Div()` is an `FT`, and a tag function is never an annotation (`-> Div` is a mypy `valid-type` error; write `-> FT`). A full page is `HtmlDocument` (`ui/layouts/base_page.py`): `Html()`, and so `BasePage`, `SidebarPage` and every section's page wrapper, returns the doctype tag and the `html` element as a pair, never one `FT`. `Result[FT]` is correct; `Result[Any]` with `# boundary: fasthtml FT component` is obsolete framing. Every route handler declares the narrowest type it returns, FT first in a union: `FT` (a fragment), `HtmlDocument` (a page), `tuple[FT, ...]` (fragments swapped together), `FtResponse` (a rendered refusal with its status), a `Response` class, or `Result[T]` under `boundary_handler` — `-> FT | Response`, `-> HtmlDocument | FtResponse`. Every name in the annotation is imported at runtime: FastHTML evaluates a handler's annotations when it registers the route, so a name bound only under `TYPE_CHECKING` is a `NameError` at boot. `tests/unit/adapters/test_route_handler_returns.py` reads, for every route the application registers (the route catalog's real-app wiring), the signature FastHTML holds, and fails on a handler that declares no return type, returns `Any` (alone or in a union) or returns `Result[Any]`; the same wiring raises the boot's `NameError`. Never `-> Response` alone on a handler that can return FT — FastHTML takes a `Response` class as the return annotation to mean "build this class from the return value", so `Response(ft)` fails with a 500. mypy refuses it (`return-value`: got `FT`, expected `Response`). `tests/unit/test_fasthtml_stubs.py` holds the stubs to the installed FastHTML: every tag declared, every declaration true of the runtime.
- **Route handlers that delegate to a typed service.** `events_service.update_event(...)` returns `Result[Event]` — the route wrapper should too. Using `Result[Any]` here is Category A (lazy), not Category C.

### `# boundary: error-metadata`

`ErrorContext.details: dict[str, Any]` — Error diagnostic metadata is intrinsically
heterogeneous. A `ValidationError` carries field names and values; a `DatabaseError` carries
query fragments and retries; an `IntegrationError` carries HTTP status codes. A single
TypedDict cannot cover all cases without being a large union, defeating the purpose.

```python
details: dict[str, Any]  # boundary: error-metadata — error context is heterogeneous
```

### `# boundary: placeholder`

Functions with `_underscored` parameters that are explicitly marked as placeholders for
future implementation. These use `Any` intentionally until the real shape is defined.

```python
# shape to write, e.g. for _knowledge_units on _analyze_blocked_knowledge_prerequisites
# (core/services/askesis/context_retriever.py:966)
_knowledge_units: list[Any]  # boundary: placeholder — prerequisite analysis not yet implemented
```

Every such placeholder is registered in `docs/reference/PLACEHOLDER_INDEX.md`.

---

## Quick Reference

| Situation | Old | Correct |
|-----------|-----|---------|
| Logger field | `logger: Any` | `logger: logging.Logger` |
| Neo4j driver | `driver: Any` | `driver: AsyncDriver` |
| Metrics | `prometheus_metrics: Any` | `prometheus_metrics: PrometheusMetrics \| None` |
| Services container | `services: Any` | `services: Services \| None` |
| FastHTML `rt` | `rt: Any` | `rt: RouteDecorator` (from `fasthtml_types`) |
| FastHTML `app` | `app: Any` | `app: FastHTMLApp` (from `fasthtml_types`) |
| Neo4j node dict | `dict[str, Any]` | `Neo4jProperties` |
| Search filters | `dict[str, Any]` | `FilterParams` |
| Relationship props | `Metadata` | `RelationshipMetadata` |
| Generic callable | `Callable[[Any], bool]` | `EntityFilter[T]` |
| Protocol return (model) | `Result[Any]` | `Result[Task]`, `Result[Askesis]`, etc. |
| Protocol return (dict) | `Result[dict[str, Any]]` | TypedDict from `query_types.py` |
| Route handler returning fragment | `Result[Any]` (with `# boundary:`) | `Result[FT]` (import from `fasthtml.common`) |
| Route handler delegating to service | `Result[Any]` | `Result[Event]` / `Result[Task]` / etc. — match the facade |
| HTML children | `*c: Any` | *keep — Category C boundary* |
| Error details | `dict[str, Any]` | *keep — Category C boundary* |

---

## Enforcement

**Ruff enforces this policy in signatures via ANN401, and `core/ports/` is enforced today.**

- ANN401 (`Any` in a parameter, return, `*args` or `**kwargs` annotation) is selected
  globally through the `"ANN"` entry in `[tool.ruff.lint] select`. It is **not** in the
  global `ignore` list. Every tree that still carries debt buys out through an explicit,
  counted entry in the ANN401 debt ledger at the top of
  `[tool.ruff.lint.per-file-ignores]` (`pyproject.toml`).
- `core/ports/` has **no** exemption entry, so an `Any` in a protocol signature fails CI.
  That is where enforcement started deliberately: an `Any` in the protocol layer
  propagates to every implementer. Trees that are already clean (`core/ingestion/`,
  `core/prompts/`, `core/constants.py`, `main.py`) likewise have no entry and are
  therefore enforced too.
- **The ledger is debt, not policy. Drive an entry's count to 0 and delete the entry** —
  the same shape as the SKUEL023 facade allowlist, driven to empty twice and then
  deleted (#828, #838).
- **ANN401 sees only top-level `Any` in a signature.** A nested `dict[str, Any]`,
  `list[Any]` or `Result[Any]` is invisible to it (measured). The ledger counts are a
  floor on the real `Any` debt, and Category B/C judgement below is still human work.
- **One `Any` is enforced ahead of the ledger: `self.backend` in `core/`.** SKUEL023
  flags it whatever the tree's ANN401 entry allows, and the forward-ref form
  (`backend: "Any | None"`) too, which ANN401 does not see at all. The reason it is
  singled out: the backend handle is the seam every service call crosses, so an `Any`
  there silently unchecks a whole class rather than one argument.
- Code reviewers should challenge any new `Any` that is not in a `# boundary:` comment.
- When refactoring, replace `Any` with the most specific type from this policy.
- If a new boundary is genuinely needed, add it to this document with an explanation.

### Before proposing a new lint rule: run the ones you already have, scoped

This section previously read *"the ruff linter does not currently flag `Any` usage (too
broad to auto-enforce)"*. Both halves were wrong: ANN401 existed, was already selected,
and was killed by a single line in `ignore` — and "too broad" was never a property of the
rule, only of the scope it was run at. That sentence is what let a duplicate `Any`-on-
handles lint rule get proposed before anyone re-read the config.

Both linters are **directory-scopeable without touching committed config**, so measure
before concluding a rule cannot be enforced:

```bash
uv run ruff check --select ANN401 core/ports          # any rule, any subtree
```

**`--select` enables a rule; it does not override `per-file-ignores`.** Once a tree is
bought out in the ANN401 ledger, the command above applies that exemption and reports
`0` — the one answer you must not take at face value. Clear the table to see the debt:

```bash
# recount one ledger entry (this is how the counts in pyproject.toml were derived)
uv run ruff check --select ANN401 --config 'lint.per-file-ignores = {}' core/services

# bucket the whole tree by directory
uv run ruff check --select ANN401 --config 'lint.per-file-ignores = {}' \
    --output-format json .
```

Clearing the table also drops the blanket `ANN` exemption on `tests/`, `ui/`,
`examples/` and `templates/`, so a tree-wide run reports more than the ledger's total.

MyPy has the same escape hatch — a per-module `[[tool.mypy.overrides]]` block with
`disallow_any_explicit = true` scopes its strictest `Any` check (`[explicit-any]`) to a
single package, verified against a two-package probe.
