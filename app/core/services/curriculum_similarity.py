"""Curriculum ``find_similar_*`` — the shared tail of the PathStep and LearningPath AI services.

Curriculum is shared content, so its similarity pool is the whole label — and
a listing of the whole label is exactly what the publication gate guards.
Ranking therefore goes through the vector-discovery chokepoint
(``VectorSearchBackend.query_vector_index``), which withholds draft-marked
curriculum, rather than over a ``backend.list()`` pool ranked in Python.
"""

from collections.abc import Sequence

from core.models.entity import Entity
from core.models.enums.entity_enums import EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.type_hints import EntityUID
from core.services.neo4j_vector_search_service import Neo4jVectorSearchService
from core.utils.embedding_text_builder import build_embedding_text
from core.utils.result_simplified import Result


async def rank_similar_curriculum(
    vector_search: Neo4jVectorSearchService,
    label: NeoLabel,
    entity_type: EntityType,
    source: Entity,
    *,
    limit: int,
) -> Result[list[tuple[EntityUID, float]]]:
    """Nearest neighbours of ``source`` in its own label's vector index.

    The source's stored ``embedding`` is the query vector when it has one;
    otherwise its canonical embedding text (``build_embedding_text``, the text
    the stored vectors were built from) is embedded once. The index answers
    the ``limit + 1`` nearest published nodes and the source itself is
    dropped, so the list holds at most ``limit`` — and fewer when drafts sit
    among the nearest neighbours, since the gate is a post-filter on the
    index's answer. Scores are the index's ``[0, 1]`` cosine scale,
    thresholded at ``ku_similar_min_score`` — the node→node threshold the
    text→entity label defaults are too strict for.
    """
    min_score = vector_search.config.ku_similar_min_score
    fetch = limit + 1
    vector: Sequence[float] | None = source.embedding
    if vector is not None:
        hits_result = await vector_search.find_similar_by_vector(
            label=label, embedding=list(vector), limit=fetch, min_score=min_score
        )
    else:
        hits_result = await vector_search.find_similar_by_text(
            label=label,
            text=build_embedding_text(entity_type, source),
            limit=fetch,
            min_score=min_score,
        )
    if hits_result.is_error:
        return Result.fail(hits_result)

    ranked = [
        (EntityUID(str(hit["node"]["uid"])), float(hit["score"]))
        for hit in hits_result.value
        if hit["node"]["uid"] != source.uid
    ]
    return Result.ok(ranked[:limit])
