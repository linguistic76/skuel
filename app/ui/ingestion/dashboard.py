"""Ingestion dashboard UI components.

Renders the admin ingestion dashboard: file/directory ingestion cards
with results display and JavaScript handlers.
"""

from typing import Any

from fasthtml.common import Div, Form, NotStr, P, Pre

from core.config.settings import get_settings
from ui.components import Button, ButtonT, Card, CardBody
from ui.forms import LabelCheckbox, LabelInput, LabelTextArea
from ui.patterns import PageHeader, SectionHeader


def _get_default_vault_path() -> str:
    """Get default ingestion path from configuration."""
    return str(get_settings().vault.ingestion_path)


def _form_group(
    label_text: str, input_id: str, placeholder: str, input_type: str = "text", value: str = ""
) -> Any:
    """Build a consistent form group."""
    kwargs: dict[str, Any] = {
        "type": input_type,
        "name": input_id,
        "id": input_id,
        "placeholder": placeholder,
    }
    if value:
        kwargs["value"] = value
    return LabelInput(label_text, cls="space-y-2 w-full", **kwargs)


def _ingestion_card(
    title: str, description: str, form_groups: list, button_text: str, onclick: str
) -> Any:
    """Build a consistent ingestion action card."""
    return Card(
        CardBody(
            SectionHeader(title),
            P(description, cls="text-muted-foreground -mt-4 mb-4"),
            Form(
                *form_groups,
                Div(
                    Button(
                        button_text,
                        type="button",
                        cls=ButtonT.primary,
                        onclick=onclick,
                    ),
                    cls="mt-2",
                ),
                cls="space-y-4",
            ),
        ),
        cls="bg-background shadow-sm border border-border",
    )


_INGESTION_SCRIPT = """
<script>
let _ingesting = false;

function showResult(result, isError) {
    const statusEl = document.getElementById('ingest-status');
    const detailsCard = document.getElementById('ingest-details-card');
    const detailsEl = document.getElementById('ingest-results');

    if (isError) {
        const msg = result.error || result.message || 'Ingestion failed';
        statusEl.innerHTML = `
            <div class="p-4 rounded-lg bg-red-50 text-red-800 border border-red-200">
                <uk-icon icon="x" width="24" height="24" class="shrink-0 h-6 w-6"></uk-icon>
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
            <div class="p-4 rounded-lg bg-green-50 text-green-800 border border-green-200">
                <uk-icon icon="check" width="24" height="24" class="shrink-0 h-6 w-6"></uk-icon>
                <div>
                    <span class="font-semibold">Ingested successfully</span>
                    <span class="text-sm opacity-80 ml-2">${summary}</span>
                </div>
            </div>`;
    }

    detailsEl.textContent = JSON.stringify(result, null, 2);
    detailsEl.classList.remove('text-muted-foreground', 'text-success', 'text-error');
    detailsEl.classList.add(isError ? 'text-error' : 'text-success');
    detailsCard.classList.remove('hidden');
    statusEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function showLoading(btnEl) {
    _ingesting = true;
    const statusEl = document.getElementById('ingest-status');
    statusEl.innerHTML = `
        <div class="alert shadow-sm">
            <span class="animate-spin text-muted-foreground"></span>
            <span>Ingesting...</span>
        </div>`;
    document.getElementById('ingest-details-card').classList.add('hidden');
    if (btnEl) {
        btnEl.disabled = true;
        btnEl.classList.add('opacity-50', 'pointer-events-none');
    }
}

function doneLoading(btnEl) {
    _ingesting = false;
    if (btnEl) {
        btnEl.disabled = false;
        btnEl.classList.remove('opacity-50', 'pointer-events-none');
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

function showRegenResult(result, isError) {
    const statusEl = document.getElementById('ingest-status');
    const detailsCard = document.getElementById('ingest-details-card');
    const detailsEl = document.getElementById('ingest-results');

    if (isError) {
        const msg = (result && result.error && result.error.message)
            || result.message || result.error || 'Regeneration failed';
        statusEl.innerHTML = `
            <div class="p-4 rounded-lg bg-red-50 text-red-800 border border-red-200">
                <uk-icon icon="x" width="24" height="24" class="shrink-0 h-6 w-6"></uk-icon>
                <span class="font-semibold">${msg}</span>
            </div>`;
    } else {
        const succeeded = result.succeeded ?? 0;
        const processed = result.processed ?? 0;
        const failed = result.failed ?? 0;
        const skippedCurrent = result.skipped_already_current ?? 0;
        const skippedNoBody = result.skipped_no_body ?? 0;
        const duration = result.duration_seconds ?? 0;
        const summary = `${succeeded}/${processed} succeeded &middot; ${failed} failed &middot; ${skippedCurrent} already-current &middot; ${skippedNoBody} no-body &middot; ${duration}s`;
        statusEl.innerHTML = `
            <div class="p-4 rounded-lg bg-green-50 text-green-800 border border-green-200">
                <uk-icon icon="check" width="24" height="24" class="shrink-0 h-6 w-6"></uk-icon>
                <div>
                    <span class="font-semibold">Chunks regenerated</span>
                    <span class="text-sm opacity-80 ml-2">${summary}</span>
                </div>
            </div>`;
    }
    detailsEl.textContent = JSON.stringify(result, null, 2);
    detailsEl.classList.remove('text-muted-foreground', 'text-success', 'text-error');
    detailsEl.classList.add(isError ? 'text-error' : 'text-success');
    detailsCard.classList.remove('hidden');
    statusEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

async function regenerateChunks() {
    if (_ingesting) return;
    const btn = event.currentTarget;
    const raw = (document.getElementById('chunks_parent_uids').value || '').trim();
    const force = document.getElementById('chunks_force').checked;
    const parent_uids = raw
        ? raw.split(/[\\s,]+/).map(s => s.trim()).filter(Boolean)
        : null;
    showLoading(btn);
    try {
        const headers = {'Content-Type': 'application/json'};
        const csrfMatch = document.cookie.match(/(?:^|; )csrf_token=([^;]+)/);
        if (csrfMatch) headers['X-CSRF-Token'] = decodeURIComponent(csrfMatch[1]);
        const resp = await fetch('/api/chunks/regenerate', {
            method: 'POST',
            headers: headers,
            body: JSON.stringify({parent_uids: parent_uids, force: force})
        });
        const text = await resp.text();
        try {
            const data = JSON.parse(text);
            showRegenResult(data, !resp.ok);
        } catch (_) {
            showRegenResult({error: 'Non-JSON response', status: resp.status, body: text.substring(0, 500)}, true);
        }
    } catch (e) {
        showRegenResult({error: e.message}, true);
    } finally {
        doneLoading(btn);
    }
}
</script>
"""


