"""Protocol for services that provide filtered, sorted entity lists with stats.

FilteredContextProvider is the standard interface through which intelligence
services understand domain state — a per-domain drill-down that complements
UserContext's broad snapshot.

UserContext is the map (broad snapshot from the MEGA-QUERY).
get_filtered_context() is the zoom lens (per-domain filtered view with stats).

Implemented by the six Activity Domain facades and by ``PsService``, ``LpService``
and ``ExerciseService``. ``KuService`` is not a provider. The composition root checks
every facade it registers against this protocol.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.models.type_hints import UserUID
from core.ports.query_types import ListContext
from core.utils.result_simplified import Result


@runtime_checkable
class FilteredContextProvider(Protocol):
    """Protocol for services that provide filtered, sorted entity lists with stats.

    The protocol captures the common params (user_uid, status_filter, sort_by).
    Concrete facades add domain-specific params with defaults (e.g., tasks has
    project/assignee, principles has category_filter), which satisfies structural
    subtyping since the base signature is always callable.

    Intelligence services depend on this for domain-agnostic entity listings.
    """

    async def get_filtered_context(
        self,
        user_uid: UserUID,
        status_filter: str = ...,
        sort_by: str = ...,
    ) -> Result[ListContext]: ...
