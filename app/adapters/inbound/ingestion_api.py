"""
Ingestion API Routes - Unified Content Ingestion API
=====================================================

API routes for the UnifiedIngestionService (ADR-014).
Handles both MD and YAML formats for all entity types.

Ownership (ADR-070):
- Every route here passes ``user_uid=current_user.uid`` as an *acting-user hint*
  only. The real owner of any USER_OWNED entity is resolved from the vault
  descriptor governing the *target path*, not from the caller's identity. See the
  canonical acts-as ownership model in core/services/vault/vault_descriptor.py
  (VaultRegistry.resolve_by_path).

Security:
- All routes require admin role + CSRF
- Path traversal validation via `_validate_ingestion_path`:
  1. `SKUEL_INGESTION_ALLOWED_PATHS` (colon-separated) — explicit override.
  2. Else `INGESTION_PATH` — the configured vault root.
  3. Neither set — fail closed. Default-deny, not default-allow.

Routes:
- POST /api/ingest/file - Ingest single file (MD or YAML)
- POST /api/ingest/vault - Ingest Obsidian vault
- POST /api/ingest/bundle - Ingest domain bundle with manifest
- POST /api/ingest/domain/{domain_name} - Ingest a domain directory

The raw arbitrary-path ``POST /api/ingest/directory`` door was retired (ADR-070
Decision 9); directory ingestion of the content vault runs through the reconciler
(``POST /api/vault/sync/content``).
"""

import asyncio
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from starlette.websockets import WebSocket, WebSocketDisconnect

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

# Global dictionary to store active WebSocket connections by operation_id
_active_connections: dict[str, WebSocket] = {}

# Background tasks must be stored to prevent garbage collection (RUF006)
_background_tasks: set[asyncio.Task[None]] = set()


def broadcast_progress(operation_id: str, progress_data: dict[str, Any]) -> None:
    """
    Broadcast progress update to WebSocket connection.

    Args:
        operation_id: UUID of the ingestion operation
        progress_data: Progress data to send
    """
    if operation_id in _active_connections:
        ws = _active_connections[operation_id]
        try:
            task = asyncio.create_task(ws.send_json(progress_data))
            _background_tasks.add(task)
            task.add_done_callback(_background_tasks.discard)
        except Exception as e:  # safety-net: WebSocket send may fail for any reason
            logger.error(f"Failed to broadcast progress: {e}")


def _resolve_allowed_ingestion_roots() -> list[Path]:
    """Resolve the effective ingestion allowlist from env (precedence order).

    1. `SKUEL_INGESTION_ALLOWED_PATHS` (colon-separated) — explicit override,
       useful when an admin runs multi-vault setups or staging directories.
    2. `INGESTION_PATH` — the single vault root (also the configured ingestion
       default at `core/config/unified_config.py`).
    3. Neither set — empty list. Callers fail closed.

    Default-deny: returning [] means `_validate_ingestion_path` rejects every
    path, including absolute ones. This closes the prior "admin can ingest
    anywhere on the host" hole without making the env var newly required for
    setups that have always relied on `INGESTION_PATH`.
    """
    explicit = os.getenv("SKUEL_INGESTION_ALLOWED_PATHS")
    if explicit:
        return [Path(p.strip()).resolve() for p in explicit.split(":") if p.strip()]

    fallback = os.getenv("INGESTION_PATH")
    if fallback:
        return [Path(fallback).resolve()]

    return []


def _reject_symlink_file(path_str: str | None) -> Result[None]:
    """Reject a symlinked file path before it is resolved.

    ``_validate_ingestion_path`` resolves symlinks (for traversal protection),
    which erases the symlink-ness the vault boundary relies on — so the service's
    ``is_ingestible_path`` no-symlink rule can't see it on the ``/api/ingest/file``
    door. The single-file door reads the target's content, so a symlink there
    could ship an external file into the graph; reject it on the ORIGINAL path.
    (Directory scans are unaffected: ``collect_files`` globs leaf symlinks without
    resolving them, so the service check still fires per-file there.)
    """
    if path_str and Path(path_str).is_symlink():
        return Result.fail(
            Errors.validation(
                "Symlinked files are not ingestible — the link target may be outside the vault.",
                "file_path",
                path_str,
            )
        )
    return Result.ok(None)


