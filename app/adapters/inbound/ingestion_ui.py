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
from core.utils.logging import get_logger
from ui.daisy_components import Button, Card, CardBody, Div, Input, Label
from ui.layouts.base_page import BasePage
from ui.patterns import PageHeader, SectionHeader

logger = get_logger("skuel.routes.ingestion_ui")

# Default vault path for ingestion forms
DEFAULT_VAULT_PATH = "/home/mike/skuel/app/data/vault"


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

    def _form_group(
        label_text: str, input_id: str, placeholder: str, input_type: str = "text", value: str = ""
    ):
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

    def _ingestion_card(
        title: str, description: str, form_groups: list, button_text: str, onclick: str
    ):
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
                subtitle="Ingest markdown and YAML content into Neo4j.",
            ),
            Div(
                # Single File Ingestion
                _ingestion_card(
                    title="Ingest File",
                    description="Ingest a single .md or .yaml file.",
                    form_groups=[
                        _form_group(
                            "File Path",
                            "file_path",
                            "e.g. file.md or file.yaml",
                            value=DEFAULT_VAULT_PATH + "/",
                        ),
                    ],
                    button_text="Ingest File",
                    onclick="ingestFile()",
                ),
                # Directory Ingestion
                _ingestion_card(
                    title="Ingest Directory",
                    description="Ingest all matching files in a directory.",
                    form_groups=[
                        _form_group(
                            "Directory Path",
                            "directory",
                            "Directory to ingest",
                            value=DEFAULT_VAULT_PATH,
                        ),
                        _form_group("Pattern (optional)", "pattern", "* for all files", value="*"),
                    ],
                    button_text="Ingest Directory",
                    onclick="ingestDirectory()",
                ),
                cls="grid gap-6 lg:grid-cols-2",
            ),
            # Results Display
            Div(id="ingest-status", cls="mt-6"),
            Card(
                CardBody(
                    Div(
                        SectionHeader("Details"),
                        Pre(
                            "",
                            id="ingest-results",
                            cls="bg-base-200 p-4 rounded-lg text-sm font-mono whitespace-pre-wrap text-base-content/70",
                        ),
                    ),
                ),
                id="ingest-details-card",
                cls="bg-base-100 shadow-sm border border-base-200 mt-3 hidden",
            ),
            # JavaScript for ingestion operations
            NotStr("""
            <script>
            let _ingesting = false;

            function showResult(result, isError) {
                const statusEl = document.getElementById('ingest-status');
                const detailsCard = document.getElementById('ingest-details-card');
                const detailsEl = document.getElementById('ingest-results');

                if (isError) {
                    const msg = result.error || result.message || 'Ingestion failed';
                    statusEl.innerHTML = `
                        <div class="alert alert-error shadow-sm">
                            <svg xmlns="http://www.w3.org/2000/svg" class="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                            </svg>
                            <span class="font-semibold">${msg}</span>
                        </div>`;
                } else {
                    const title = result.title || result.uid || '';
                    const entityType = (result.entity_type || '').toUpperCase();
                    const nodes = (result.nodes_created || 0) + (result.nodes_updated || 0);
                    const rels = result.relationships_created || 0;
                    const chunks = result.chunks_generated ? ' &middot; Chunks generated' : '';
                    // Directory ingestion returns different fields
                    const totalFiles = result.total_files || 0;
                    const successful = result.successful || 0;
                    const failed = result.failed || 0;
                    const isDirectory = totalFiles > 0;

                    let summary;
                    if (isDirectory) {
                        summary = `${successful}/${totalFiles} files &middot; ${nodes} node(s), ${rels} relationship(s)`;
                        if (failed > 0) summary += ` &middot; ${failed} failed`;
                    } else {
                        summary = `${entityType}${title ? ' &middot; ' + title : ''} &middot; ${nodes} node(s), ${rels} relationship(s)${chunks}`;
                    }

                    statusEl.innerHTML = `
                        <div class="alert alert-success shadow-sm">
                            <svg xmlns="http://www.w3.org/2000/svg" class="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                            </svg>
                            <div>
                                <span class="font-semibold">Ingested successfully</span>
                                <span class="text-sm opacity-80 ml-2">${summary}</span>
                            </div>
                        </div>`;
                }

                detailsEl.textContent = JSON.stringify(result, null, 2);
                detailsEl.classList.remove('text-base-content/70', 'text-success', 'text-error');
                detailsEl.classList.add(isError ? 'text-error' : 'text-success');
                detailsCard.classList.remove('hidden');
                statusEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }

            function showLoading(btnEl) {
                _ingesting = true;
                const statusEl = document.getElementById('ingest-status');
                statusEl.innerHTML = `
                    <div class="alert shadow-sm">
                        <span class="loading loading-spinner loading-sm"></span>
                        <span>Ingesting...</span>
                    </div>`;
                document.getElementById('ingest-details-card').classList.add('hidden');
                if (btnEl) {
                    btnEl.disabled = true;
                    btnEl.classList.add('btn-disabled');
                }
            }

            function doneLoading(btnEl) {
                _ingesting = false;
                if (btnEl) {
                    btnEl.disabled = false;
                    btnEl.classList.remove('btn-disabled');
                }
            }

            async function ingestFile() {
                if (_ingesting) return;
                const btn = event.currentTarget;
                const filePath = document.getElementById('file_path').value;
                if (!filePath) { showResult({error: 'File path is required'}, true); return; }
                showLoading(btn);
                try {
                    const resp = await fetch('/api/ingest/file', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({file_path: filePath})
                    });
                    const text = await resp.text();
                    try {
                        const data = JSON.parse(text);
                        showResult(data, !resp.ok);
                    } catch (_) {
                        showResult({error: 'Non-JSON response', status: resp.status, body: text.substring(0, 500)}, true);
                    }
                } catch (e) {
                    showResult({error: e.message}, true);
                } finally {
                    doneLoading(btn);
                }
            }

            async function ingestDirectory() {
                if (_ingesting) return;
                const btn = event.currentTarget;
                const directory = document.getElementById('directory').value;
                const pattern = document.getElementById('pattern').value || '*';
                if (!directory) { showResult({error: 'Directory path is required'}, true); return; }
                showLoading(btn);
                try {
                    const resp = await fetch('/api/ingest/directory', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({directory: directory, pattern: pattern})
                    });
                    const text = await resp.text();
                    try {
                        const data = JSON.parse(text);
                        showResult(data, !resp.ok);
                    } catch (_) {
                        showResult({error: 'Non-JSON response', status: resp.status, body: text.substring(0, 500)}, true);
                    }
                } catch (e) {
                    showResult({error: e.message}, true);
                } finally {
                    doneLoading(btn);
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
