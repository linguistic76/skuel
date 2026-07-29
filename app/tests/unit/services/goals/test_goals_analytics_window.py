"""
Unit guards for the Goals period-analytics window filter.
=========================================================

``GoalsIntelligenceService.get_performance_analytics`` fetched its window with::

    await self.backend.find_by(user_uid=..., updated_at__gte=cutoff.isoformat())

Unlike the Choices defect in #859, that key is *not* dropped: ``updated_at`` is a real
``Goal`` field, so ``build_search_query`` accepts it and emits ``n.updated_at >= $bound``
with a **string** bound. ``updated_at`` is stored in two shapes — an ISO string from the
CRUD write path and a native temporal from the vault re-ingest path (``ON MATCH``) — and
Neo4j evaluates ``<temporal> >= <string>`` as null, so the re-ingested rows were silently
dropped. The endpoint returned a plausible number that was simply too low.

That is why "seed goals, assert non-empty" is not a valid guard here: the bug
**under**-returns, so a non-empty assertion passes against it. The negative control has to
be a row that must be *included* but was not — which is the integration half's job, since
only a real Neo4j can hold the temporal shape. See
tests/integration/test_goals_analytics_window.py.

What this cheap half pins is the *call*: that the service reaches for the coercing helper
at all, on the right field, with a live ``period_days``.

``TestNoBareComparisonOnMixedTimestamps`` is the durable part. Rather than naming the one
method that was wrong, it derives every site tree-wide that filters ``created_at`` or
``updated_at`` through a bare comparison operator, in any call or dict literal. That is the
forward guard for the three still-unimplemented siblings in
docs/reference/PLACEHOLDER_INDEX.md § Group A (habits / choices / principles period
analytics): whichever one is implemented next fails this test if it copies the goals call
instead of the documented helper. It carries its own positive control, because a scanner
that reports zero everywhere is indistinguishable from a scanner that cannot see.
"""

from __future__ import annotations

import ast
import re
from dataclasses import fields
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

import adapters
import core
import services_bootstrap
import ui
from core.models.goal.goal import Goal
from core.services.goals.goals_intelligence_service import GoalsIntelligenceService
from core.utils.result_simplified import Result

GOAL_FIELDS = {f.name for f in fields(Goal)}

USER = "user_goal_window"


class RecordingBackend:
    """Records whichever fetch the service reaches for, so either shape can be inspected."""

    def __init__(self, goals: list[Goal] | None = None) -> None:
        self.goals = goals or []
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def find_by(self, **filters: Any) -> Result[list[Goal]]:
        self.calls.append(("find_by", filters))
        return Result.ok(self.goals)

    async def find_by_date_range(self, **kwargs: Any) -> Result[list[Goal]]:
        self.calls.append(("find_by_date_range", kwargs))
        return Result.ok(self.goals)

    def referenced_model_fields(self) -> set[str]:
        """Every ``Goal`` field name the recorded calls tried to filter or sort on."""
        referenced: set[str] = set()
        for name, kwargs in self.calls:
            if name == "find_by":
                for key in kwargs:
                    if key in {"limit", "offset", "sort_by", "sort_order"}:
                        continue
                    referenced.add(key.rsplit("__", 1)[0] if "__" in key else key)
            else:
                referenced.add(str(kwargs["date_field"]))
                referenced.update(kwargs.get("additional_filters") or {})
        return referenced


def make_service(backend: RecordingBackend) -> GoalsIntelligenceService:
    # GoalsIntelligenceService declares _require_relationships = True, so construction
    # refuses a missing relationship service. get_performance_analytics never reaches a
    # relationship read — it is backend fetch plus pure Python — so the stub only has to
    # satisfy the constructor's fail-fast check.
    return GoalsIntelligenceService(backend=backend, relationship_service=MagicMock())


