"""
Form Domain Events
===================

Events published when form operations occur.

FormTemplate events:
- FormTemplateCreated — admin creates a new form template
- FormTemplateUpdated — admin updates a form template
- FormTemplateDeleted — admin deletes a form template

FormSubmission events:
- FormSubmitted        — user submits a form response
- FormSubmissionDeleted — user deletes a form submission
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.events.base import BaseEvent


@dataclass(frozen=True)
class FormTemplateCreated(BaseEvent):
    """
    Published when an admin creates a new FormTemplate.

    Triggers:
    - Audit trail for admin content creation
    """

    template_uid: str
    title: str
    field_count: int
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "form_template.created"


@dataclass(frozen=True)
class FormTemplateUpdated(BaseEvent):
    """
    Published when an admin updates a FormTemplate.

    Triggers:
    - Audit trail for content changes
    """

    template_uid: str
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "form_template.updated"


@dataclass(frozen=True)
class FormTemplateDeleted(BaseEvent):
    """
    Published when an admin deletes a FormTemplate.

    Triggers:
    - Cleanup of related resources
    """

    template_uid: str
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "form_template.deleted"


@dataclass(frozen=True)
class FormSubmitted(BaseEvent):
    """
    Published when a user submits a form response.

    Triggers:
    - User context updates
    - Notification to admin (if share_with_admin)
    - Activity tracking
    """

    submission_uid: str
    user_uid: str
    template_uid: str
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "form.submitted"


@dataclass(frozen=True)
class FormSubmissionDeleted(BaseEvent):
    """
    Published when a user deletes a form submission.

    Triggers:
    - User context updates
    """

    submission_uid: str
    user_uid: str
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "form_submission.deleted"
