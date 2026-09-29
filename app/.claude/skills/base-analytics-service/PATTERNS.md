# BaseAnalyticsService Implementation Patterns

Each pattern below is taken from a live service. Read the named file for the whole method.

---

## Pattern 1: A User-Scoped Analytics Method

`HabitsIntelligenceService.get_performance_analytics`
(`core/services/habits/habits_intelligence_service.py`): one backend read, then arithmetic.

```python
async def get_performance_analytics(
    self, user_uid: UserUID, _period_days: int = 30
) -> Result[dict[str, Any]]:  # boundary: per-domain analytics payload
    habits_result = await self.backend.find_by(user_uid=user_uid)
    if habits_result.is_error:
        return Result.fail(habits_result)

    habits = habits_result.value or []
    total_habits = len(habits)
    active_habits = [h for h in habits if h.is_active]

    avg_consistency = sum(h.success_rate for h in habits) / total_habits if total_habits else 0.0
    habits_with_streak = [h for h in habits if h.current_streak > 0]
    at_risk_habits = [h for h in active_habits if h.success_rate < 0.5]

    return Result.ok(
        {
            "user_uid": user_uid,
            "period_days": _period_days,
            "total_habits": total_habits,
            "active_habits": len(active_habits),
            "habits_with_streak": len(habits_with_streak),
            "at_risk_habits": len(at_risk_habits),
            "avg_consistency": round(avg_consistency, 2),
        }
    )
```

What to take from it:

- The read is `self.backend.find_by(user_uid=...)` — a method the backend protocol declares.
  Do not invent a backend method in the service; add it to the protocol and the backend.
- `find_by` defaults to `limit=100`, and this call passes none: `total_habits` is at most 100.
  Pass the limit a new method needs — `limit=QueryLimit.MAXIMUM` (`core/constants.py`) where the
  metric is a count over everything the user has.
- A failed read is propagated, not turned into zeros.
- Guard every division: an empty list is a normal input.
- `_period_days` is accepted and not applied. The payload echoes it, which does not mean the
  numbers are windowed. A new method that takes a period applies it.

---

## Pattern 2: The Typed-Context Template

`get_goal_progress_dashboard` (`core/services/goals/_analytics_mixin.py`) runs the base template,
then shapes the envelope for its caller.

```python
async def get_goal_progress_dashboard(
    self, uid: str, min_confidence: float = 0.7
) -> Result[dict[str, Any]]:  # boundary: dashboard payload
    analysis_result = await self._analyze_entity_with_typed_context(
        uid,
        metrics_fn=calculate_goal_progress_metrics,
        recommendations_fn=goal_recommendations,
        min_confidence=min_confidence,
    )
    if analysis_result.is_error:
        return analysis_result

    analysis = analysis_result.value
    goal = self._to_domain_model(analysis["entity"], GoalDTO, Goal)
    context: GoalCrossContext = analysis["context"]
    metrics = analysis["metrics"]

    supporting_tasks = [{"uid": t.uid} for t in context.tasks]
    supporting_habits = [{"uid": h.uid} for h in context.habits]
    ...
```

The metrics function reads the path-aware context — typed entity lists, each entry carrying
`distance` and `path_strength`:

```python
def calculate_goal_progress_metrics(
    goal: Any,  # boundary: generic across the six metrics functions
    context: PathAwareGoalCrossContext,
) -> dict[str, Any]: ...  # boundary: metrics map


def goal_recommendations(
    goal: Any,  # boundary: generic across the six recommendation functions
    context: PathAwareGoalCrossContext,
    metrics: dict[str, Any],  # boundary: metrics map
) -> list[str]: ...
```

Both are in `core/services/intelligence/metrics_calculators.py`:

| Domain | `metrics_fn` | `recommendations_fn` |
|--------|--------------|----------------------|
| Tasks | `calculate_task_cross_domain_metrics` | `task_recommendations` |
| Goals | `calculate_goal_progress_metrics` | `goal_recommendations`, `goal_learning_recommendations` |
| Habits | `calculate_habit_integration_metrics` | `habit_recommendations` |
| Events | `calculate_event_performance_metrics` | — |
| Principles | `calculate_principle_alignment_metrics` | `principle_recommendations` |
| Choices | `calculate_decision_metrics` | `decision_improvement_opportunities` |

The Choices pair is in the same module but is not re-exported by the package — import it from
`core.services.intelligence.metrics_calculators`. Events passes no `recommendations_fn`: its
analysis surfaces no recommendations list.

A metrics function is pure: no I/O, no `await`. Put a new lens there, not inline in the
service.

---

## Pattern 3: Recommendations with `RecommendationEngine`

From `core/services/events/_analytics_mixin.py`:

```python
return (
    RecommendationEngine()
    .with_metrics(
        {
            "total_events": total_events,
            "low_impact_ratio": low_impact_ratio,
            "high_impact_ratio": high_impact_ratio,
        }
    )
    .add_conditional(
        low_impact_ratio > 0.3,
        f"Consider linking {low_impact_count} low-impact events to goals or habits",
    )
    .add_threshold_check(
        "total_events",
        threshold=5,
        message="Schedule more events to maintain consistent progress",
        comparison="lt",
    )
    .build()
)
```

