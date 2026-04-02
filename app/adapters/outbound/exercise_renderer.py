"""
Exercise Renderer
=================

Renders Exercise domain models to Markdown (.md) — a plain-text format
users can open, edit, and respond to in any text editor or Obsidian.

Architecture:
    Outbound adapter — transforms domain models into presentation formats.
    The route handler calls render_exercise_md() directly; no service
    indirection needed since this is pure presentation.

Format choice:
    SKUEL embraces Markdown as the default document format. Exercises are
    downloaded as .md files so students can fill in responses directly,
    commit them to a vault, or paste into the submission form.

See: adapters/outbound/invoice_renderer.py for the PDF pattern (finance only).
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.models.exercises.exercise import Exercise


def _field_block_md(field: dict[str, Any]) -> str:
    """Render a single form_schema field as a Markdown answer block."""
    label = field.get("label", field.get("name", ""))
    required = field.get("required", False)
    field_type = field.get("type", "text")
    options: list[Any] = field.get("options", [])

    required_marker = " *(required)*" if required else ""
    lines = [f"**{label}**{required_marker}", ""]

    if options:
        lines.extend(f"- [ ] {opt}" for opt in options)
        lines.append("")
        return "\n".join(lines)

    if field_type == "textarea":
        lines += ["", "", "", "", ""]  # blank lines for a longer response
    else:
        lines.append("")  # single blank line

    lines.append("")
    return "\n".join(lines)


def render_exercise_md(exercise: Exercise, user_uid: str | None = None) -> str:
    """
    Render an exercise to a Markdown worksheet.

    Produces a file students download, fill in, and submit back. The YAML
    frontmatter carries submission metadata (exercise_uid, exercise_number,
    user_uid, revision) so the upload handler can route the submission
    automatically — no Identifier field needed on the submit form.

    Args:
        exercise: Exercise domain model
        user_uid: Authenticated user's UID — pre-filled in the frontmatter
            so the student doesn't have to look it up. Pass None to emit a
            placeholder string instead.

    Returns:
        Markdown document string with YAML frontmatter
    """
    today = date.today().isoformat()
    title = exercise.title or exercise.uid

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

    sections: list[str] = []

    # YAML frontmatter — submission metadata the upload handler reads back
    uid_value = user_uid or "your_user_uid_here"
    num_value = str(exercise.exercise_number) if exercise.exercise_number is not None else ""
    sections.append("---")
    sections.append(f"exercise_uid: {exercise.uid}")
    if num_value:
        sections.append(f"exercise_number: {num_value}")
    sections.append(f"user_uid: {uid_value}")
    sections.append("revision: 1")
    sections.append("---")
    sections.append("")

    # Header
    sections.append(f"# {title}")
    if meta_parts:
        sections.append(" · ".join(meta_parts))
    sections.append(f"*{exercise.uid} — Generated {today}*")
    sections.append("")

    # Description
    if exercise.description:
        sections.append(exercise.description)
        sections.append("")

    # Response fields
    if exercise.form_schema:
        sections.append("---")
        sections.append("")
        sections.append("## Your Responses")
        sections.append("")
        sections.extend(_field_block_md(field) for field in exercise.form_schema)

    # Feedback instructions
    if exercise.instructions:
        sections.append("---")
        sections.append("")
        sections.append("## Feedback Instructions")
        sections.append("")
        sections.append(
            "*These are the instructions sent to the AI when generating your feedback.*"
        )
        sections.append("")
        sections.append(exercise.instructions)
        sections.append("")

    return "\n".join(sections)


__all__ = ["render_exercise_md"]
