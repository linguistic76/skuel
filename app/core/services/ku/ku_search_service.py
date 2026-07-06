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