| Method | Adds the message when |
|--------|-----------------------|
| `with_metrics(metrics)` | — sets the numeric values `add_threshold_check` reads |
| `add_threshold_check(metric_name, threshold, message, comparison="lt")` | the metric compares true; `comparison` is `lt`, `gt`, `le` or `ge` |
| `add_conditional(condition, message)` | `condition` is true |
| `add_message(message)` | always |
| `build()` | — returns `list[str]` |

A metric name missing from `with_metrics` reads as `0.0`, so an `lt` check on a misspelled name
always fires.

---

## Pattern 4: Trend Classification

```python
from core.services.intelligence import Trend, analyze_completion_trend

trend = analyze_completion_trend(completed_count=80, total_count=100)
# {"trend": "excellent", "completion_rate": 80.0, "analyzed_count": 100}
```

`analyze_completion_trend(completed_count, total_count, thresholds=None)` takes **counts** and
returns a dict. With `total_count == 0` the trend is `Trend.INSUFFICIENT_DATA`. The default
thresholds are 80 / 60 / 40 percent.

`Trend` members: `IMPROVING`, `STABLE`, `DECLINING`, `EXCELLENT`, `NEEDS_ATTENTION`,
`INSUFFICIENT_DATA`.

---

## Pattern 5: A Dual-Track System Calculator

The template calls `system_calculator(entity, user_uid)` and expects
`(level, score, evidence)`. From `core/services/principles/_alignment_intelligence_mixin.py`:

```python
async def _calculate_system_alignment_for_dual_track(
    self, principle: Principle, _user_uid: UserUID
) -> tuple[AlignmentLevel, float, list[str]]:
    evidence: list[str] = []
    total_score = 0.0
    ...
    return AlignmentLevel.from_score(score), score, evidence


@staticmethod
def _alignment_level_to_score(level: AlignmentLevel) -> float:
    return level.to_score()
```

- Convert between level and score with the enum's own `to_score()` / `from_score()`.
- For a user-level dimension (`require_entity=False`), `entity` is `None` — the calculator
  works from `user_uid`.
- `evidence` strings reach the user in the gap card; write them as findings ("3 goals guided by
  this principle").
- An exception raised by the calculator becomes `Result.fail(Errors.system(...))` in the
  template. Return a low score for "no evidence"; raise only for a real failure.

---

## Pattern 6: A Decomposed Service

When a service passes roughly 350 lines, its methods move into mixin files in the same package
and the service file keeps `__init__` and the protocol methods.

```python
class TasksIntelligenceService(
    _CoreIntelligenceMixin,
    _AnalyticsMixin,
    _ProductivityMixin,
    _DualTrackMixin,
    BaseAnalyticsService["TasksOperations", Task],
):
    _service_name = "tasks.intelligence"
```

A mixin in this shape:

- declares the attributes it reads as annotations (`backend: TasksOperations`,
  `relationships: UnifiedRelationshipService[Any, Any, Any] | None  # boundary: domain-generic
  params`) so mypy can check its body;
- defines no `__init__`;
- is listed before `BaseAnalyticsService` in the bases.

Line counts are advisory; coherence decides. See
[SERVICE_DECOMPOSITION_RULE.md](/docs/patterns/SERVICE_DECOMPOSITION_RULE.md).

---

## Anti-Patterns

### Inventing a backend method

```python
# WRONG - no protocol declares get_user_habits; mypy rejects it against HabitsOperations
habits = await self.backend.get_user_habits(user_uid)

# CORRECT
habits_result = await self.backend.find_by(user_uid=user_uid, limit=QueryLimit.MAXIMUM)
```

### Passing a relationship type to `get_related_uids`

```python
# WRONG - the first argument is a config method key, and there is no direction parameter
await self.relationships.get_related_uids(uid, "REINFORCES_KNOWLEDGE", direction="outgoing")

# CORRECT
await self.relationships.get_related_uids("knowledge", habit_uid)
```

The keys are declared in `core/models/relationship_registry.py`; read the domain's entry before choosing one.

### Swallowing a failed read

```python
# WRONG - a failed read is reported as "ready"
prereqs = await self.relationships.get_related_uids("prerequisite_habits", habit.uid)
if prereqs.is_error:
    return Result.ok(True)

# CORRECT
if prereqs.is_error:
    return Result.fail(prereqs)
```

### Cypher in the service

A query string in `core/` fails SKUEL021, and one in a docstring fails SKUEL033. State what the
method means; the query is a backend method.

### An unannotated broad `except`

```python
# WRONG
except Exception as e:
    return Result.fail(Errors.system(message=str(e)))

# CORRECT - a narrow type from core/utils/exception_types.py
except DATA_CONVERSION_EXCEPTIONS as e:
    return Result.fail(Errors.system(message="Malformed analytics row", exception=e))
```

The template's two broad catches wrap caller-supplied callables and carry a `# safety-net:`
annotation (SKUEL017).
