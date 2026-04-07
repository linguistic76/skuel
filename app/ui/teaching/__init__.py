"""
Teaching UI Components
======================

Public exports for the teaching UI package.
"""

from ui.teaching.badges import entity_type_badge, submission_preview_badge
from ui.teaching.forms import (
    form_data_preview,
    format_date,
    render_feedback_submission_form,
    render_form_data_detail,
    render_form_responses_section,
    render_revision_request_form,
    render_submission_metadata,
)

__all__ = [
    "entity_type_badge",
    "submission_preview_badge",
    "format_date",
    "form_data_preview",
    "render_feedback_submission_form",
    "render_form_data_detail",
    "render_form_responses_section",
    "render_revision_request_form",
    "render_submission_metadata",
]
