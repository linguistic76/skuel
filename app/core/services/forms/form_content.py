"""Canonical processed_content generation for FormSubmissions."""

from typing import Any

MAX_PROCESSED_CONTENT_LENGTH = 10_000


def build_form_processed_content(
    *,
    template_title: str,
    template_uid: str,
    schema: tuple[dict[str, Any], ...] | None,
    form_data: dict[str, Any],
) -> str:
    """
    Deterministic searchable text from template schema + form data.

    Schema ordering, labels over keys, bools normalized, unknown keys ignored.
    """
    lines: list[str] = [f"Form: {template_title} ({template_uid})"]
    if not schema:
        return lines[0]
    for spec in schema:
        name = spec.get("name")
        if not name or name not in form_data:
            continue
        label = spec.get("label", name)
        value = form_data[name]
        if value is None:
            continue
        if isinstance(value, bool):
            display = "Yes" if value else "No"
        else:
            display = str(value).strip()
        if not display:
            continue
        lines.append(f"{label}: {display}")
    result = "\n".join(lines)
    if len(result) > MAX_PROCESSED_CONTENT_LENGTH:
        return result[:MAX_PROCESSED_CONTENT_LENGTH]
    return result