def _validate_ingestion_path(path_str: str | None) -> Result[Path]:
    """
    Validate a path for ingestion, checking for traversal attacks.

    Default-deny: every request path must resolve under at least one root from
    `_resolve_allowed_ingestion_roots()`. If neither env var configures a root,
    every request is rejected (fail closed). The earlier behavior of "allow any
    absolute path when env var unset" is gone — `INGESTION_PATH` (which already
    has the documented default vault) is the natural fallback.

    Args:
        path_str: The path string from the request

    Returns:
        Result[Path]: Resolved Path on success, validation error on failure
    """
    if not path_str:
        return Result.fail(Errors.validation("Path is required", "path", None))

    try:
        # Resolve to absolute path (handles .. and symlinks)
        resolved = Path(path_str).resolve()

        allowed_paths = _resolve_allowed_ingestion_roots()
        if not allowed_paths:
            logger.error(
                "Ingestion blocked: no allowlist configured. "
                "Set SKUEL_INGESTION_ALLOWED_PATHS or INGESTION_PATH."
            )
            return Result.fail(
                Errors.validation(
                    "Ingestion path allowlist is not configured. "
                    "Set SKUEL_INGESTION_ALLOWED_PATHS or INGESTION_PATH.",
                    "path",
                    path_str,
                )
            )

        is_allowed = any(
            resolved == allowed or resolved.is_relative_to(allowed) for allowed in allowed_paths
        )
        if not is_allowed:
            logger.warning(f"Path traversal attempt blocked: {path_str} -> {resolved}")
            return Result.fail(
                Errors.validation(
                    f"Path outside allowed directories: {resolved}",
                    "path",
                    path_str,
                )
            )

        return Result.ok(resolved)

    except (ValueError, OSError) as e:
        return Result.fail(Errors.validation(f"Invalid path: {e}", "path", path_str))


