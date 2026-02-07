"""
Domain-Integrated Ingestion Trigger Components
================================================

Ingestion buttons and modals for domain list pages (admin-only).

Components:
- DomainIngestionTrigger: Ingestion button for domain pages
- DomainIngestionModal: Modal for ingestion configuration
"""

from fasthtml.common import *


def DomainIngestionTrigger(domain_name: str, is_admin: bool) -> FT | None:
    """
    Ingestion trigger button for domain pages (admin-only).

    Args:
        domain_name: Domain name (e.g., "ku", "tasks", "goals")
        is_admin: Whether current user is admin

    Returns:
        FastHTML component or None if not admin
    """
    if not is_admin:
        return None  # Hide if not admin

    return Button(
        f"🔄 Ingest {domain_name.upper()}",
        cls="btn btn-sm btn-outline btn-primary",
        onclick=f"document.getElementById('ingestion-modal-{domain_name}').showModal()",
    )


def DomainIngestionModal(domain_name: str, default_path: str | None = None) -> FT:
    """
    Modal for domain-specific ingestion configuration.

    Args:
        domain_name: Domain name (e.g., "ku", "tasks", "goals")
        default_path: Default source directory path (optional)

    Returns:
        FastHTML component
    """
    if default_path is None:
        default_path = f"/home/mike/0bsidian/skuel/docs/{domain_name}"

    return Dialog(
        Form(
            Div(
                # Modal header
                H3(f"Ingest {domain_name.upper()} from Files", cls="font-bold text-lg mb-4"),
                # Source directory
                Div(
                    Label("Source Directory", cls="label"),
                    Input(
                        type="text",
                        name="source_path",
                        placeholder=default_path,
                        value=default_path,
                        cls="input input-bordered w-full",
                        required=True,
                    ),
                    P(
                        "Path to directory containing Markdown/YAML files",
                        cls="text-xs text-base-content/70 mt-1",
                    ),
                    cls="form-control mb-4",
                ),
                # Pattern
                Div(
                    Label("File Pattern (optional)", cls="label"),
                    Input(
                        type="text",
                        name="pattern",
                        placeholder="*.md",
                        value="*.md",
                        cls="input input-bordered w-full",
                    ),
                    P(
                        "Glob pattern to filter files (default: *.md)",
                        cls="text-xs text-base-content/70 mt-1",
                    ),
                    cls="form-control mb-4",
                ),
                # Dry run checkbox
                Div(
                    Label(
                        Input(
                            type="checkbox",
                            name="dry_run",
                            value="true",
                            cls="checkbox checkbox-primary",
                        ),
                        Span("Preview only (dry-run)", cls="ml-2"),
                        cls="label cursor-pointer justify-start",
                    ),
                    P(
                        "Preview changes without writing to database",
                        cls="text-xs text-base-content/70 mt-1",
                    ),
                    cls="form-control mb-4",
                ),
                # Action buttons
                Div(
                    Button(
                        "Start Ingestion",
                        type="submit",
                        cls="btn btn-primary",
                    ),
                    Button(
                        "Cancel",
                        type="button",
                        cls="btn btn-ghost",
                        onclick=f"document.getElementById('ingestion-modal-{domain_name}').close()",
                    ),
                    cls="modal-action",
                ),
                # Results container
                Div(
                    id=f"ingestion-results-{domain_name}",
                    cls="mt-4",
                ),
                cls="modal-box max-w-2xl",
            ),
            method="dialog",
            hx_post=f"/api/ingest/domain/{domain_name}",
            hx_target=f"#ingestion-results-{domain_name}",
            hx_indicator=f"#ingestion-loading-{domain_name}",
        ),
        # Loading indicator
        Div(
            Span(cls="loading loading-spinner loading-lg"),
            Span("Ingesting...", cls="ml-2"),
            id=f"ingestion-loading-{domain_name}",
            cls="htmx-indicator text-center py-4",
        ),
        id=f"ingestion-modal-{domain_name}",
        cls="modal",
    )


__all__ = [
    "DomainIngestionTrigger",
    "DomainIngestionModal",
]
