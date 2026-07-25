"""
Hierarchy Read Mixin
====================

The typed parent/child/hierarchy reads shared by the 6 activity domain core
services (Tasks, Goals, Habits, Events, Choices, Principles). Before this mixin,
each service carried a byte-identical trio (``get_sub<entity>`` /
``get_parent_<entity>`` / ``get_<entity>_hierarchy``) differing only in the
``(DTO, model)`` pair — 18 methods, one shape.

These return fully-typed domain models via ``BackendOperations.get_*_raw`` and are
DISTINCT from ``RelationshipOperationsMixin.get_hierarchy``, which returns raw
parent/child dicts via ``hierarchy_query_raw``.

REQUIRES (Mixin Dependencies, provided at runtime via BaseService MRO):
    - backend: B (a HierarchicalBackendOperations — CRUD + get_*_raw)
    - _dto_class / _model_class: the configured conversion classes
    - _to_domain_model: from ConversionHelpersMixin

Scoped to hierarchy-capable services only: its backend bound is
``HierarchicalBackendOperations`` (not plain ``BackendOperations``, which lacks
``get_*_raw``), so it is mixed into the 6 activity core services directly rather
than into ``BaseService`` (whose backends are not all hierarchy-capable).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.protocols import DomainModelProtocol, DTOProtocol
from core.models.type_hints import EntityUID
from core.ports import HierarchicalBackendOperations
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Errors, Result


class HierarchyReadMixin[B: HierarchicalBackendOperations, T: DomainModelProtocol]:
    """Shared typed hierarchy reads for the activity domains."""

    # Attributes provided by the composing class / sibling mixins at runtime.
    backend: B
    _dto_class: type[DTOProtocol] | None
    _model_class: type[T] | None

    if TYPE_CHECKING:
        # Provided at runtime by ConversionHelpersMixin (via BaseService MRO). The
        # signature must match that method exactly (an incompatible declaration would
        # be an MRO override error), so `data` stays Any:
        # boundary: mirrors ConversionHelpersMixin._to_domain_model — accepts model | DTO | dict.
        def _to_domain_model(
            self, data: Any, dto_class: type[DTOProtocol], model_class: type[T]
        ) -> T: ...

    def _ensure_conversion_classes(self) -> Result[tuple[type[DTOProtocol], type[T]]]:
        """Return the configured ``(dto_class, model_class)``, narrowed non-None.

        Both are synced from ``DomainConfig`` at init and validated by
        ``_validate_configuration``; a ``None`` here is a configuration bug for a
        conversion-capable domain, surfaced as a validation failure instead of an
        ``AttributeError`` deeper in the call.
        """
        dto_class = self._dto_class
        model_class = self._model_class
        if dto_class is None or model_class is None:
            return Result.fail(
                Errors.validation(
                    message="dto_class/model_class not configured for this domain",
                    field="configuration",
                )
            )
        return Result.ok((dto_class, model_class))

    @with_error_handling("get_subentities", error_type="database", uid_param="parent_uid")
    async def get_subentities(self, parent_uid: str, depth: int = 1) -> Result[list[T]]:
        """Get child entities of a parent at the given depth (typed domain models).

        Backend: ``BackendOperations.get_children_raw``.
        """
        classes = self._ensure_conversion_classes()
        if classes.is_error:
            return Result.fail(classes)
        dto_class, model_class = classes.value

        result = await self.backend.get_children_raw(parent_uid, depth)
        if result.is_error:
            return Result.fail(result)
        return Result.ok(
            [self._to_domain_model(data, dto_class, model_class) for data in result.value]
        )

    @with_error_handling("get_parent_entity", error_type="database", uid_param="child_uid")
    async def get_parent_entity(self, child_uid: str) -> Result[T | None]:
        """Get the immediate parent of a child entity, if any (typed domain model).

        Backend: ``BackendOperations.get_parent_raw``.
        """
        classes = self._ensure_conversion_classes()
        if classes.is_error:
            return Result.fail(classes)
        dto_class, model_class = classes.value

        result = await self.backend.get_parent_raw(child_uid)
        if result.is_error:
            return Result.fail(result)
        if result.value is None:
            return Result.ok(None)
        return Result.ok(self._to_domain_model(result.value, dto_class, model_class))

    @with_error_handling("get_entity_hierarchy", error_type="database", uid_param="uid")
    async def get_entity_hierarchy(self, uid: str) -> Result[dict[str, Any]]:
        """Full hierarchy context: ancestors, current, siblings, children, depth.

        Backend: ``BackendOperations.get_hierarchy_raw`` (typed models — not to be
        confused with ``RelationshipOperationsMixin.get_hierarchy``).

        Return shape (a genuinely heterogeneous map — ``list[T]`` / ``T`` / ``int``):
        ``{"ancestors": list[T], "current": T, "siblings": list[T], "children": list[T],
        "depth": int}``.
        boundary: dict[str, Any] is the domain-agnostic contract consumed by the shared
        hierarchy API factory (``Callable[[str], Awaitable[Result[dict[str, Any]]]]``, which
        JSON-serializes it); a generic TypedDict is not a subtype of that dict (PEP 589) and
        would only be unwrapped back at the factory boundary.
        """
        classes = self._ensure_conversion_classes()
        if classes.is_error:
            return Result.fail(classes)
        dto_class, model_class = classes.value

        current_result = await self.backend.get(uid)
        if current_result.is_error:
            return Result.fail(current_result)
        current = self._to_domain_model(current_result.value, dto_class, model_class)

        hierarchy_result = await self.backend.get_hierarchy_raw(EntityUID(uid))
        if hierarchy_result.is_error:
            return Result.fail(hierarchy_result)

        raw = hierarchy_result.value
        return Result.ok(
            {
                "ancestors": [
                    self._to_domain_model(n, dto_class, model_class) for n in raw["ancestors"]
                ],
                "current": current,
                "siblings": [
                    self._to_domain_model(n, dto_class, model_class) for n in raw["siblings"]
                ],
                "children": [
                    self._to_domain_model(n, dto_class, model_class) for n in raw["children"]
                ],
                "depth": len(raw["ancestors"]),
            }
        )
