"""
Ingestion API Routes - Unified Content Ingestion API
=====================================================

API routes for the UnifiedIngestionService (ADR-014).
Handles both MD and YAML formats for all 14 entity types.

Security:
- All routes require admin role
- Path traversal validation via SKUEL_INGESTION_ALLOWED_PATHS env var
- If env var not set, any absolute path is allowed (admin-only anyway)

Routes:
- POST /api/ingest/file - Ingest single file (MD or YAML)
- POST /api/ingest/directory - Ingest directory with pattern
- POST /api/ingest/vault - Sync Obsidian vault
- POST /api/ingest/bundle - Ingest domain bundle with manifest
"""

import os
from pathlib import Path
from typing import TYPE_CHECKING

from fasthtml.common import H1, H2, Form, NotStr, P, Pre
from starlette.requests import Request

from core.auth import require_admin
from core.ui.daisy_components import Button, Card, CardBody, Container, Div, Input, Label
from core.utils.error_boundary import boundary_handler
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from ui.layouts.navbar import create_navbar

if TYPE_CHECKING:
    from core.services.ingestion import UnifiedIngestionService

logger = get_logger("skuel.routes.ingestion")


def _validate_ingestion_path(path_str: str) -> Result[Path]:
    """
    Validate a path for ingestion, checking for traversal attacks.

    Security:
    - Resolves path to absolute form
    - Checks against SKUEL_INGESTION_ALLOWED_PATHS if set (colon-separated list)
    - If env var not set, allows any absolute path (admin-only routes)

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

        # Check against allowed paths if configured
        allowed_paths_str = os.getenv("SKUEL_INGESTION_ALLOWED_PATHS")
        if allowed_paths_str:
            allowed_paths = [
                Path(p.strip()).resolve() for p in allowed_paths_str.split(":") if p.strip()
            ]
            is_allowed = any(
                resolved == allowed or resolved.is_relative_to(allowed) for allowed in allowed_paths
            )
            if not is_allowed:
                logger.warning(f"Path traversal attempt blocked: {path_str} -> {resolved}")
                return Result.fail(
                    Errors.validation(
                        f"Path outside allowed directories. Allowed: {allowed_paths_str}",
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
    unified_ingestion: "UnifiedIngestionService",
    user_service=None,
):
    """
    Create unified ingestion API routes.

    Args:
        app: FastHTML app instance
        rt: Router instance
        unified_ingestion: The UnifiedIngestionService instance
        user_service: UserService instance for admin role checks

    Returns:
        List of created routes
    """
    routes = []

    if not unified_ingestion:
        logger.error("UnifiedIngestionService not provided to ingestion API routes")
        return routes

    def get_user_service():
        """Get user service for admin role checks."""
        if user_service is None:
            raise ValueError("User service required for admin-protected routes")
        return user_service

    # ============================================================================
    # API ROUTES
    # ============================================================================

    @rt("/api/ingest/file", methods=["POST"])
    @require_admin(get_user_service)
    @boundary_handler()
    async def ingest_file_route(request: Request, current_user):
        """
        Ingest a single file (MD or YAML) into Neo4j.

        Request body:
            file_path: str - Path to file to ingest

        Returns:
            Result with uid, title, entity_type, and statistics

        Security: Path validated against SKUEL_INGESTION_ALLOWED_PATHS if set
        """
        try:
            data = await request.json()
            file_path = data.get("file_path")

            # Validate path (traversal protection)
            path_result = _validate_ingestion_path(file_path)
            if path_result.is_error:
                return path_result

            path = path_result.value
            if not path.exists():
                return Result.fail(Errors.not_found("File", str(path)))

            result = await unified_ingestion.ingest_file(path)

            if result.is_ok:
                return Result.ok({"success": True, **result.value})
            else:
                return Result.fail(result.expect_error())

        except Exception as e:
            logger.error(f"File ingestion failed: {e}")
            return Result.fail(
                Errors.system("File ingestion failed", exception=e, operation="ingest_file")
            )

    @rt("/api/ingest/directory", methods=["POST"])
    @require_admin(get_user_service)
    @boundary_handler()
    async def ingest_directory_route(request: Request, current_user):
        """
        Ingest all supported files in a directory.

        Request body:
            directory: str - Path to directory
            pattern: str - Glob pattern (default: "*")
            batch_size: int - Batch size for bulk ops (default: 500)

        Returns:
            Result with IngestionStats

        Security: Path validated against SKUEL_INGESTION_ALLOWED_PATHS if set
        """
        try:
            data = await request.json()
            directory = data.get("directory")
            pattern = data.get("pattern", "*")
            batch_size = data.get("batch_size", 500)

            # Validate path (traversal protection)
            path_result = _validate_ingestion_path(directory)
            if path_result.is_error:
                return path_result

            dir_path = path_result.value
            if not dir_path.exists() or not dir_path.is_dir():
                return Result.fail(Errors.not_found("Directory", str(dir_path)))

            result = await unified_ingestion.ingest_directory(
                dir_path, pattern=pattern, batch_size=batch_size
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
                return Result.fail(result.expect_error())

        except Exception as e:
            logger.error(f"Directory ingestion failed: {e}")
            return Result.fail(
                Errors.system(
                    "Directory ingestion failed", exception=e, operation="ingest_directory"
                )
            )

    @rt("/api/ingest/vault", methods=["POST"])
    @require_admin(get_user_service)
    @boundary_handler()
    async def ingest_vault_route(request: Request, current_user):
        """
        Ingest an Obsidian vault or specific subdirectories.

        Request body:
            vault_path: str - Root path of vault
            subdirs: list[str] - Optional subdirectories to sync

        Returns:
            Result with aggregated IngestionStats

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

            result = await unified_ingestion.ingest_vault(path, subdirs=subdirs)

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
                return Result.fail(result.expect_error())

        except Exception as e:
            logger.error(f"Vault ingestion failed: {e}")
            return Result.fail(
                Errors.system("Vault ingestion failed", exception=e, operation="ingest_vault")
            )

    @rt("/api/ingest/bundle", methods=["POST"])
    @require_admin(get_user_service)
    @boundary_handler()
    async def ingest_bundle_route(request: Request, current_user):
        """
        Ingest a domain bundle with manifest.

        Request body:
            bundle_path: str - Path to bundle directory

        Returns:
            Result with BundleStats

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

            result = await unified_ingestion.ingest_bundle(path)

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
                return Result.fail(result.expect_error())

        except Exception as e:
            logger.error(f"Bundle ingestion failed: {e}")
            return Result.fail(
                Errors.system("Bundle ingestion failed", exception=e, operation="ingest_bundle")
            )

    # Collect all routes
    routes.extend([
        ingest_file_route,
        ingest_directory_route,
        ingest_vault_route,
        ingest_bundle_route,
    ])

    logger.info(f"Ingestion API routes registered: {len(routes)} endpoints")
    return routes


__all__ = ["create_ingestion_api_routes"]
