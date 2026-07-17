"""Ingestion dashboard UI components.

Renders the admin ingestion dashboard: file/directory ingestion cards
with results display and JavaScript handlers.
"""

from typing import Any

from fasthtml.common import Div, Form, NotStr, P, Pre

from ui.components import Button, ButtonT, Card, CardBody, Icon
from ui.forms import LabelCheckbox, LabelInput, LabelTextArea
from ui.patterns import PageHeader, SectionHeader


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
                __ICON_X__
                <span class="font-semibold">${msg}</span>
            </div>`;
    } else {
        const title = result.title || result.uid || '';
        const entityType = (result.entity_type || '').toUpperCase();
        const nodes = (result.nodes_created || 0) + (result.nodes_updated || 0);
        const rels = result.relationships_created || 0;
        const chunks = result.chunks_generated ? ' &middot; Chunks generated' : '';
        const summary = `${entityType}${title ? ' &middot; ' + title : ''} &middot; ${nodes} node(s), ${rels} relationship(s)${chunks}`;

        statusEl.innerHTML = `
            <div class="p-4 rounded-lg bg-green-50 text-green-800 border border-green-200">
                __ICON_CHECK__
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
        <div class="flex items-center gap-3 rounded-lg border border-base-300 bg-base-200 p-4 text-sm shadow-sm">
            <span class="inline-block animate-spin rounded-full border-2 border-current border-t-transparent w-4 h-4 text-muted-foreground"></span>
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

// Content-vault sync (ADR-070 Decision 9) — the single directory-ingest path.
// Replaces the retired arbitrary-path /api/ingest/directory door; the reconciler
// ingests the fixed content vault (INGESTION_PATH), inbound-only.
async function syncContentVault() {
    if (_ingesting) return;
    const btn = event.currentTarget;
    showLoading(btn);
    try {
        const headers = {'Content-Type': 'application/json'};
        const csrfMatch = document.cookie.match(/(?:^|; )csrf_token=([^;]+)/);
        if (csrfMatch) headers['X-CSRF-Token'] = decodeURIComponent(csrfMatch[1]);
        const resp = await fetch('/api/vault/sync/content', {
            method: 'POST',
            headers: headers,
            body: JSON.stringify({})
        });
        const text = await resp.text();
        try {
            const data = JSON.parse(text);
            showSyncResult(data, !resp.ok);
        } catch (_) {
            showSyncResult({error: 'Non-JSON response', status: resp.status, body: text.substring(0, 500)}, true);
        }
    } catch (e) {
        showSyncResult({error: e.message}, true);
    } finally {
        doneLoading(btn);
    }
}

function showSyncResult(result, isError) {
    const statusEl = document.getElementById('ingest-status');
    const detailsCard = document.getElementById('ingest-details-card');
    const detailsEl = document.getElementById('ingest-results');

    if (isError) {
        const msg = (result && result.error && result.error.message)
            || result.message || result.error || 'Content vault sync failed';
        statusEl.innerHTML = `
            <div class="p-4 rounded-lg bg-red-50 text-red-800 border border-red-200">
                __ICON_X__
                <span class="font-semibold">${msg}</span>
            </div>`;
    } else {
        const ingested = result.entries_ingested ?? 0;
        const errors = (result.errors || []).length;
        const warnings = (result.warnings || []).length;
        const failed = result.files_failed ?? 0;
        let summary = `${ingested} note(s) ingested`;
        if (failed > 0) summary += ` &middot; ${failed} file(s) failed`;
        if (errors > 0) summary += ` &middot; ${errors} error(s)`;
        if (warnings > 0) summary += ` &middot; ${warnings} warning(s)`;
        // "synced" is only claimed for a clean run (G10) — problems get an
        // amber banner; the full error/warning lines are in the JSON below.
        const clean = errors === 0 && warnings === 0 && failed === 0;
        const cardCls = clean
            ? 'bg-green-50 text-green-800 border-green-200'
            : 'bg-amber-50 text-amber-900 border-amber-200';
        const headline = clean ? 'Content vault synced' : 'Content vault sync had problems';
        statusEl.innerHTML = `
            <div class="p-4 rounded-lg border ${cardCls}">
                __ICON_CHECK__
                <div>
                    <span class="font-semibold">${headline}</span>
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

function showRegenResult(result, isError) {
    const statusEl = document.getElementById('ingest-status');
    const detailsCard = document.getElementById('ingest-details-card');
    const detailsEl = document.getElementById('ingest-results');

    if (isError) {
        const msg = (result && result.error && result.error.message)
            || result.message || result.error || 'Regeneration failed';
        statusEl.innerHTML = `
            <div class="p-4 rounded-lg bg-red-50 text-red-800 border border-red-200">
                __ICON_X__
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
                __ICON_CHECK__
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
""".replace("__ICON_X__", str(Icon("x", size=24, cls="shrink-0 inline-block"))).replace(
    "__ICON_CHECK__", str(Icon("check", size=24, cls="shrink-0 inline-block"))
)


def build_ingestion_dashboard(vault_path: str) -> Any:
    """Build the full ingestion dashboard content.

    Args:
        vault_path: Default ingestion path shown in the directory form —
            resolved by the route (UI components don't read config).
    """

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
                title="Sync content vault",
                description=(
                    f"Ingest the content vault ({vault_path}) through the reconciler — "
                    "the single directory-ingest path (ADR-070 Decision 9). "
                    "Inbound-only, incremental (unchanged files are skipped)."
                ),
                form_groups=[],
                button_text="Sync content vault",
                onclick="syncContentVault()",
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
