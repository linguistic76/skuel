"""
Ingestion UI Routes - Ingestion Dashboard
==========================================

UI dashboard for the UnifiedIngestionService.

Security:
- Dashboard requires admin role
"""


from fasthtml.common import H1, H2, Form, NotStr, P, Pre
from starlette.requests import Request

from core.auth import require_admin
from core.ui.daisy_components import Button, Card, CardBody, Container, Div, Input, Label
from core.utils.logging import get_logger
from ui.layouts.navbar import create_navbar

logger = get_logger("skuel.routes.ingestion_ui")


def create_ingestion_ui_routes(
    app,
    rt,
    unified_ingestion,
    user_service=None,
):
    """
    Create ingestion UI routes (admin dashboard).

    Args:
        app: FastHTML app instance
        rt: Router instance
        unified_ingestion: The UnifiedIngestionService instance
        user_service: UserService instance for admin role checks

    Returns:
        List of created routes
    """
    routes = []

    # Named function for require_admin decorator (SKUEL012 compliance)
    def get_user_service():
        """Get user service for admin role checks."""
        return user_service

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

    # Collect all routes
    routes.extend([ingest_dashboard])

    logger.info(f"Ingestion UI routes registered: {len(routes)} endpoints")
    return routes


__all__ = ["create_ingestion_ui_routes"]
