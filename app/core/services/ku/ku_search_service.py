"""
KuSearchService - Atomic Knowledge Unit Search
===============================================

Search operations for atomic Kus: full-text, tags, NOUS topic membership.
Inherits search(), get_by_category(), get_by_status() from BaseService.
Exposed on the facade as ``KuService.search`` (sub-service attribute), which
is what SearchRouter resolves for KU domain searches.

See: /docs/architecture/SEARCH_ARCHITECTURE.md
"""

from typing import Any

from core.models.ku.ku import Ku
from core.models.ku.ku_dto import KuDTO
from core.ports.backend_operations_typing import BackendOperations
from core.services.base_service import BaseService
from core.services.domain_config import create_curriculum_domain_config
from core.utils.result_simplified import Result


class KuSearchService(BaseService[BackendOperations[Ku], Ku]):
    """Search for atomic Knowledge Units.

    Inherits from BaseService:
    - search(query, user_uid) — full-text search
    - get_by_category(category, user_uid) — filter by NOUS topic membership
    - get_by_status(status, user_uid) — filter by status
    - list_categories(user_uid) — list unique NOUS topics
    """

    _config = create_curriculum_domain_config(
        dto_class=KuDTO,
        model_class=Ku,
        domain_name="ku",
        search_fields=("title", "description", "summary"),
        category_field="nous",  # NOUS topic membership (array — `has` semantics)
        supports_user_progress=False,
        entity_label="Ku",
    )

    async def list_nous_subtopics(self) -> Result[list[str]]:
        """List the NOUS sub-topic vocabulary — distinct `nous_subtopic` values.

        The 2nd taxonomy level beneath `nous`. Derived from the graph exactly
        like `list_all_categories()` (the NOUS-topic vocabulary), but reads the
        `nous_subtopic` array property rather than the configured `category_field`.
        Array-valued: `distinct_values_raw` UNWINDs each element to its own value.

        Fail-soft: with no authored `nous_subtopic` data the list is empty, so
        the faucet renders nothing (no data yet — the mechanism ships ahead of
        the vault content).

        Backend: ``UniversalNeo4jBackend.distinct_values_raw("nous_subtopic")``.
        """
        result = await self.backend.distinct_values_raw("nous_subtopic", user_uid=None)
        if result.is_error:
            return Result.fail(result)
        subtopics = [record["value"] for record in (result.value or []) if record.get("value")]
        return Result.ok(subtopics)

    async def nous_subtopic_map(self) -> Result[dict[str, list[str]]]:
        """Map each NOUS topic to the sub-topics authored alongside it.

        Derived from the graph (distinct co-occurring `nous` + `nous_subtopic`
        pairs across `:Ku` + `:PathStep`), never hardcoded — the dependent
        /search dropdown narrows sub-topic options to the selected NOUS topic
        without the taxonomy ever leaving the vault (content boundary).

        Fail-soft: with no authored `nous_subtopic` data the map is empty, so the
        dependent control degrades to the same fail-soft-empty behaviour as the
        flat vocabulary (`list_nous_subtopics`).

        Backend: ``KuBackend.nous_subtopic_pairs``.
        """
        result = await self.backend.nous_subtopic_pairs()  # type: ignore[attr-defined]
        if result.is_error:
            return Result.fail(result)
        mapping: dict[str, list[str]] = {}
        for record in result.value or []:
            nous = record.get("nous")
            subtopic = record.get("subtopic")
            if not nous or not subtopic:
                continue
            mapping.setdefault(nous, []).append(subtopic)
        return Result.ok(mapping)

    async def search_by_alias(
        self, alias: str
    ) -> Result[list[dict[str, Any]]]:  # boundary: Neo4j node properties — Ku fields
        """Search Kus by alias (alternative name).

        Args:
            alias: Alias to search for (case-insensitive substring)

        Returns:
            Result containing list of matching Ku property dicts from Neo4j
        """
        result = await self.backend.search_by_alias(alias)  # type: ignore[attr-defined]
        if result.is_error:
            return Result.fail(result)

        return Result.ok([record["ku"] for record in (result.value or [])])
