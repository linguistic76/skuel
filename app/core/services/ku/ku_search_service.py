"""
KuSearchService - Atomic Knowledge Unit Search
===============================================

Search operations for atomic Kus: by namespace, tags, category.
Inherits search(), get_by_category(), get_by_status() from BaseService.

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
    - get_by_category(category, user_uid) — filter by namespace
    - get_by_status(status, user_uid) — filter by status
    - list_categories(user_uid) — list unique namespaces

    Adds:
    - get_by_namespace(namespace) — domain-specific namespace search
    """

    _config = create_curriculum_domain_config(
        dto_class=KuDTO,
        model_class=Ku,
        domain_name="ku",
        search_fields=("title", "description", "summary"),
        category_field="namespace",
        supports_user_progress=False,
        entity_label="Ku",
    )

    async def get_by_namespace(self, namespace: str) -> Result[list[dict[str, Any]]]:
        """Get all Kus in a specific namespace.

        Args:
            namespace: Namespace to filter by (e.g., "attention", "emotion")

        Returns:
            Result containing list of Ku dicts
        """
        query = """
        MATCH (ku:Entity:Ku {namespace: $namespace})
        RETURN ku
        ORDER BY ku.title ASC
        """
        result = await self.backend.execute_query(query, {"namespace": namespace})
        if result.is_error:
            return Result.fail(result.expect_error())

        return Result.ok([record["ku"] for record in (result.value or [])])

    async def search_by_alias(self, alias: str) -> Result[list[dict[str, Any]]]:
        """Search Kus by alias (alternative name).

        Args:
            alias: Alias to search for (case-insensitive substring)

        Returns:
            Result containing list of matching Ku dicts
        """
        query = """
        MATCH (ku:Entity:Ku)
        WHERE any(a IN ku.aliases WHERE toLower(a) CONTAINS toLower($alias))
        RETURN ku
        ORDER BY ku.title ASC
        """
        result = await self.backend.execute_query(query, {"alias": alias})
        if result.is_error:
            return Result.fail(result.expect_error())

        return Result.ok([record["ku"] for record in (result.value or [])])
