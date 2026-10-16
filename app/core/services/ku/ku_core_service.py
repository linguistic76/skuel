"""
KuCoreService - Atomic Knowledge Unit reads
============================================

Reads for lightweight ontology/reference Kus. A Ku is authored in the content
vault (ADR-091 S8); this service creates none.
Uses BaseService with curriculum domain config (shared content).

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from core.models.ku.ku import Ku
from core.models.ku.ku_dto import KuDTO
from core.ports.backend_operations_typing import BackendOperations
from core.services.base_service import BaseService
from core.services.domain_config import create_curriculum_domain_config
from core.utils.result_simplified import Result


class KuCoreService(BaseService[BackendOperations[Ku], Ku]):
    """Core reads for atomic Knowledge Units.

    Ku is shared content (vault-authored, publicly readable).
    No user ownership — uses curriculum domain config.
    """

    def __init__(self, backend: BackendOperations[Ku]) -> None:
        super().__init__(backend=backend)

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

    async def get_ku(self, uid: str) -> Result[Ku | None]:
        """Get a Knowledge Unit by UID."""
        return await self.backend.get(uid)
