"""The curriculum services as one typed set.

The composition root builds the curriculum facades and the services they share in
one call and hands the set to the wiring steps that follow. Each key names the
class built under it, so a read of ``learning_services["ps"]`` is a ``PsService``
to the type checker. The embedding pair is ``None`` where the intelligence tier
builds no embeddings.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from core.services.embeddings_service import EmbeddingsService
    from core.services.ku_service import KuService
    from core.services.lp.lp_intelligence_service import LpIntelligenceService
    from core.services.lp_service import LpService
    from core.services.neo4j_vector_search_service import Neo4jVectorSearchService
    from core.services.ps_service import PsService
    from core.services.user_progress_service import UserProgressService


class LearningServices(TypedDict):
    """The curriculum facades, the progress service and the embedding pair."""

    learning_intelligence: LpIntelligenceService
    atomic_ku_service: KuService
    user_progress: UserProgressService
    learning_paths: LpService
    ps: PsService
    embeddings_service: EmbeddingsService | None
    vector_search_service: Neo4jVectorSearchService | None