def build_ingestion_dashboard() -> Any:
    """Build the full ingestion dashboard content."""
    vault_path = _get_default_vault_path()

    regen_form_groups = [
        LabelTextArea(
            "Parent UIDs (optional)",
            name="chunks_parent_uids",
            id="chunks_parent_uids",
            placeholder="Comma- or whitespace-separated. Leave blank for all :Content nodes.",
            rows=3,
            cls="space-y-2 w-full",
        ),
        LabelCheckbox(
            "Force (regenerate even when chunks match current version)",
            name="chunks_force",
            id="chunks_force",
        ),
    ]

    return Div(
        PageHeader(
            "Content Ingestion",
            subtitle="Ingest markdown and YAML content into Neo4j.",
        ),
        Div(
            _ingestion_card(
                title="Ingest File",
                description="Ingest a single .md or .yaml file.",
                form_groups=[
                    _form_group(
                        "File Path",
                        "file_path",
                        "e.g. file.md or file.yaml",
                        value=vault_path + "/",
                    ),
                ],
                button_text="Ingest File",
                onclick="ingestFile()",
            ),
            _ingestion_card(
                title="Ingest Directory",
                description="Ingest all matching files in a directory.",
                form_groups=[
                    _form_group(
                        "Directory Path",
                        "directory",
                        "Directory to ingest",
                        value=vault_path,
                    ),
                    _form_group("Pattern (optional)", "pattern", "* for all files", value="*"),
                ],
                button_text="Ingest Directory",
                onclick="ingestDirectory()",
            ),
            _ingestion_card(
                title="Regenerate Chunks",
                description=(
                    "Re-chunk existing :Content nodes. Use after a "
                    "CHUNKING_ALGORITHM_VERSION bump or when chunks drift. "
                    "Idempotent: stale chunks are replaced, not duplicated."
                ),
                form_groups=regen_form_groups,
                button_text="Regenerate",
                onclick="regenerateChunks()",
            ),
            cls="grid gap-6 lg:grid-cols-2",
        ),
        Div(id="ingest-status", cls="mt-6"),
        Card(
            CardBody(
                Div(
                    SectionHeader("Details"),
                    Pre(
                        "",
                        id="ingest-results",
                        cls="bg-muted p-4 rounded-lg text-sm font-mono whitespace-pre-wrap text-muted-foreground",
                    ),
                ),
            ),
            id="ingest-details-card",
            cls="bg-background shadow-sm border border-border mt-3 hidden",
        ),
        NotStr(_INGESTION_SCRIPT),
    )
