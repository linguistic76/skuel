"""
Ingestion UI Routes - Ingestion Dashboard
==========================================

UI dashboard for the UnifiedIngestionService.

Security:
- Dashboard requires admin role
"""

from fasthtml.common import Form, NotStr, P, Pre
from starlette.requests import Request

from core.auth import require_admin
from core.ui.daisy_components import Button, Card, CardBody, Div, Input, Label
from core.utils.logging import get_logger
from ui.layouts.base_page import BasePage
from ui.patterns import PageHeader, SectionHeader

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

    def _form_group(label_text: str, input_id: str, placeholder: str, input_type: str = "text", value: str = ""):
        """Build a consistent DaisyUI form group."""
        input_attrs = {
            "type": input_type,
            "name": input_id,
            "id": input_id,
            "placeholder": placeholder,
            "cls": "input input-bordered w-full",
        }
        if value:
            input_attrs["value"] = value
        return Div(
            Label(label_text, _for=input_id, cls="label"),
            Input(**input_attrs),
            cls="form-control w-full",
        )

    def _ingestion_card(title: str, description: str, form_groups: list, button_text: str, onclick: str):
        """Build a consistent ingestion action card."""
        return Card(
            CardBody(
                SectionHeader(title),
                P(description, cls="text-base-content/60 -mt-4 mb-4"),
                Form(
                    *form_groups,
                    Div(
                        Button(
                            button_text,
                            type="button",
                            cls="btn btn-primary",
                            onclick=onclick,
                        ),
                        cls="mt-2",
                    ),
                    cls="space-y-4",
                ),
            ),
            cls="bg-base-100 shadow-sm border border-base-200",
        )

    @rt("/ingest")
    @require_admin(get_user_service)
    async def ingest_dashboard(request: Request, current_user):
        """Unified ingestion dashboard UI. Requires ADMIN role."""
        content = Div(
            PageHeader(
                "Content Ingestion",
                subtitle="Ingest markdown and YAML content into Neo4j. Supports all 15 entity types.",
            ),
            Div(
                # Single File Ingestion
                _ingestion_card(
                    title="Ingest File",
                    description="Ingest a single .md or .yaml file.",
                    form_groups=[
                        _form_group("File Path", "file_path", "/path/to/file.md or /path/to/file.yaml"),
                    ],
                    button_text="Ingest File",
                    onclick="ingestFile()",
                ),
                # Directory Ingestion
                _ingestion_card(
                    title="Ingest Directory",
                    description="Ingest all .md and .yaml files in a directory.",
                    form_groups=[
                        _form_group("Directory Path", "directory", "/path/to/directory"),
                        _form_group("Pattern (optional)", "pattern", "* for all files", value="*"),
                    ],
                    button_text="Ingest Directory",
                    onclick="ingestDirectory()",
                ),
                # Vault Ingestion
                _ingestion_card(
                    title="Ingest Obsidian Vault",
                    description="Ingest an entire Obsidian vault or specific subdirectories.",
                    form_groups=[
                        _form_group("Vault Path", "vault_path", "/path/to/obsidian/vault"),
                        _form_group("Subdirectories (comma-separated, optional)", "subdirs", "docs, notes, curriculum"),
                    ],
                    button_text="Ingest Vault",
                    onclick="ingestVault()",
                ),
                # Bundle Ingestion
                _ingestion_card(
                    title="Ingest Domain Bundle",
                    description="Ingest a domain bundle with manifest.yaml.",
                    form_groups=[
                        _form_group("Bundle Path", "bundle_path", "/path/to/bundle"),
                    ],
                    button_text="Ingest Bundle",
                    onclick="ingestBundle()",
                ),
                cls="grid gap-6 lg:grid-cols-2",
            ),
            # Results Display
            Card(
                CardBody(
                    SectionHeader("Ingestion Results"),
                    Pre(
                        "Results will appear here after ingestion...",
                        id="ingest-results",
                        cls="bg-base-200 p-4 rounded-lg text-sm font-mono whitespace-pre-wrap min-h-[100px] text-base-content/70",
                    ),
                ),
                cls="bg-base-100 shadow-sm border border-base-200 mt-6",
            ),
            # JavaScript for ingestion operations
            NotStr("""
            <script>
            function showResult(result) {
                const el = document.getElementById('ingest-results');
                el.textContent = JSON.stringify(result, null, 2);
                el.classList.remove('text-base-content/70');
                el.classList.add('text-base-content');
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

        return await BasePage(
            content,
            title="Content Ingestion",
            request=request,
            active_page="ingest",
        )

    # Collect all routes
    routes.extend([ingest_dashboard])

    logger.info(f"Ingestion UI routes registered: {len(routes)} endpoints")
    return routes


__all__ = ["create_ingestion_ui_routes"]
