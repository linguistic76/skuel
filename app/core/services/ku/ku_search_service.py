"""
KuSearchService - Atomic Knowledge Unit Search
===============================================

Search operations for atomic Kus: full-text, tags, NOUS topic membership.
Inherits search(), get_by_category(), get_by_status() from BaseService.
Exposed on the facade as ``KuService.search`` (sub-service attribute), which
is what SearchRouter resolves for KU domain searches.

See: /docs/architecture/SEARCH_ARCHITECTURE.md
"""

from typing import Any, cast

from core.models.ku.ku import Ku
from core.models.ku.ku_dto import KuDTO
from core.ports.curriculum_protocols import KuOperations
from core.ports.query_types import NousSubtopicPair, to_nous_subtopic_pairs
from core.services.base_service import BaseService
from core.services.domain_config import create_curriculum_domain_config
from core.utils.result_simplified import Result


class KuSearchService(BaseService[KuOperations, Ku]):
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
        # Keyword search covers title/description only — matches ku_fulltext_idx
        # (neo4j_schema_manager) and the SEARCH_FIELD_CONFIG fallback. `summary`
        # stays content-bearing for embeddings, not keyword search — don't re-add.
        search_fields=("title", "description"),
        category_field="nous",  # NOUS topic membership (array — `has` semantics)
        supports_user_progress=False,
        entity_label="Ku",
    )

    async def nous_subtopic_pairs(self) -> Result[list[NousSubtopicPair]]:
        """This Ku label's contribution of (nous, nous_subtopic) co-occurrence pairs.

        Scoped to `:Ku` — `SearchRouter.nous_subtopic_map` folds this together
        with the PathStep contribution (`PsSearchService.nous_subtopic_pairs`)
        into the dependent /search dropdown's map. The cross-domain merge stays in
        the service layer, not this per-domain sub-service. Raw Neo4j property
        unions are narrowed to typed string pairs here at the domain boundary.

        Backend: ``KuBackend.nous_subtopic_pairs``.
        """
        result = await self.backend.nous_subtopic_pairs()
        if result.is_error:
            return Result.fail(result)
        return Result.ok(to_nous_subtopic_pairs(result.value or []))

    async def search_by_alias(
        self, alias: str
    ) -> Result[list[dict[str, Any]]]:  # boundary: Neo4j node properties — Ku fields
        """Search Kus by alias (alternative name).

        Args:
            alias: Alias to search for (case-insensitive substring)

        Returns:
            Result containing list of matching Ku property dicts from Neo4j
        """
        result = await self.backend.search_by_alias(alias)
        if result.is_error:
            return Result.fail(result)

        # Each row's "ku" is a Neo4j node projected to a property dict.
        return Result.ok([cast("dict[str, Any]", record["ku"]) for record in (result.value or [])])
