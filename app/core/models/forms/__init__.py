"""
Forms Domain Models
===================

General-purpose form system: admin creates FormTemplates, users submit FormSubmissions.
Decoupled from the learning loop — forms are a content collection + distribution tool.

Models:
    FormTemplate  — Admin-created form definition (extends Entity, shared)
    FormSubmission — User response to a FormTemplate (extends UserOwnedEntity)
"""

from core.models.forms.form_submission import FormSubmission
from core.models.forms.form_submission_dto import FormSubmissionDTO
from core.models.forms.form_submission_request import FormSubmissionCreateRequest
from core.models.forms.form_template import FormTemplate
from core.models.forms.form_template_dto import FormTemplateDTO
from core.models.forms.form_template_request import (
    FormTemplateCreateRequest,
    FormTemplateUpdateRequest,
)

__all__ = [
    "FormTemplate",
    "FormTemplateDTO",
    "FormTemplateCreateRequest",
    "FormTemplateUpdateRequest",
    "FormSubmission",
    "FormSubmissionDTO",
    "FormSubmissionCreateRequest",
]
