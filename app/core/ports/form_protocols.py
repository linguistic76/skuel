"""
Form Protocols - ISP Contracts for Form Services
=================================================

Two protocol tiers:
- Backend-level: FormTemplateBackendOperations, FormSubmissionBackendOperations
  (consumed by service __init__, extend BackendOperations[T] with domain methods)
- Route-level: FormTemplateOperations, FormSubmissionOperations
  (consumed by route files, service-facing ISP contracts)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from core.models.type_hints import UserUID
from core.ports.base_protocols import BackendOperations
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    import builtins

    from core.models.forms.form_submission import FormSubmission
    from core.models.forms.form_template import FormTemplate

# ========================================================================
# Backend-level protocols (typed self.backend in services)
# ========================================================================


class FormTemplateBackendOperations(BackendOperations["FormTemplate"], Protocol):
    """Backend operations for FormTemplate — base CRUD + domain-specific methods.

    Implementation: FormTemplateBackend (domain_backends.py)
    Consumer: FormTemplateService.__init__
    """

    async def link_to_lesson(self, form_template_uid: str, lesson_uid: str) -> Result[bool]: ...

    async def unlink_from_lesson(self, form_template_uid: str, lesson_uid: str) -> Result[bool]: ...

    async def get_forms_for_lesson(self, lesson_uid: str) -> Result[list[dict[str, Any]]]: ...

    async def count_submissions(self, template_uid: str) -> Result[int]: ...


class FormSubmissionBackendOperations(BackendOperations["FormSubmission"], Protocol):
    """Backend operations for FormSubmission — base CRUD + domain-specific methods.

    Implementation: FormSubmissionBackend (domain_backends.py)
    Consumer: FormSubmissionService.__init__
    """

    async def create_with_relationships(
        self,
        submission: FormSubmission,
        user_uid: UserUID,
        form_template_uid: str,
    ) -> Result[FormSubmission]: ...

    async def list_by_user(
        self, user_uid: UserUID, limit: int = 50
    ) -> Result[list[dict[str, Any]]]: ...

    async def get_submissions_for_template(
        self, form_template_uid: str
    ) -> Result[list[dict[str, Any]]]: ...

    async def find_admin_user_uid(self, admin_role: str) -> Result[str | None]: ...


# ========================================================================
# Route-level protocols (typed service in routes)
# ========================================================================


class FormTemplateOperations(Protocol):
    """Form template operations — CRUDOperations + lesson embedding.

    Route consumer: form_templates_api.py, CRUDRouteFactory
    Implementation: FormTemplateService (extends BaseService)
    """

    async def create(self, entity: Any) -> Result[FormTemplate]: ...

    async def get(self, uid: str) -> Result[FormTemplate | None]: ...

    async def update(self, uid: str, updates: dict[str, Any]) -> Result[FormTemplate]: ...

    async def delete(self, uid: str, cascade: bool = False) -> Result[bool]: ...

    async def list(
        self,
        limit: int = 100,
        offset: int = 0,
        order_by: str | None = None,
        order_desc: bool = False,
        user_uid: UserUID | None = None,
        **kwargs: Any,
    ) -> Result[builtins.list[FormTemplate]]: ...

    async def link_to_lesson(self, form_template_uid: str, lesson_uid: str) -> Result[bool]: ...

    async def unlink_from_lesson(self, form_template_uid: str, lesson_uid: str) -> Result[bool]: ...

    async def get_for_lesson(self, lesson_uid: str) -> Result[builtins.list[dict[str, Any]]]: ...


class FormSubmissionOperations(Protocol):
    """Form submission operations for user-facing submit/list/delete/share.

    Route consumer: form_submissions_api.py
    Implementation: FormSubmissionService
    """

    async def submit_form(
        self,
        user_uid: UserUID,
        form_template_uid: str,
        form_data: dict[str, Any],
        title: str | None = None,
        group_uid: str | None = None,
        recipient_uids: list[str] | None = None,
        share_with_admin: bool = False,
    ) -> Result[FormSubmission]: ...

    async def get_submission(
        self, uid: str, user_uid: UserUID
    ) -> Result[FormSubmission | None]: ...

    async def get_my_submissions(
        self, user_uid: UserUID, limit: int = 50
    ) -> Result[list[dict[str, Any]]]: ...

    async def delete_submission(self, uid: str, user_uid: UserUID) -> Result[bool]: ...

    async def share_submission(
        self,
        uid: str,
        user_uid: UserUID,
        group_uid: str | None = None,
        recipient_uids: list[str] | None = None,
        share_with_admin: bool = False,
    ) -> Result[bool]: ...
