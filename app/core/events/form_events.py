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
from typing import Any, ClassVar

from core.events.base import BaseEvent
from core.models.type_hints import UserUID


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
    metadata: dict[str, Any] | None = None

    event_type: ClassVar[str] = "form_template.created"


@dataclass(frozen=True)
class FormTemplateUpdated(BaseEvent):
    """
    Published when an admin updates a FormTemplate.

    Triggers:
    - Audit trail for content changes
    """

    template_uid: str
    metadata: dict[str, Any] | None = None

    event_type: ClassVar[str] = "form_template.updated"


@dataclass(frozen=True)
class FormTemplateDeleted(BaseEvent):
    """
    Published when an admin deletes a FormTemplate.

    Triggers:
    - Cleanup of related resources
    """

    template_uid: str
    metadata: dict[str, Any] | None = None

    event_type: ClassVar[str] = "form_template.deleted"


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
    user_uid: UserUID
    template_uid: str
    metadata: dict[str, Any] | None = None

    event_type: ClassVar[str] = "form.submitted"


@dataclass(frozen=True)
class FormSubmissionDeleted(BaseEvent):
    """
    Published when a user deletes a form submission.

    Triggers:
    - User context updates
    """

    submission_uid: str
    user_uid: UserUID
    metadata: dict[str, Any] | None = None

    event_type: ClassVar[str] = "form_submission.deleted"
