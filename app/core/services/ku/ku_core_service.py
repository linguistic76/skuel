"""
KuCoreService - Atomic Knowledge Unit CRUD
===========================================

CRUD operations for lightweight ontology/reference Kus.
Uses BaseService with curriculum domain config (shared content, admin-created).

See: /docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md
"""

from typing import Any

from core.models.ku.ku import Ku
from core.models.ku.ku_dto import KuDTO
from core.models.enums.entity_enums import EntityType
from core.ports.backend_operations_typing import BackendOperations
from core.services.base_service import BaseService
from core.services.domain_config import create_curriculum_domain_config
from core.utils.result_simplified import Result


class KuCoreService(BaseService[BackendOperations[Ku], Ku]):
    """Core CRUD for atomic Knowledge Units.

    Ku is shared content (admin-created, publicly readable).
    No user ownership — uses curriculum domain config.
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

    async def create_ku(
        self,
        title: str,
        namespace: str | None = None,
        ku_category: str | None = None,
        aliases: list[str] | None = None,
        source: str | None = None,
        description: str | None = None,
        summary: str | None = None,
        domain: str | None = None,
        tags: list[str] | None = None,
    ) -> Result[KuDTO]:
        """Create a new atomic Knowledge Unit.

        Args:
            title: Ku title (e.g., "caffeine", "buzzing", "meditation")
            namespace: Primary grouping (attention, emotion, body, ...)
            ku_category: state/concept/principle/intake/substance/practice/value
            aliases: Alternative names
            source: self_observation/research/teacher
            description: Optional description
            summary: Optional summary
            domain: Optional domain classification
            tags: Optional tags
        """
        from core.utils.uid_generator import UIDGenerator

        uid = UIDGenerator.generate_knowledge_uid(title)

        properties: dict[str, Any] = {
            "uid": uid,
            "title": title,
            "entity_type": EntityType.KU.value,
            "namespace": namespace,
            "ku_category": ku_category,
            "aliases": aliases or [],
            "source": source,
            "description": description,
            "summary": summary,
            "domain": domain,
            "tags": tags or [],
        }

        # Filter None values
        properties = {k: v for k, v in properties.items() if v is not None}

        result = await self.backend.create(properties)
        if result.is_error:
            return result

        return await self.backend.get(uid)

    async def get_ku(self, uid: str) -> Result[Ku]:
        """Get a Knowledge Unit by UID."""
        return await self.backend.get(uid)