@pytest.mark.asyncio
class TestPerformanceAnalyticsWindow:
    """The window fetch must use the coercing helper, on the field it claims."""

    async def test_window_uses_the_coercing_helper_not_a_bare_comparison(self) -> None:
        """RED before the fix: the one call was ``find_by`` with ``updated_at__gte``.

        ``find_by`` reaches ``build_search_query``, which emits a bare ``>=`` against the
        bound as given. Only ``find_by_date_range`` coerces the *stored* value first, so
        naming the helper is the whole fix.
        """
        backend = RecordingBackend()
        result = await make_service(backend).get_performance_analytics(USER, period_days=30)
        assert result.is_ok, f"get_performance_analytics failed: {result}"

        assert len(backend.calls) == 1, f"expected one fetch, got {backend.calls}"
        name, _kwargs = backend.calls[0]
        assert name == "find_by_date_range", (
            "the window went through find_by, which compares a string bound against a "
            "mixed-representation field and drops the temporally-stored rows"
        )

    async def test_window_field_is_updated_at(self) -> None:
        """``updated_at`` is the decided key: recent *activity*, not corpus entry."""
        backend = RecordingBackend()
        await make_service(backend).get_performance_analytics(USER, period_days=30)

        _name, kwargs = backend.calls[0]
        assert kwargs["date_field"] == "updated_at"

    async def test_window_is_open_ended_and_user_scoped(self) -> None:
        """A rolling "last N days" report has a lower bound only.

        ``end_date=date.today()`` would not *break* it — the coercion is day-granular, so
        ``<= date(today)`` still admits today's rows — but it would silently drop any row
        whose ``updated_at`` is ahead of the clock (skew, a bad import), which is a
        different decision than "since the cutoff" and not one this method makes.
        """
        backend = RecordingBackend()
        await make_service(backend).get_performance_analytics(USER, period_days=30)

        _name, kwargs = backend.calls[0]
        assert kwargs["start_date"] == date.today() - timedelta(days=30)
        assert kwargs["end_date"] is None
        assert (kwargs.get("additional_filters") or {})["user_uid"] == USER

    async def test_window_fetch_only_names_real_goal_fields(self) -> None:
        """Every field the fetch names must exist on Goal.

        ``find_by_date_range`` validates ``date_field`` with a regex only — no model-aware
        gate — so an unknown name reaches Cypher as ``n.<typo>`` and matches nothing.

        A forward guard, not a regression proof: this **passes pre-fix**, and that is the
        point. It is the generic guard #859 leaned on for the Choices defect, and it is
        structurally blind to this one — ``updated_at`` is a real ``Goal`` field, so the
        bad call named nothing unknown. Field-name membership catches a dropped predicate;
        it cannot catch a predicate that is emitted and then evaluates to null.
        """
        backend = RecordingBackend()
        await make_service(backend).get_performance_analytics(USER, period_days=30)

        unknown = backend.referenced_model_fields() - GOAL_FIELDS
        assert not unknown, f"fetch names {sorted(unknown)}, which Goal does not declare"

    async def test_period_days_is_live(self) -> None:
        """A different ``period_days`` must move the bound — it is the whole parameter."""
        bounds = []
        for period_days in (7, 365):
            backend = RecordingBackend()
            await make_service(backend).get_performance_analytics(USER, period_days=period_days)
            _name, kwargs = backend.calls[0]
            bounds.append(kwargs["start_date"])

        assert bounds[0] != bounds[1]

    async def test_the_window_is_not_silently_capped_at_the_helper_default(self) -> None:
        """``find_by_date_range`` defaults to ``limit=100``.

        Every metric in the response is a count or a mean over the returned set, so the
        default page size would understate all of them for a prolific user — the same
        silent-under-return class as the bug this method had.
        """
        backend = RecordingBackend()
        await make_service(backend).get_performance_analytics(USER, period_days=30)

        _name, kwargs = backend.calls[0]
        assert kwargs["limit"] > 100, (
            "left on the helper's default page size; total_goals would cap silently"
        )


# ============================================================================
# Tree-wide guard: no bare comparison against a mixed-representation timestamp
# ============================================================================

# ``created_at`` and ``updated_at`` are each written in two shapes (ISO string from the
# CRUD path, native temporal from the bulk re-ingest path), so a bare comparison operator
# against either one is wrong wherever it appears. Both spellings that reach
# ``build_search_query`` are covered: a call keyword (``find_by(updated_at__gte=...)``,
# ``count(...)``) and a dict-literal key (``list(filters={"updated_at__gte": ...})``).
_MIXED_TIMESTAMP_COMPARISON = re.compile(r"^(created_at|updated_at)__(gt|gte|lt|lte)$")

