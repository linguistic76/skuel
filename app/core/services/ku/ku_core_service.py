"""
KuCoreService - Atomic Knowledge Unit CRUD
===========================================

CRUD operations for lightweight ontology/reference Kus.
Uses BaseService with curriculum domain config (shared content, admin-created).

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from typing import Any

from core.models.enums import Domain
from core.models.enums.entity_enums import EntityType
from core.models.ku.ku import Ku
from core.models.ku.ku_dto import KuDTO
from core.models.type_hints import EntityUID
from core.ports.backend_operations_typing import BackendOperations
from core.services.base_service import BaseService
from core.services.domain_config import create_curriculum_domain_config
from core.utils.result_simplified import Result


class KuCoreService(BaseService[BackendOperations[Ku], Ku]):
    """Core CRUD for atomic Knowledge Units.

    Ku is shared content (admin-created, publicly readable).
    No user ownership — uses curriculum domain config.
    """

    def __init__(self, backend: BackendOperations[Ku], event_bus: Any = None) -> None:
        super().__init__(backend=backend)
        self.event_bus = event_bus

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

    async def create_ku(
        self,
        title: str,
        aliases: list[str] | None = None,
        description: str | None = None,
        summary: str | None = None,
        domain: str | None = None,
        tags: list[str] | None = None,
    ) -> Result[Ku | None]:
        """Create a new atomic Knowledge Unit.

        Args:
            title: Ku title (e.g., "caffeine", "buzzing", "meditation")
            aliases: Alternative names
            description: Optional description
            summary: Optional summary
            domain: Optional domain classification
            tags: Optional tags
        """
        from core.utils.uid_generator import UIDGenerator

        uid = UIDGenerator.generate_knowledge_uid(title)

        # Build the frozen Ku end-to-end (ADR-035/ADR-065). domain crosses the
        # enum boundary here — an unknown value raises rather than silently
        # storing a raw string (CLAUDE.md § Enum-Enforced Boundaries).
        ku = Ku(
            uid=EntityUID(uid),
            entity_type=EntityType.KU,
            title=title,
            aliases=tuple(aliases) if aliases else (),
            description=description,
            summary=summary or "",
            domain=Domain(domain) if domain else Domain.KNOWLEDGE,
            tags=tuple(tags) if tags else (),
        )

        result: Result[Ku | None] = await self.backend.create(ku)  # type: ignore[assignment]  # Result invariance — Ku is always non-None here
        if result.is_error:
            return result

        # Post-persist embedding refresh (ADR-074) — the background worker embeds async
        from core.events.embedding_publisher import publish_embedding_requested

        await publish_embedding_requested(self.event_bus, EntityType.KU, ku, self.logger)

        return await self.backend.get(uid)

    async def get_ku(self, uid: str) -> Result[Ku | None]:
        """Get a Knowledge Unit by UID."""
        return await self.backend.get(uid)
