"""
Analytics Protocols
===================

The metrics surface that cross-layer aggregation consumes.

Implementation: core/services/analytics/analytics_metrics_service.py
                (``AnalyticsMetricsService``)
Consumer: core/services/analytics/analytics_aggregation_service.py
          (``AnalyticsAggregationService``)

WHY THIS EXISTS: ``AnalyticsAggregationService`` typed its collaborator ``Any``,
which erased the return type of all fifteen ``calculate_*_metrics`` calls it
makes. Storing those ``Result`` objects straight into parameters annotated
``dict[str, dict]`` was therefore invisible to mypy at every site, and stayed
invisible until the reports raised at runtime. Typing the collaborator against
this protocol makes that exact substitution an ``arg-type`` error.

WHY THE PAYLOAD STAYS ``dict[str, Any]``: Category C of the Any policy — the
metric payloads are genuinely heterogeneous. Each domain returns a different key
set, the values span int / float / str / list / nested dict, and every method has
a zero-activity early return carrying fewer keys than its populated one. A
TypedDict per domain would have to be ``total=False`` throughout, which buys no
checking the aggregator's ``.get(key, default)`` reads don't already tolerate.
The defect class this file closes is Result-vs-dict, not key-level drift.

See: /docs/patterns/protocol_architecture.md, /docs/patterns/ANY_USAGE_POLICY.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from datetime import date

    from core.models.type_hints import UserUID


@runtime_checkable
class AnalyticsMetricsOperations(Protocol):
    """Per-domain and per-layer metric calculation, each fallible.

    Every method returns ``Result`` — a failed layer is a value to unwrap, not an
    exception to catch. Aggregation degrades a failed layer to an empty dict; it
    must never hand the ``Result`` itself to the analysis helpers.

    Layer 1 (activities) takes a window; Layer 0 curriculum is point-in-time.
    """

    # Layer 1: activity domains
    async def calculate_task_metrics(
        self, user_uid: UserUID, start_date: date, end_date: date
    ) -> Result[dict[str, Any]]: ...

    async def calculate_habit_metrics(
        self, user_uid: UserUID, start_date: date, end_date: date
    ) -> Result[dict[str, Any]]: ...

    async def calculate_goal_metrics(
        self, user_uid: UserUID, start_date: date, end_date: date
    ) -> Result[dict[str, Any]]: ...

    async def calculate_event_metrics(
        self, user_uid: UserUID, start_date: date, end_date: date
    ) -> Result[dict[str, Any]]: ...

    async def calculate_choice_metrics(
        self, user_uid: UserUID, start_date: date, end_date: date
    ) -> Result[dict[str, Any]]: ...

    async def calculate_principle_metrics(
        self, user_uid: UserUID, start_date: date, end_date: date
    ) -> Result[dict[str, Any]]: ...

    # Layer 0: curriculum
    async def calculate_knowledge_metrics(
        self, user_uid: UserUID, start_date: date, end_date: date
    ) -> Result[dict[str, Any]]: ...

    async def calculate_curriculum_metrics(self, user_uid: UserUID) -> Result[dict[str, Any]]: ...

    # Layer 2: reflection
    async def calculate_journal_metrics(
        self, user_uid: UserUID, start_date: date, end_date: date
    ) -> Result[dict[str, Any]]: ...
