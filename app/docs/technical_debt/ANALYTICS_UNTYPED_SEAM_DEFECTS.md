---
title: Analytics Untyped-Seam Defects
updated: 2026-08-12
status: resolved
category: technical-debt
tags: [analytics, error-handling, result, technical-debt, types]
related: [RETURN_VALUE_ERRORS_ANALYSIS.md, ERROR_HANDLING.md]
---

# Analytics Untyped-Seam Defects

**Status**: ✅ RESOLVED (2026-08-12)
**Defect count**: 8 (1 reported, 5 found by fixing it, 2 more by Codex on #1032)
**Surfaces affected**: every cross-layer analytics report; three single-domain reports
**Guard**: `tests/unit/test_weekly_life_summary_composition.py`

## Overview

Fixing one reported bug in `AnalyticsAggregationService.aggregate_weekly_life_summary`
uncovered five more in the same call chain. All six are the same defect: **code
reading a name or a type that its input does not carry**, on a path where nothing
checked and nothing failed loudly.

Every one of them was route-reachable. Together they meant that
`/api/analytics/weekly-life-summary`, `/api/analytics/monthly-life-review`,
`/api/analytics/quarterly-progress`, `/api/analytics/yearly-review`,
`/api/analytics/cross-domain-patterns` and `/ui/analytics/weekly-life-summary`
could not return a result for any user, and that `/ui/analytics/view` failed on the
Tasks, Events and Principles domains for any user holding the entity in question.

This file records why a class this large stayed invisible, because that is the part
that generalises.

## Why it survived

### 1. `@with_error_handling` makes a coding defect look like a runtime failure

`core/utils/decorators.py` catches `except Exception` and routes it through
`_categorize_exception`, so an `AttributeError` from reading a field that does not
exist returns the *same* `Result.fail(Errors.system(...))` that a genuine outage
returns. The route boundary then renders "Error generating analytics: …". Nothing
distinguishes "the database is down" from "this line has never worked".

The exception is logged (`self.logger.error(f"Failed to {operation}: {e}")`, and
only when the receiver satisfies `HasLogger`), so the evidence existed — but the
surfaced Result carried none of it, and a report that fails always looks the same as
one that fails sometimes.

**Implication**: `@with_error_handling` on a method is not evidence the method
works. On any decorated method, "returns `Result.fail`" is compatible with "raises
on every call".

### 2. Defects queue behind each other

`aggregate_weekly_life_summary` raised at its first line of analysis, so on that
path the other five defects were unreachable — three of them had a second caller
and were failing there independently, but nothing on the cross-layer path could
reach them. Each fix moved the failure one step further down the same method. A fix
verified only by "the reported traceback is gone" would have shipped five times over
— the traceback *did* change each time.

**Implication**: when unblocking a method that has never completed, the exit
condition is "the method returns", not "the reported error is gone".

### 3. Nothing asserted on the output

No test called `aggregate_weekly_life_summary`. The shape made one hard to write
honestly: a test that mocked `calculate_*_metrics` to return plain dicts would pass
against the bug, because the bug lives exactly at the seam between the metrics
service and the aggregator.

## The six defects

| # | Site | Symptom | Precondition |
|---|------|---------|--------------|
| 1 | `analytics_aggregation_service.py` — 9 + 6 call sites | `TypeError: argument of type 'Result' is not a container or iterable` | any call |
| 2 | `aggregate_monthly_life_review` / `_quarterly_progress` / `_yearly_review` — 5 sites | `KeyError: 'domains'` | any call |
| 3 | `_generate_knowledge_activity_insight` | `TypeError: '<' not supported between instances of 'dict' and 'dict'`; and a percentage that could exceed 100 | any call |
| 4 | `calculate_principle_metrics` | `TypeError: unsupported operand type(s) for +: 'int' and 'PrincipleStrength'` | user holds ≥1 principle |
| 5 | `calculate_event_metrics` | `TypeError: '>' not supported between instances of 'datetime.time' and 'datetime.datetime'` | user holds ≥1 event |
| 6 | `calculate_task_metrics` | `AttributeError: 'Task' object has no attribute 'completed_at'` | user holds ≥1 completed task |
| 7 | `_correlate_knowledge_activities` | names a `top_substance_driver` on a week with no activity | zero activity |
| 8 | `calculate_event_metrics` | a completed future event counts in both `upcoming` and `completed` | future-dated COMPLETED event |

Defects 7–8 were found by Codex on #1032 **after** the first six were fixed — see
[Two the fix itself introduced](#two-the-fix-itself-introduced).

Defects 1–3 are in `AnalyticsAggregationService` and were reachable only through the
cross-layer reports. Defects 4–6 are in `AnalyticsMetricsService` and have a second,
independent caller — `AnalyticsService._calculate_metrics`, the single-domain report
path behind `/ui/analytics/view` — so they were breaking that surface on their own,
not merely hiding behind defect 1.

### 1. `Result[dict]` placed where `dict` was expected

Every `calculate_*_metrics` returns `Result[dict[str, Any]]`. Eight of the nine
results were stored straight into `layer1_domains` and into the returned summary;
only `curriculum_metrics` was unwrapped. The analysis helpers below index and
`.get()` their arguments, and `Result` supports neither — so
`if "total_count" in domains["tasks"]` raised on the first membership test.
`detect_cross_domain_patterns` carried the identical defect.

The type annotations said `dict[str, dict]` and `dict[str, Any]` at every one of
those parameters. They were not wrong — they were simply not checked, because
`AnalyticsAggregationService.__init__` types `metrics_service: Any`, which erases
the return type of every call made through it.

**Fixed by**: one `_layer_metrics(name, result)` helper at the top of the module,
built from the existing `Result.log_if_error(...).or_else({})`. A failed layer still
degrades to `{}` per the file's fail-soft header, but now logs on the way through —
an empty layer and a genuinely quiet week are indistinguishable downstream.

### 2. Readers of a key the writer never wrote

The monthly, quarterly and yearly reviews all reach into the weekly summary's
Layer-1 dict as `weekly_data["domains"]`. The weekly summary returns
`layer_1_activities` and never has. `layer_1_activities` is the documented shape
(`adapters/inbound/analytics_summary_api.py`) and the key the UI renderer reads, so
the five readers moved, not the writer.

### 3. A sort key and a unit that did not match their data

`sorted(substance_drivers.items(), key=operator.itemgetter(1))` sorted on the
*value*, which is a dict — unorderable. Separately, the loop rendered
`contribution_estimate * 100` as a percentage; that value is `activity_count ×
weight`, unbounded, so 20 active habits would have printed "Habits: 200%".

Fixed by sorting with the existing `get_contribution_estimate` and rendering each
driver's share of the total, which is a real percentage and sums to 100.

### 4. Summing an enum

`getattr(p, "strength", 0.5)` never reached its default: `strength` is a
`PrincipleStrength` (or `None`), so the attribute exists and `sum()` got enum
members. Fixed with the enum's own `rank()` — documented "for aggregate stats" —
over `CORE.rank()`, which puts `avg_strength` on the 0–1 scale that
`alignment_score`'s `* 100` and its `< 70` reader in `_identify_growth_opportunities`
already assume. `from_value` maps a missing or unknown strength to `MODERATE`, and
absorbs the raw strings Neo4j deserialization can produce.

### 5. Comparing a `time` to a `datetime`

`e.start_time > datetime.now()` — `Event.start_time` is a `datetime.time`. The model
already carries `start_datetime()`, which combines `event_date` and `start_time` and
returns `None` when either is absent. The same loop divided `duration_minutes`,
also optional, without a guard.

### 6. Reading a field name no model has

`task.completed_at` — the field is `completion_date`, and it is a `date` against a
`datetime` `created_at`, so the subtraction needed `.date()` as well. This is the
same shape as the `days_until_review` defect fixed in `calculate_knowledge_metrics`
earlier on this branch (`244ea55a3`): **a plausible field name, never spelled by any
model, reached only on a branch nothing exercised.**

## Two the fix itself introduced

Both were raised by Codex on #1032, after the six above were fixed. Neither existed
as observable behaviour before — the reports raised and rendered nothing — so both
are defects *of the repair*, and they are the clearest evidence for amplifier 2:
making a dead path live exposes whatever that path was going to do wrong.

### 7. A week with no activity named a top driver

`substance_drivers` always carries all three keys, so `max(..., default=(None, {}))`
never fell through to its default and always returned a domain — at a contribution
of `0.0`. `top_substance_driver` said `"habits"`, the weekly summary text repeated
it, and the insight line read "Prioritize habits activities to make knowledge real"
to a learner who had logged nothing. The `"No significant activity detected"` branch
existed for exactly this state and was unreachable.

This is the same rule as the truthful-chip work: deriving a value is not a licence to
*name* it. A zero total now means no driver.

### 8. Completed future events counted as upcoming

`Event.is_upcoming()` is "in the future and not completed"; the metric compared only
the start time, so a future-dated COMPLETED event incremented `upcoming_count` while
also appearing in `completed_count` — analytics disagreeing with the event views.

Only the *status* half of `is_upcoming()` was adopted. It delegates to `is_past()`,
which compares whole dates and treats an undated event as not-past, so calling it
outright would have counted this morning's event and every unscheduled one as
upcoming. The divergence (time-precise here, date-granular there) is deliberate and
pinned by a test. CANCELLED is not excluded, because the model does not exclude it —
inventing a second rule here is how the two drift apart in the first place.

## The guard

`tests/unit/test_weekly_life_summary_composition.py` — 10 tests.

Its one structural decision is where the stubs sit. The metrics service is the
**real** one, so the `Result` wrapper and every asserted number come from production
code; the stubs are one layer further out, at the six `get_user_items_in_range`
delegations and the three Layer-0/2 reads. A test that stubbed `calculate_*_metrics`
instead would pass against defect 1.

It also pins the seam itself (`test_metrics_service_still_returns_result`): if the
metrics contract is ever changed to plain dicts, the unwrapping becomes dead and the
remaining assertions would keep passing for the wrong reason.

Verified non-vacuous — reverting the aggregator fails 9 of the 10.

Neo4j is deliberately not involved. The queries under those delegations are a
different subject, guarded by `tests/integration/test_knowledge_metrics_learner_scope.py`
and the per-domain analytics pipelines.

## Still open

- **Principle `alignment_score` units.** `rank() / CORE.rank()` is a judgment call.
  The metric had no prior working output, so nothing regressed either way, but a
  different mapping is defensible and no ADR fixes this.
- **"ALL 7 DOMAINS" in the aggregation service.** Its class and method docstrings
  claim seven Layer-1 domains; the code collects six (Finance is an admin-only
  Firefly sidecar, ADR-052, and is not gathered here). Only the one inline comment
  on an edited line was corrected.
- ~~**`AnalyticsAggregationService.__init__` types `metrics_service: Any`.**~~
  **CLOSED on #1032** — typed against `AnalyticsMetricsOperations`
  (`core/ports/analytics_protocols.py`). Verified by re-injecting the original
  defect at one call site: mypy now reports three `arg-type` errors where it
  previously reported none. The metric *payload* stays `dict[str, Any]` (Any policy
  Category C — see the protocol module docstring for why a TypedDict per domain
  would have to be `total=False` throughout and would buy no checking).
- **Per-learner substance magnitudes.** Already recorded as a KNOWN LIMITATION in
  `calculate_knowledge_metrics`' own docstring; unrelated to this class but on the
  same path.

## Finding more of this class

The three amplifiers above are not specific to analytics. Where they co-occur —
a broad error decorator, an `Any`-typed collaborator, and no output assertion — the
same defects are invisible by construction.

- Grep for services whose collaborators are typed `Any` and whose methods are
  wrapped in `@with_error_handling`. That pair means neither mypy nor the runtime
  will report a wrong field name.
- For any metric or report method with no test that asserts on its *output*, assume
  nothing about whether it has ever returned. Call it once with realistic inputs.
- `getattr(obj, "field", <default>)` is not a null guard when the attribute exists
  and holds `None`, or holds an enum. Defects 4 and 6 both wore that disguise.
