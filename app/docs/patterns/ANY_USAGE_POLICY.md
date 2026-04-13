# Any Usage Policy

*Last updated: 2026-04-11*

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
- `SubmissionOperations.submit_file()` params — Were `entity_type: Any`, `processor_type: Any`, now `EntityType`, `ProcessorType`
- `SubmissionOperations.list_submissions()` params — Were `entity_type: Any`, `status: Any`, now `EntityType`, `EntityStatus`
- `SubmissionOperations.set_visibility()` — Was `visibility: Any`, now `Visibility`
- `ExerciseReportOperations.generate_report()` — Were `entry: Any`, `exercise: Any`, now `Submission`, `Exercise`
- `TeacherReviewService.__init__()` — Was `ku_interaction_service: Any`, now `LessonMasteryService`
- `ReviewQueueOperations.request_review()` — Was `Result[dict[str, Any]]`, now `Result[ReviewRequestResult]`
- `ReviewQueueOperations.get_pending_reviews()` — Was `Result[list[dict[str, Any]]]`, now `Result[list[PendingReviewItem]]`
- `TeacherReviewOperations.get_group_detail()` — Was `Result[list[dict[str, Any]]]`, now `Result[list[GroupMemberProgress]]`
- `PsBackend.get_step_with_knowledge()` / `get_step_with_context()` / `delete_step_node()` / `get_standalone_steps()` — Were `Result[list[dict[str, Any]]]`, now `Result[list[PsStepWithKnowledgeRow]]` / `Result[list[PsStepWithContextRow]]` / `Result[list[PsDeleteStepRow]]` / `Result[list[PsStandaloneStepRow]]` (11 new TypedDicts added to `query_types.py`)
- `FormTemplateBackend.get_forms_for_path_step()` / `FormTemplateService.get_for_path_step()` — Were `Result[list[dict[str, Any]]]`, now `Result[list[Neo4jProperties]]` (reuses existing alias)

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

- **Domain model returns:** `Result[SubmissionEntity]`, `Result[ExerciseReport]`, `Result[Askesis]`,
  `Result[CalendarData]`, `Result[Group]`, `Result[JeInput]`, `Result[JeOutput]`, `Result[Exercise]`,
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
| `RichEntityItem`, `RichKnowledgeUnitItem`, `RichLearningPathItem`, `RichPathStepItem`, `RichMOCItem` | `UserContext` fields | `entities_rich`, `knowledge_units_rich`, `enrolled_paths_rich`, `active_path_steps_rich`, `active_mocs_rich` |
| `UnsubmittedExerciseItem`, `PendingRevisedExerciseItem`, `FacetInteractionItem` | `UserContext` fields | `unsubmitted_exercises`, `pending_revised_exercises`, `facet_interaction_history` |
| `CrossDomainInsightsData`, `CrossDomainInsightItem` | `UserContext` field | `cross_domain_insights` |
| `NextActionResult`, `AtRiskHabitsResult`, `AdaptiveLearningPathResult`, `FutureContextStateResult`, `ContextHealthResult` | `ContextAwareOperations` | `get_next_action`, `get_at_risk_habits`, `get_adaptive_learning_path`, `predict_future_context_state`, `get_context_health` |
| `GraphInfluenceItem`, `RelationshipSummaryResult` | `GraphEntity` | `get_upstream_influences`, `get_downstream_impacts`, `get_relationship_summary` |
| `SubstantiationSummaryResult`, `PsKnowledgeSummaryResult`, `PsPracticeSummaryResult`, `UserProgressResult` | `CurriculumOperations`, `PsOperations` | `get_substantiation_summary`, `get_knowledge_summary`, `get_practice_summary`, `get_user_progress` |

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

### `# boundary: fasthtml-elements`

FastHTML HTML element factories (`Div`, `Span`, `CardBody`, etc.) accept variadic children
and arbitrary HTML attributes. HTML structure is inherently dynamic; a complete TypedDict
for all HTML attributes would be impractical.

```python
def CardBody(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    # boundary: fasthtml-elements — html children and attrs are structurally dynamic
```

### `# boundary: fasthtml-app`

The FastHTML `app` object's type hierarchy is not exported by the library. The `FastHTMLApp`
protocol in `adapters/inbound/fasthtml_types.py` captures the minimal interface SKUEL uses.
The `Any` in its `__call__` signature (ASGI scope/receive/send) is a framework boundary.

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
future implementation. These use `Any` intentionally until the service type is defined.

```python
_tasks_service: Any = None  # boundary: placeholder — TasksService not yet threaded here
```

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
| HTML children | `*c: Any` | *keep — Category C boundary* |
| Error details | `dict[str, Any]` | *keep — Category C boundary* |

---

## Enforcement

- The ruff linter does not currently flag `Any` usage (too broad to auto-enforce).
- Code reviewers should challenge any new `Any` that is not in a `# boundary:` comment.
- When refactoring, replace `Any` with the most specific type from this policy.
- If a new boundary is genuinely needed, add it to this document with an explanation.
