"""
Ingestion Routes - Unified Content Ingestion API
=================================================

API and UI routes for the UnifiedIngestionService (ADR-014).
Handles both MD and YAML formats for all 14 entity types.

Security:
- All routes require admin role
- Path traversal validation via SKUEL_INGESTION_ALLOWED_PATHS env var
- If env var not set, any absolute path is allowed (admin-only anyway)

Routes:
- /api/ingest/file - Ingest single file (MD or YAML)
- /api/ingest/directory - Ingest directory with pattern
- /api/ingest/vault - Sync Obsidian vault
- /api/ingest/bundle - Ingest domain bundle with manifest
- /ingest - Dashboard UI for ingestion operations
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


def create_ingestion_routes(
    _app, rt, unified_ingestion: "UnifiedIngestionService", user_service=None
):
    """
    Create unified ingestion routes.

    Args:
        _app: FastHTML app instance
        rt: Router instance
        unified_ingestion: The UnifiedIngestionService instance
        user_service: UserService instance for admin role checks
    """

    if not unified_ingestion:
        logger.error("UnifiedIngestionService not provided to ingestion routes")
        return

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

    # ============================================================================
    # UI ROUTE
    # ============================================================================

    @rt("/ingest")
    @require_admin(get_user_service)
    def ingest_dashboard(request: Request, current_user):
        """Unified ingestion dashboard UI. Requires ADMIN role."""
        user_uid = current_user.uid if current_user else None
        navbar = create_navbar(current_user=user_uid, is_authenticated=True, is_admin=True)

        return Div(
            navbar,
            Container(
                H1("Unified Content Ingestion", cls="text-2xl font-bold mt-4"),
                P(
                    "Ingest markdown and YAML content into Neo4j. Supports all 14 entity types.",
                    cls="text-lg text-gray-500 mb-4",
                ),
                # Single File Ingestion
                Card(
                    CardBody(
                        H2("Ingest File", cls="text-xl font-semibold"),
                        P("Ingest a single .md or .yaml file", cls="text-gray-500"),
                        Form(
                            Div(
                                Label("File Path", _for="file_path"),
                                Input(
                                    type="text",
                                    name="file_path",
                                    id="file_path",
                                    placeholder="/path/to/file.md or /path/to/file.yaml",
                                    cls="input input-bordered w-full",
                                ),
                                cls="mb-4",
                            ),
                            Button(
                                "Ingest File",
                                type="button",
                                cls="btn btn-primary",
                                onclick="ingestFile()",
                            ),
                        ),
                    ),
                    cls="mb-4",
                ),
                # Directory Ingestion
                Card(
                    CardBody(
                        H2("Ingest Directory", cls="text-xl font-semibold"),
                        P("Ingest all .md and .yaml files in a directory", cls="text-gray-500"),
                        Form(
                            Div(
                                Label("Directory Path", _for="directory"),
                                Input(
                                    type="text",
                                    name="directory",
                                    id="directory",
                                    placeholder="/path/to/directory",
                                    cls="input input-bordered w-full",
                                ),
                                cls="mb-4",
                            ),
                            Div(
                                Label("Pattern (optional)", _for="pattern"),
                                Input(
                                    type="text",
                                    name="pattern",
                                    id="pattern",
                                    value="*",
                                    placeholder="* for all files",
                                    cls="input input-bordered w-full",
                                ),
                                cls="mb-4",
                            ),
                            Button(
                                "Ingest Directory",
                                type="button",
                                cls="btn btn-primary",
                                onclick="ingestDirectory()",
                            ),
                        ),
                    ),
                    cls="mb-4",
                ),
                # Vault Ingestion
                Card(
                    CardBody(
                        H2("Ingest Obsidian Vault", cls="text-xl font-semibold"),
                        P(
                            "Sync an entire Obsidian vault or specific subdirectories",
                            cls="text-gray-500",
                        ),
                        Form(
                            Div(
                                Label("Vault Path", _for="vault_path"),
                                Input(
                                    type="text",
                                    name="vault_path",
                                    id="vault_path",
                                    placeholder="/path/to/obsidian/vault",
                                    cls="input input-bordered w-full",
                                ),
                                cls="mb-4",
                            ),
                            Div(
                                Label("Subdirectories (comma-separated, optional)", _for="subdirs"),
                                Input(
                                    type="text",
                                    name="subdirs",
                                    id="subdirs",
                                    placeholder="docs, notes, curriculum",
                                    cls="input input-bordered w-full",
                                ),
                                cls="mb-4",
                            ),
                            Button(
                                "Ingest Vault",
                                type="button",
                                cls="btn btn-primary",
                                onclick="ingestVault()",
                            ),
                        ),
                    ),
                    cls="mb-4",
                ),
                # Bundle Ingestion
                Card(
                    CardBody(
                        H2("Ingest Domain Bundle", cls="text-xl font-semibold"),
                        P("Ingest a domain bundle with manifest.yaml", cls="text-gray-500"),
                        Form(
                            Div(
                                Label("Bundle Path", _for="bundle_path"),
                                Input(
                                    type="text",
                                    name="bundle_path",
                                    id="bundle_path",
                                    placeholder="/path/to/bundle",
                                    cls="input input-bordered w-full",
                                ),
                                cls="mb-4",
                            ),
                            Button(
                                "Ingest Bundle",
                                type="button",
                                cls="btn btn-primary",
                                onclick="ingestBundle()",
                            ),
                        ),
                    ),
                    cls="mb-4",
                ),
                # Results Display
                Card(
                    CardBody(
                        H2("Ingestion Results", cls="text-xl font-semibold"),
                        Pre(id="ingest-results", cls="mt-4"),
                    ),
                ),
                cls="container mx-auto mt-8 mb-8",
            ),
            # JavaScript for ingestion operations
            NotStr("""
            <script>
            function showResult(result) {
                document.getElementById('ingest-results').textContent =
                    JSON.stringify(result, null, 2);
            }

            async function ingestFile() {
                const filePath = document.getElementById('file_path').value;
                if (!filePath) {
                    showResult({error: 'File path is required'});
                    return;
                }
                try {
                    const response = await fetch('/api/ingest/file', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({file_path: filePath})
                    });
                    const result = await response.json();
                    showResult(result);
                } catch (e) {
                    showResult({error: e.message});
                }
            }

            async function ingestDirectory() {
                const directory = document.getElementById('directory').value;
                const pattern = document.getElementById('pattern').value || '*';
                if (!directory) {
                    showResult({error: 'Directory path is required'});
                    return;
                }
                try {
                    const response = await fetch('/api/ingest/directory', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({directory: directory, pattern: pattern})
                    });
                    const result = await response.json();
                    showResult(result);
                } catch (e) {
                    showResult({error: e.message});
                }
            }

            async function ingestVault() {
                const vaultPath = document.getElementById('vault_path').value;
                const subdirsStr = document.getElementById('subdirs').value;
                if (!vaultPath) {
                    showResult({error: 'Vault path is required'});
                    return;
                }
                const subdirs = subdirsStr
                    ? subdirsStr.split(',').map(s => s.trim()).filter(s => s)
                    : null;
                try {
                    const response = await fetch('/api/ingest/vault', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({vault_path: vaultPath, subdirs: subdirs})
                    });
                    const result = await response.json();
                    showResult(result);
                } catch (e) {
                    showResult({error: e.message});
                }
            }

            async function ingestBundle() {
                const bundlePath = document.getElementById('bundle_path').value;
                if (!bundlePath) {
                    showResult({error: 'Bundle path is required'});
                    return;
                }
                try {
                    const response = await fetch('/api/ingest/bundle', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({bundle_path: bundlePath})
                    });
                    const result = await response.json();
                    showResult(result);
                } catch (e) {
                    showResult({error: e.message});
                }
            }
            </script>
            """),
        )

    logger.info("Ingestion routes created - unified MD + YAML ingestion")


__all__ = ["create_ingestion_routes"]
