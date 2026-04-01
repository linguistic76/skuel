"""
Exercise Renderer
=================

Renders Exercise domain models to HTML and PDF (printable worksheet).

Architecture:
    Outbound adapter — transforms domain models into presentation formats.
    The route handler calls render_exercise_pdf() directly; no service
    indirection needed since this is pure presentation.

See: adapters/outbound/invoice_renderer.py for the established pattern.
"""

from __future__ import annotations

import html
from datetime import date
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.models.exercises.exercise import Exercise


def _e(value: Any) -> str:
    """HTML-escape a value. Safe to call on None."""
    return html.escape(str(value)) if value is not None else ""


def _field_block(field: dict[str, Any]) -> str:
    """Render a single form_schema field as a printable answer block."""
    label = _e(field.get("label", field.get("name", "")))
    required = field.get("required", False)
    field_type = field.get("type", "text")
    options: list[Any] = field.get("options", [])

    required_marker = '<span class="required">*</span>' if required else ""

    if options:
        options_html = "".join(
            f'<div class="option">☐ {_e(opt)}</div>' for opt in options
        )
        return f"""
        <div class="field-block">
            <div class="field-label">{label}{required_marker}</div>
            <div class="field-options">{options_html}</div>
        </div>"""

    if field_type == "textarea":
        lines = "".join('<div class="answer-line"></div>' for _ in range(6))
        return f"""
        <div class="field-block">
            <div class="field-label">{label}{required_marker}</div>
            <div class="answer-lines">{lines}</div>
        </div>"""

    # text / number / date — single line
    return f"""
    <div class="field-block">
        <div class="field-label">{label}{required_marker}</div>
        <div class="answer-lines"><div class="answer-line"></div></div>
    </div>"""


def render_exercise_html(exercise: Exercise) -> str:
    """
    Render an exercise to a self-contained HTML string for WeasyPrint.

    Produces a clean printable worksheet: metadata header, description,
    form fields with blank answer spaces, and instructions.
    All user-supplied content is HTML-escaped.

    Args:
        exercise: Exercise domain model

    Returns:
        Complete HTML document string
    """
    title = _e(exercise.title)
    description = _e(exercise.description or "")
    instructions = _e(exercise.instructions or "")
    uid = _e(exercise.uid)
    generated = date.today().isoformat()

    # Metadata line
    meta_parts: list[str] = []
    if exercise.sel_category:
        val = getattr(exercise.sel_category, "value", str(exercise.sel_category))
        meta_parts.append(val.replace("_", " ").title())
    if exercise.learning_level:
        val = getattr(exercise.learning_level, "value", str(exercise.learning_level))
        meta_parts.append(val.title())
    if exercise.estimated_time_minutes:
        meta_parts.append(f"{exercise.estimated_time_minutes} min")
    meta_line = " · ".join(meta_parts) if meta_parts else ""

    # Form fields
    fields_html = ""
    if exercise.form_schema:
        field_blocks = "".join(_field_block(f) for f in exercise.form_schema)
        fields_html = f"""
        <div class="section">
            <div class="section-title">Your Responses</div>
            {field_blocks}
        </div>"""

    # Instructions
    instructions_html = ""
    if instructions:
        instructions_html = f"""
        <div class="section instructions-section">
            <div class="section-title">Feedback Instructions</div>
            <p class="instructions-note">
                These are the exact instructions sent to the AI when generating your feedback.
            </p>
            <pre class="instructions-text">{instructions}</pre>
        </div>"""

    description_html = f'<p class="description">{description}</p>' if description else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  @page {{
    size: A4;
    margin: 20mm 18mm 20mm 18mm;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: Georgia, "Times New Roman", serif;
    font-size: 11pt;
    color: #1a1a1a;
    line-height: 1.5;
  }}
  .header {{
    border-bottom: 2px solid #1a1a1a;
    padding-bottom: 8pt;
    margin-bottom: 16pt;
  }}
  .brand {{
    font-size: 8pt;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #6b7280;
    margin-bottom: 4pt;
  }}
  .title {{
    font-size: 18pt;
    font-weight: bold;
    line-height: 1.2;
    margin-bottom: 4pt;
  }}
  .meta {{
    font-size: 9pt;
    color: #6b7280;
  }}
  .description {{
    font-size: 11pt;
    color: #374151;
    margin-bottom: 16pt;
    font-style: italic;
  }}
  .section {{
    margin-bottom: 20pt;
  }}
  .section-title {{
    font-size: 10pt;
    font-weight: bold;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #6b7280;
    border-bottom: 1px solid #e5e7eb;
    padding-bottom: 3pt;
    margin-bottom: 12pt;
  }}
  .field-block {{
    margin-bottom: 14pt;
    page-break-inside: avoid;
  }}
  .field-label {{
    font-size: 10.5pt;
    font-weight: bold;
    margin-bottom: 6pt;
    color: #111827;
    line-height: 1.4;
  }}
  .required {{
    color: #ef4444;
    margin-left: 2pt;
  }}
  .answer-lines {{
    margin-top: 4pt;
  }}
  .answer-line {{
    border-bottom: 1px solid #9ca3af;
    height: 22pt;
    margin-bottom: 4pt;
  }}
  .field-options {{
    margin-top: 4pt;
  }}
  .option {{
    font-size: 10pt;
    margin-bottom: 6pt;
    color: #374151;
  }}
  .instructions-section {{
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 4pt;
    padding: 10pt 12pt;
  }}
  .instructions-note {{
    font-size: 8.5pt;
    color: #9ca3af;
    margin-bottom: 8pt;
    font-style: italic;
  }}
  .instructions-text {{
    font-family: "Courier New", Courier, monospace;
    font-size: 9pt;
    white-space: pre-wrap;
    color: #374151;
    line-height: 1.6;
  }}
  .footer {{
    position: running(footer);
    font-size: 8pt;
    color: #9ca3af;
    display: flex;
    justify-content: space-between;
  }}
  @page {{ @bottom-center {{ content: element(footer); }} }}
</style>
</head>
<body>

<div class="header">
  <div class="brand">SKUEL · Exercise</div>
  <div class="title">{title}</div>
  {f'<div class="meta">{_e(meta_line)}</div>' if meta_line else ""}
</div>

{description_html}

{fields_html}

{instructions_html}

<div class="footer">
  <span>{uid}</span>
  <span>Generated {generated}</span>
</div>

</body>
</html>"""


def render_exercise_pdf(exercise: Exercise) -> bytes:
    """
    Render an exercise to PDF bytes via WeasyPrint.

    Args:
        exercise: Exercise domain model

    Returns:
        PDF file content as bytes

    Raises:
        ImportError: If WeasyPrint is not installed
    """
    html_content = render_exercise_html(exercise)

    from weasyprint import HTML  # type: ignore[import-untyped]

    pdf: bytes = HTML(string=html_content).write_pdf()  # type: ignore[assignment]
    return pdf


__all__ = ["render_exercise_html", "render_exercise_pdf"]