# Docstrings and comments are neither Call keywords nor Dict keys, so prose that *describes*
# the anti-pattern — as core/services/choices/_analytics_mixin.py does — cannot trip this.
_GUARDED_TREES = (core, adapters, ui, services_bootstrap)

_POSITIVE_CONTROL_SOURCE = """
async def window(backend, user_uid, cutoff):
    a = await backend.find_by(user_uid=user_uid, updated_at__gte=cutoff)
    b = await backend.count(created_at__lt=cutoff)
    c = await backend.list(filters={"updated_at__lte": cutoff})
    return a, b, c
"""


def _scan_source(source: str, label: str) -> list[str]:
    """Every bare-comparison site in one module, as ``label:lineno key`` strings."""
    hits: list[str] = []
    module = ast.parse(source)
    for node in ast.walk(module):
        if isinstance(node, ast.Call):
            hits.extend(
                f"{label}:{node.lineno} {keyword.arg}="
                for keyword in node.keywords
                if keyword.arg and _MIXED_TIMESTAMP_COMPARISON.match(keyword.arg)
            )
        elif isinstance(node, ast.Dict):
            hits.extend(
                f"{label}:{key.lineno} {{{key.value!r}: ...}}"
                for key in node.keys
                if isinstance(key, ast.Constant)
                and isinstance(key.value, str)
                and _MIXED_TIMESTAMP_COMPARISON.match(key.value)
            )
    return hits


def _tree_paths() -> list[Path]:
    """Resolve the guarded trees from their packages, not from a path guess."""
    return [Path(next(iter(pkg.__path__))).resolve() for pkg in _GUARDED_TREES]


class TestNoBareComparisonOnMixedTimestamps:
    """No tree above the persistence boundary may window these two fields with ``>=``."""

    def test_the_scanner_detects_all_three_spellings(self) -> None:
        """Positive control. Without it, a clean sweep proves nothing about the sweep.

        A scanner that silently reports zero — wrong node types, a regex that never
        matches, an unparsed file — reads exactly like a clean tree. This pins that the
        detector fires on the kwarg form the goals defect used *and* on the two sibling
        spellings that reach the same query builder.
        """
        hits = _scan_source(_POSITIVE_CONTROL_SOURCE, "control")

        assert len(hits) == 3, f"scanner saw {len(hits)} of 3 known-bad sites: {hits}"

    def test_the_scanner_ignores_prose_describing_the_anti_pattern(self) -> None:
        """Negative control: the pattern in a docstring or comment is documentation.

        core/services/choices/_analytics_mixin.py records why it does *not* use
        ``find_by(created_at__gte=...)``, and this method's own docstring does the same.
        A line-scan would flag both and pressure the next author to delete the warning.
        """
        prose = '''
def window():
    """Routed through find_by_date_range, not find_by(created_at__gte=...)."""
    # ...nor count(updated_at__gte=...), for the same reason.
    return None
'''
        assert _scan_source(prose, "prose") == []

    def test_no_guarded_tree_filters_a_mixed_timestamp_with_a_bare_comparison(self) -> None:
        """The sweep itself.

        The remedy is ``find_by_date_range(date_field=...)``, which coerces the stored
        value before comparing — see the helper's contract on
        ``EntitySearchOperations.find_by_date_range`` and
        docs/reference/PLACEHOLDER_INDEX.md § Group A.
        """
        hits: list[str] = []
        scanned = 0
        for tree in _tree_paths():
            for path in sorted(tree.rglob("*.py")):
                scanned += 1
                hits.extend(
                    _scan_source(
                        path.read_text(encoding="utf-8"), str(path.relative_to(tree.parent))
                    )
                )

        # Guards the sweep against a silently empty file list (a bad rglob, a moved package).
        assert scanned > 100, f"only {scanned} modules scanned — the tree walk is broken"
        assert hits == [], (
            "bare comparison against a mixed-representation timestamp — the "
            "temporally-stored rows are silently dropped:\n  " + "\n  ".join(hits)
        )
