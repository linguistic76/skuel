"""
Ingestion API Routes - the admin ingestion dashboard's API
==========================================================

The API behind ``/ingest`` (``ingestion_ui.py``). Ingestion itself has ONE
door: the reconciler (ADR-070 Decision 9) — the dashboard's "Sync content
vault" button posts to ``POST /api/vault/sync/content``
(``adapters/inbound/vault_routes.py``), the personal-vault button to
``POST /api/vault/sync``, and ``./dev vault-sync`` runs the same engine in
process. Nothing here ingests a file: a raw per-file or per-manifest door
skips the tracker-driven reconciliation (deletions, edge retraction, 🆔
retirement, preview) that only the reconciler's walk performs.

Routes:
- POST /api/chunks/regenerate - re-run ingestion's chunking stage over stored
  :Content (admin tool; registered only when BatchChunkingService is wired)

Security:
- Admin role + CSRF
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.auth import make_service_getter, require_admin
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports import IngestionOperations
    from core.services.chunks.batch_chunking_service import BatchChunkingService

logger = get_logger("skuel.routes.ingestion")


def create_ingestion_api_routes(
    app,
    rt,
    unified_ingestion: IngestionOperations,
    user_service=None,
    batch_chunking_service: BatchChunkingService | None = None,
):
    """
    Create the ingestion dashboard's API routes.

    Args:
        app: FastHTML app instance
        rt: Router instance
        unified_ingestion: The UnifiedIngestionService instance — the surface's
            registration gate (DomainRouteConfig passes it as the primary
            service; no route here calls it).
        user_service: UserService instance for admin role checks
        batch_chunking_service: Admin tool for chunk regeneration.
            When None, the /api/chunks/regenerate route is not registered.
    """

    if not unified_ingestion:
        logger.error("UnifiedIngestionService not provided to ingestion API routes")
        return

    get_user_service = make_service_getter(user_service)

    # Chunk regeneration — admin tool, only registered when service is wired.
    # In CORE tier the service exists but publishes no embedding events.
    if batch_chunking_service is not None:

        @rt("/api/chunks/regenerate", methods=["POST"])
        @csrf_protected
        @require_admin(get_user_service)
        @boundary_handler()
        async def regenerate_chunks_route(request: Request, current_user: Any = None):
            """
            Regenerate :ContentChunk nodes for :Content parents.

            Request body (JSON, validated by RegenerateChunksRequest):
                parent_uids: list[str] | None — restrict to these uids. None = all.
                force: bool — regenerate even when chunks match current
                    CHUNKING_ALGORITHM_VERSION.

            Returns:
                Result wrapping RegenerationStats as a dict (counts + per-parent
                errors + duration). Per-parent failures do not fail the batch.
            """
            from pydantic import ValidationError

            from core.models.chunks_request import RegenerateChunksRequest

            try:
                payload = await request.json()
                body = RegenerateChunksRequest.model_validate(payload)
            except ValidationError as e:
                return Result.fail(
                    Errors.validation(
                        f"Invalid request body: {e.errors()}",
                        "body",
                        None,
                    )
                )

            result = await batch_chunking_service.regenerate_chunks(
                parent_uids=body.parent_uids,
                force=body.force,
            )
            if result.is_error:
                return Result.fail(result)
            return Result.ok(result.value.to_dict())

    logger.info("Ingestion API routes registered")


__all__ = ["create_ingestion_api_routes"]