def create_ingestion_api_routes(
    app,
    rt,
    unified_ingestion: "IngestionOperations",
    user_service=None,
    graph_auth=None,
    batch_chunking_service: "BatchChunkingService | None" = None,
):
    """
    Create unified ingestion API routes.

    Args:
        app: FastHTML app instance
        rt: Router instance
        unified_ingestion: The UnifiedIngestionService instance
        user_service: UserService instance for admin role checks
        graph_auth: GraphAuthService for WebSocket graph-session validation
        batch_chunking_service: Phase 2 admin tool for chunk regeneration.
            When None, the /api/chunks/regenerate route is not registered.

    Returns:
        List of created routes
    """
    routes: list[Any] = []

    if not unified_ingestion:
        logger.error("UnifiedIngestionService not provided to ingestion API routes")
        return routes

    get_user_service = make_service_getter(user_service)

    # ============================================================================
    # API ROUTES
    # ============================================================================

    @rt("/api/ingest/file", methods=["POST"])
    @csrf_protected
    @require_admin(get_user_service)
    @boundary_handler()
    async def ingest_file_route(request: Request, current_user):
        """
        Ingest a single file (MD or YAML) into Neo4j.

        Request body:
            file_path: str - Path to file to ingest

        Returns:
            Result with uid, title, entity_type, and statistics

        Ownership: ``current_user.uid`` is passed as an acting-user hint only; the
        owner is resolved from the vault descriptor for ``file_path`` (ADR-070).

        Security: Path validated against SKUEL_INGESTION_ALLOWED_PATHS if set
        """
        try:
            data = await request.json()
            file_path = data.get("file_path")

            # Reject symlinks on the ORIGINAL path — validation below resolves them
            # away, bypassing the service's vault symlink boundary.
            symlink_check = _reject_symlink_file(file_path)
            if symlink_check.is_error:
                return Result.fail(symlink_check)

            # Validate path (traversal protection)
            path_result = _validate_ingestion_path(file_path)
            if path_result.is_error:
                return path_result

            path = path_result.value
            if not path.exists():
                return Result.fail(Errors.not_found("File", str(path)))

            result = await unified_ingestion.ingest_file(path, user_uid=current_user.uid)

            if result.is_ok:
                return Result.ok({"success": True, **result.value})
            else:
                return Result.fail(result)

        except Exception as e:  # safety-net: HTTP error boundary
            logger.error(f"File ingestion failed: {e}")
            return Result.fail(
                Errors.system("File ingestion failed", exception=e, operation="ingest_file")
            )

    # NOTE: the raw ``POST /api/ingest/directory`` admin door was removed
    # (ADR-070 Decision 9). Arbitrary-path directory ingestion is unified onto the
    # reconciler: content-vault sync now goes through ``POST /api/vault/sync/content``
    # (see ``adapters/inbound/vault_routes.py``) or the in-process
    # ``scripts/vault_bridge_sync.py --vault content``.

    @rt("/api/ingest/vault", methods=["POST"])
    @csrf_protected
    @require_admin(get_user_service)
    @boundary_handler()
    async def ingest_vault_route(request: Request, current_user):
        """
        Ingest an Obsidian vault or specific subdirectories.

        Request body:
            vault_path: str - Root path of vault
            subdirs: list[str] - Optional subdirectories to ingest

        Returns:
            Result with aggregated IngestionStats

        Ownership: ``current_user.uid`` is an acting-user hint; each ingested file's
        owner is resolved from the vault descriptor for its path (ADR-070).

        Security: Path validated against SKUEL_INGESTION_ALLOWED_PATHS if set
        """
        try:
            data = await request.json()
            vault_path = data.get("vault_path")
            subdirs = data.get("subdirs")

            # Validate path (traversal protection)
            path_result = _validate_ingestion_path(vault_path)
            if path_result.is_error:
                return path_result

            path = path_result.value
            if not path.exists() or not path.is_dir():
                return Result.fail(Errors.not_found("Vault", str(path)))

            result = await unified_ingestion.ingest_vault(
                path, subdirs=subdirs, user_uid=current_user.uid
            )

            if result.is_ok:
                stats = result.value
                return Result.ok(
                    {
                        "success": True,
                        "total_files": stats.total_files,
                        "successful": stats.successful,
                        "failed": stats.failed,
                        "nodes_created": stats.nodes_created,
                        "nodes_updated": stats.nodes_updated,
                        "relationships_created": stats.relationships_created,
                        "duration_seconds": stats.duration_seconds,
                        "files_per_second": stats.files_per_second,
                        "errors": stats.errors or [],
                    }
                )
            else:
                return Result.fail(result)

        except Exception as e:  # safety-net: HTTP error boundary
            logger.error(f"Vault ingestion failed: {e}")
            return Result.fail(
                Errors.system("Vault ingestion failed", exception=e, operation="ingest_vault")
            )

    @rt("/api/ingest/bundle", methods=["POST"])
    @csrf_protected
    @require_admin(get_user_service)
    @boundary_handler()
    async def ingest_bundle_route(request: Request, current_user):
        """
        Ingest a domain bundle with manifest.

        Request body:
            bundle_path: str - Path to bundle directory

        Returns:
            Result with BundleStats

        Ownership: ``current_user.uid`` is an acting-user hint; each ingested file's
        owner is resolved from the vault descriptor for its path (ADR-070).

        Security: Path validated against SKUEL_INGESTION_ALLOWED_PATHS if set
        """
        try:
            data = await request.json()
            bundle_path = data.get("bundle_path")

            # Validate path (traversal protection)
            path_result = _validate_ingestion_path(bundle_path)
            if path_result.is_error:
                return path_result

            path = path_result.value
            if not path.exists() or not path.is_dir():
                return Result.fail(Errors.not_found("Bundle", str(path)))

            manifest_path = path / "manifest.yaml"
            if not manifest_path.exists():
                return Result.fail(
                    Errors.validation(
                        "Bundle must contain manifest.yaml",
                        "bundle_path",
                        bundle_path,
                    )
                )

            result = await unified_ingestion.ingest_bundle(path, user_uid=current_user.uid)

            if result.is_ok:
                stats = result.value
                return Result.ok(
                    {
                        "success": True,
                        "bundle_name": stats.bundle_name,
                        "total_attempted": stats.total_attempted,
                        "total_successful": stats.total_successful,
                        "total_failed": stats.total_failed,
                        "entities_created": stats.entities_created or [],
                        "errors": stats.errors or [],
                    }
                )
            else:
                return Result.fail(result)

        except Exception as e:  # safety-net: HTTP error boundary
            logger.error(f"Bundle ingestion failed: {e}")
            return Result.fail(
                Errors.system("Bundle ingestion failed", exception=e, operation="ingest_bundle")
            )

    # Domain-specific ingestion endpoint
    @rt("/api/ingest/domain/{domain_name}", methods=["POST"])
    @csrf_protected
    @require_admin(get_user_service)
    @boundary_handler(success_status=200)
    async def domain_ingest(request: Request, domain_name: str, current_user):
        """
        Domain-specific ingestion endpoint.

        Request form:
            source_path: str - Path to directory to ingest
            pattern: str - File pattern (default: "*.md")
            dry_run: str - "true" for preview mode

        Returns:
            Result with DryRunPreview or IngestionStats
        """
        try:
            form_data = await request.form()
            # form_data.get() returns `UploadFile | str | None` — narrow to str.
            # File uploads in these fields are user error (not supported).
            source_path_raw = form_data.get("source_path")
            pattern_raw = form_data.get("pattern", "*.md")
            source_path_str = source_path_raw if isinstance(source_path_raw, str) else None
            pattern = pattern_raw if isinstance(pattern_raw, str) else "*.md"
            dry_run = form_data.get("dry_run") == "true"

            # Validate path
            path_result = _validate_ingestion_path(source_path_str)
            if path_result.is_error:
                return path_result

            source_path = path_result.value
            if not source_path.exists() or not source_path.is_dir():
                return Result.fail(Errors.not_found("Directory", str(source_path)))

            # Validate the domain string. This door does NOT filter files by
            # EntityType — it ingests every file in the directory and lets each
            # file's declared `type:` drive its persistence. The domain name is a
            # human-facing label for the target directory, not a filter.
            valid_domains = frozenset(
                {
                    "lesson",
                    "article",
                    "ku",
                    "ps",
                    "lp",
                    "tasks",
                    "goals",
                    "habits",
                    "events",
                    "choices",
                    "principles",
                }
            )
            if domain_name not in valid_domains:
                return Result.fail(Errors.validation(f"Unknown domain: {domain_name}"))

            result = await unified_ingestion.ingest_directory(
                source_path,
                pattern=pattern,
                dry_run=dry_run,
                user_uid=current_user.uid,
            )

            if result.is_error:
                return Result.fail(result)

            # Return appropriate component based on mode
            if dry_run:
                from ui.patterns.ingestion_preview import DryRunPreviewComponent

                preview = result.value
                return Result.ok(DryRunPreviewComponent(preview, operation_id=None))
            else:
                from ui.patterns.ingestion_results import IngestionResultsSummary

                stats = result.value
                return Result.ok(IngestionResultsSummary(stats))

        except Exception as e:  # safety-net: HTTP error boundary
            logger.error(f"Domain ingestion failed for {domain_name}: {e}")
            return Result.fail(
                Errors.system(
                    f"Domain ingestion failed for {domain_name}",
                    exception=e,
                    operation="domain_ingest",
                )
            )

    # Chunk regeneration — admin tool, only registered when service is wired.
    # In CORE tier the service exists but publishes no embedding events.
    chunk_routes: list[Any] = []
    if batch_chunking_service is not None:

        @rt("/api/chunks/regenerate", methods=["POST"])
        @csrf_protected
        @require_admin(get_user_service)
        @boundary_handler()
        async def regenerate_chunks_route(request: Request, current_user):
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

        chunk_routes.append(regenerate_chunks_route)

    # WebSocket route for real-time progress
    @rt("/ws/ingest/progress/{operation_id}")
    async def ingestion_progress_websocket(ws: WebSocket, operation_id: str):
        """
        WebSocket for real-time ingestion progress updates.

        Security: Requires admin session. Closes with 4003 if unauthorized.

        Clients connect with the operation_id and receive JSON progress updates:
        {
            "current": 100,
            "total": 1000,
            "percentage": 10.0,
            "current_file": "/path/to/file.md",
            "eta_seconds": 90
        }
        """
        # Auth check before accepting — ingestion is admin-only. Validates
        # the graph session (revoked cookies can't open a socket) and
        # re-fetches role from Neo4j (does NOT trust session is_admin flag).
        from adapters.inbound.auth import require_websocket_admin

        user_uid = await require_websocket_admin(ws, user_service, graph_auth)
        if not user_uid:
            return

        await ws.accept()
        logger.info(f"WebSocket connected for operation: {operation_id}")

        # Store connection
        _active_connections[operation_id] = ws

        try:
            # Keep connection alive
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected for operation: {operation_id}")
            # Remove connection
            _active_connections.pop(operation_id, None)
        except Exception as e:  # safety-net: WebSocket cleanup on unexpected error
            logger.error(f"WebSocket error for operation {operation_id}: {e}")
            # Remove connection
            _active_connections.pop(operation_id, None)

    # Collect all routes
    routes.extend(
        [
            ingest_file_route,
            ingest_vault_route,
            ingest_bundle_route,
            domain_ingest,
            *chunk_routes,
            ingestion_progress_websocket,
        ]
    )

    logger.info(f"Ingestion API routes registered: {len(routes)} endpoints")
    return routes


__all__ = ["create_ingestion_api_routes"]
