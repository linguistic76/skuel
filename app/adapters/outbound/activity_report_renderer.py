"""
Activity Report Markdown Renderer
=================================

Renders an ``ActivityReport`` entity to the ``.md`` document the user downloads
(``GET /activity-reports/md``). Reports are served as Markdown so they open,
edit and annotate in any text editor or Obsidian — the one document format
SKUEL hands users for downloadable content.

The body is the report as the user chose to keep it: a ``revision`` replaces
the generated text, an ``additive`` annotation follows it under its own heading.
Baked recommendations (``metadata["intelligence"]["recommendations"]``) close
the document.
"""

from __future__ import annotations

import re
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.report.activity_report import ActivityReport


def _stamp(value: object | None) -> str:
    """A date-ish value as ``YYYY-MM-DD`` (datetimes, Neo4j temporals, ISO strings).

    Neo4j temporals and ISO strings both stringify ISO-first, so the first ten
    characters are the date for every shape the entity carries.
    """
    if value is None:
        return ""
    if isinstance(value, date):
        return value.isoformat()[:10]
    return str(value)[:10]


def activity_report_filename(report: ActivityReport) -> str:
    """The download filename: ``activity-report-{period}-{date}.md``, slug-safe."""
    parts = ["activity-report", report.time_period or "", _stamp(report.created_at)]
    raw = "-".join(p for p in parts if p)
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip("-")
    return f"{slug[:80] or 'activity-report'}.md"


def render_activity_report_md(report: ActivityReport) -> str:
    """Render the report to Markdown with a YAML frontmatter block.

    Frontmatter carries the identity and window (uid, generated, period, start,
    end, depth, domains, processor) so a re-imported file stays traceable; the
    body is ``user_revision`` when the user replaced the text, otherwise
    ``processed_content`` followed by any additive annotation.
    """
    title = report.title or "Activity Report"
    domains = ", ".join(report.domains_covered) if report.domains_covered else "all"
    processor = report.processor_type.value if report.processor_type else ""
    lines: list[str] = [
        "---",
        f"uid: {report.uid}",
        f"generated: {_stamp(report.created_at)}",
        f"period: {report.time_period or ''}",
        f"period_start: {_stamp(report.period_start)}",
        f"period_end: {_stamp(report.period_end)}",
        f"depth: {report.depth or ''}",
        f"domains: {domains}",
        f"processor: {processor}",
        "---",
        "",
        f"# {title}",
        "",
    ]

    revised = report.annotation_mode == "revision" and bool(report.user_revision)
    body = report.user_revision if revised else report.processed_content
    lines.append((body or "_This report has no generated content._").rstrip())
    lines.append("")

    if report.annotation_mode == "additive" and report.user_annotation:
        lines.extend(["## Your notes", "", report.user_annotation.rstrip(), ""])

    intelligence = (report.metadata or {}).get("intelligence") or {}
    recommendations = intelligence.get("recommendations") or []
    if recommendations:
        lines.extend(["## Recommendations", ""])
        for rec in recommendations:
            if not isinstance(rec, dict):
                continue
            text = str(rec.get("text") or "").strip()
            if not text:
                continue
            domain = str(rec.get("domain") or "").strip()
            severity = str(rec.get("severity") or "").strip()
            tag = " · ".join(t for t in (domain, severity) if t)
            lines.append(f"- {text}" + (f" _({tag})_" if tag else ""))
        lines.append("")

    return "\n".join(lines)


__all__ = ["activity_report_filename", "render_activity_report_md"]
