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
- `EntryReportOperations.generate_report()` — Were `entry: Any`, `exercise: Any`, now `Submission`, `Exercise`
- `TeacherReviewService.__init__()` — Was `ku_interaction_service: Any`, now `LessonMasteryService`
- `ReviewQueueOperations.request_review()` — Was `Result[dict[str, Any]]`, now `Result[ReviewRequestResult]`
- `ReviewQueueOperations.get_pending_reviews()` — Was `Result[list[dict[str, Any]]]`, now `Result[list[PendingReviewItem]]`
- `TeacherReviewOperations.get_group_detail()` — Was `Result[list[dict[str, Any]]]`, now `Result[list[GroupMemberProgress]]`
- `PsBackend.get_step_with_knowledge()` / `delete_step_node()` / `get_standalone_steps()` — Were `Result[list[dict[str, Any]]]`, now `Result[list[PsStepWithKnowledgeRow]]` / `Result[list[PsDeleteStepRow]]` / `Result[list[PsStandaloneStepRow]]` (typed-row TypedDicts in `query_types.py`)
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
- Cross-domain context returns → `GraphContextResult`

**Phase 4 — Return types:** ~170 protocol methods migrated from `Result[Any]` to specific types (0 `Result[Any]` remain in protocols, 2 intentional: `base_service_interface.py` and `OwnershipVerifier.verify_ownership` in `service_protocols.py` — the latter is a narrow internal callback protocol used by `LateralRelationshipService` and `LateralRelationshipsOrchestrator` to accept any domain facade's `verify_ownership(uid, user_uid) -> Result[T]`; `Result[T]` is invariant, each facade returns a different concrete `T`, and callers only branch on `.is_error`):

- **Domain model returns:** `Result[SubmissionEntity]`, `Result[EntryReport]`, `Result[Askesis]`,
  `Result[CalendarData]`, `Result[Group]`, `Result[UserEntry]`, `Result[Exercise]`,
  `Result[FormTemplate]`, `Result[FormSubmission]`, `Result[ReportSchedule]`, `Result[ActivityReport]`
- **110 output TypedDicts** in `query_types.py` for structured dict returns:

| TypedDict | Protocol / Field | Methods |
|-----------|-----------------|---------|
| `SignUpResult`, `SignInResult` | `GraphAuthOperations` | `sign_up`, `sign_in` |
| `ReviewQueueItem`, `SubmissionDetailResult`, `TeacherDashboardStats`, `GroupMemberProgress` | `TeacherReviewOperations` | `get_review_queue`, `get_submission_detail`, `get_dashboard_stats`, `get_group_detail` |
| `ReviewRequestResult`, `PendingReviewItem` | `ReviewQueueOperations` | `request_review`, `get_pending_reviews` |
| `KnowledgeSuggestionsResult`, `KnowledgeGenerationResult`, `LearningOpportunitiesResult` | `KnowledgeIntelligenceOperations` | `get_knowledge_suggestions`, `generate_knowledge_from_entities`, `get_learning_opportunities` |
| `KnowledgePrerequisitesResult`, `KnowledgePrerequisiteItem` | `KnowledgeIntelligenceOperations` | `get_knowledge_prerequisites` |
| `BehavioralInsightsResult`, `PerformanceAnalyticsResult` | `DomainIntelligenceOperations` | `get_behavioral_insights`, `get_performance_analytics` |
| `CrossDomainOpportunitiesResult`, `CrossDomainConnectionItem`, `AIInsightsResult` | `DomainIntelligenceOperations` | `get_cross_domain_opportunities`, `get_ai_insights` |
| `LifePathStatus`, `LifePathRecommendation`, `LifePathDesignation`, `LifePathAlignmentResult` | `LifePathOperations`, `LifePathAlignmentOperations` | `get_full_status`, `capture_and_recommend`, `designate_and_calculate`, `get_alignment`, `calculate_alignment` |
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

FastHTML/fastcore present four distinct surfaces, and `Any` is justified at only two of them. The other two have typed alternatives — `Result[Any]` and `app: Any` / `rt: Any` show up there as regressions, not boundaries.

| Surface | Typed alternative | `# boundary:` tag |
|---------|-------------------|--------------------|
| `app` / `rt` route-factory params | `FastHTMLApp` / `RouteDecorator` protocols | *none — protocol IS the boundary* |
| Route handler return | `Result[FT]` for HTML fragments; `Result[Goal]` etc. for models | *none — the concrete type IS the contract* |
| FT element internals (`*c`, `**kwargs`) | none — HTML is structurally heterogeneous | `# boundary: fasthtml-elements` |
| ASGI plumbing (`scope/receive/send`) | none — Starlette doesn't export usable types | `# boundary: fasthtml-app` |

#### `# boundary: fasthtml-elements`

FastHTML HTML element factories (`Div`, `Span`, `CardBody`, etc.) accept variadic children and arbitrary HTML attributes. HTML structure is inherently dynamic; a complete TypedDict for all HTML attributes would be impractical.

```python
def CardBody(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    # boundary: fasthtml-elements — html children and attrs are structurally dynamic
```

#### `# boundary: fasthtml-app`

The `FastHTMLApp` protocol in `adapters/inbound/fasthtml_types.py` captures the minimal interface SKUEL calls. The `Any` in its `__call__(scope, receive, send)` signature is the ASGI boundary — Starlette doesn't expose usable types for those three parameters.

#### `# type: ignore[arg-type]  # fasthtml dynamic-attr splat`

A fifth, narrower case — an **`arg-type` ignore**, not an `Any` annotation. MonsterUI component factories (`Button`, `Input`, `Select`, …) declare typed keyword slots (`disabled: bool`, `size: Size | None`). Splatting a dynamic attribute dict — `**{"x-on:click": expr}` — spills its `str` values onto those typed slots, so mypy reports `arg-type` ("expected bool"). Most dynamic attrs have a kwarg form and must use it: plain-hyphen (`hx_get=`, not `**{"hx-get": …}`) and HTMX event handlers (`hx_on__after_request=`, since `__`→`--` and htmx treats `hx-on--evt` as `hx-on::evt`). Only **Alpine** colon / at / dot attributes (`x-on:click`, `:class`, `@click.outside`) cannot be expressed as a FastHTML kwarg — Alpine parses on the colon and has no dash alias, so the splat is the only correct render. Tag those, and only those:

```python
Button("Close", **{"x-on:click": close_expr})  # type: ignore[arg-type]  # fasthtml dynamic-attr splat
```

**Escape DYNAMIC values with `json.dumps()`.** An Alpine handler attribute is JS source — a runtime value spliced into it can break out of its string literal (or inject). Use `**{"x-on:click": f"setTag({json.dumps(tag)})"}`, never `f"setTag('{tag}')"` (a tag like `it's` ends the JS string → the click throws). `json.dumps` emits a properly-escaped JS string literal, and FastHTML's attribute escaping handles the surrounding quotes. Static literals you control (e.g. a hardcoded `'all'`/`'overdue'` preset) are exempt.

**A colon / `@` Alpine attr written as an underscore-kwarg renders DEAD, silently.** `x_on_click="open()"` → `x-on-click="open()"`, which Alpine never binds — no error, the click just does nothing. Always splat colon / `@` / dot attrs. Detect regressions: `grep -rn "x_on_\|x_bind_" ui/ adapters/inbound/`.

⚠️ **Historical timing note:** the `# type: ignore[arg-type]` is only valid where `arg-type` is **enabled** for the module. During the sweep, adding it on a tree where `arg-type` was still globally disabled tripped `[unused-ignore]` (`warn_unused_ignores = true`), so each per-module flip landed its ignores together with the `enable_error_code`. `arg-type` is now enforced on all first-party trees, so this is no longer a live concern. See `.claude/skills/ui-browser/SKILL.md` § Splat vs underscore-kwarg for the full convert-vs-suppress decision table (incl. the `json.dumps` rule).

#### What does NOT need a `# boundary:` tag

- **`app` / `rt` parameters in route factories.** Use the protocols from `fasthtml_types.py`. Lifting `app: Any` to `app: FastHTMLApp` is migration work, not a boundary.
- **Route handler returns rendering HTML.** `from fasthtml.common import FT` gives a real class (`fastcore.xml.FT`) that type-checks. `Result[FT]` is correct; `Result[Any]` with `# boundary: fasthtml FT component` is now obsolete framing.
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
