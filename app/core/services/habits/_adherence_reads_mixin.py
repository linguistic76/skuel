"""The Habits facade's hydrated reads — every Habit a read returns carries its derived ``success_rate``.

``Habit.success_rate`` is derived at read time (``core.services.habits._adherence``).
This mixin sits first in ``HabitsService``'s MRO and wraps the inherited CRUD reads
the route factories call (``get``, ``get_for_user``, ``list``) so the habit a route
serializes, and the habit a cross-domain caller reads, carries the rate — never
the node's stale number; the facade's own read methods go through the same
helpers. ``verify_ownership`` stays unhydrated: it is the gate in front of every
write, and a write has no use for the rate. A write's result (create, update,
complete) is the stored entity — its rate is ``None`` until it is read.

A mixin rather than methods on the facade body so the facade's own ``list[...]``
annotations keep meaning the builtin.
"""

from __future__ import annotations

import builtins
from typing import TYPE_CHECKING

from core.services.habits._adherence import (
    enrich_habit_with_adherence,
    enrich_habits_with_adherence,
)
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.habit.habit import Habit
    from core.models.type_hints import FilterParams, UserUID
    from core.ports.domain_protocols import HabitsOperations


class _AdherenceReadsMixin:
    """Hydrates the inherited CRUD reads of ``HabitsService``."""

    backend: HabitsOperations

    async def get(self, uid: str) -> Result[Habit]:
        return await self._with_adherence(await super().get(uid))  # type: ignore[misc]

    async def get_for_user(self, uid: str, user_uid: UserUID) -> Result[Habit]:
        return await self._with_adherence(
            await super().get_for_user(uid, user_uid)  # type: ignore[misc]
        )

    async def list(
        self,
        limit: int = 100,
        offset: int = 0,
        filters: FilterParams | None = None,
        sort_by: str | None = None,
        sort_order: str = "asc",
        user_uid: UserUID | None = None,
        order_by: str | None = None,
        order_desc: bool = False,
    ) -> Result[tuple[builtins.list[Habit], int]]:
        return await self._page_with_adherence(
            await super().list(  # type: ignore[misc]
                limit=limit,
                offset=offset,
                filters=filters,
                sort_by=sort_by,
                sort_order=sort_order,
                user_uid=user_uid,
                order_by=order_by,
                order_desc=order_desc,
            )
        )

    async def enrich_with_adherence(
        self, habits: builtins.list[Habit]
    ) -> Result[builtins.list[Habit]]:
        """``habits`` with their derived ``success_rate`` — ``None`` where a habit has no rate yet."""
        return await enrich_habits_with_adherence(self.backend, habits)

    async def _with_adherence(self, result: Result[Habit]) -> Result[Habit]:
        if result.is_error:
            return result
        return await enrich_habit_with_adherence(self.backend, result.value)

    async def _list_with_adherence(
        self, result: Result[builtins.list[Habit]]
    ) -> Result[builtins.list[Habit]]:
        if result.is_error:
            return result
        return await self.enrich_with_adherence(result.value)

    async def _page_with_adherence(
        self, result: Result[tuple[builtins.list[Habit], int]]
    ) -> Result[tuple[builtins.list[Habit], int]]:
        if result.is_error:
            return result
        habits, total = result.value
        enriched = await self.enrich_with_adherence(habits)
        if enriched.is_error:
            return Result.fail(enriched)
        return Result.ok((enriched.value, total))
