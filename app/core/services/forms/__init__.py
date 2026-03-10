"""
Forms Services
==============

FormTemplateService — CRUD + article linking for admin-created form templates.
FormSubmissionService — Submit, list, delete, and share user form responses.
"""

from core.services.forms.form_submission_service import FormSubmissionService
from core.services.forms.form_template_service import FormTemplateService

__all__ = ["FormTemplateService", "FormSubmissionService"]
