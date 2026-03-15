"""
Form Protocols - ISP Contracts for Form Services
=================================================

Interface Segregation Principle protocols consumed by route files.

FormTemplateOperations — admin-facing CRUD + lesson linking
FormSubmissionOperations — user-facing submit, list, delete, share
"""

from typing import Any, Protocol

from core.utils.result_simplified import Result


class FormTemplateOperations(Protocol):
    """Form template operations for admin CRUD and lesson embedding.

    Route consumer: form_templates_api.py
    Implementation: FormTemplateService
    """

    async def create_form_template(
        self,
        title: str,
        form_schema: list[dict[str, Any]],
        description: str | None = None,
        instructions: str | None = None,
        tags: list[str] | None = None,
    ) -> Result[Any]: ...

    async def get_form_template(self, uid: str) -> Result[Any]: ...

    async def list_form_templates(self, limit: int = 50) -> Result[list[Any]]: ...

    async def update_form_template(
        self,
        uid: str,
        title: str | None = None,
        description: str | None = None,
        instructions: str | None = None,
        form_schema: list[dict[str, Any]] | None = None,
        tags: list[str] | None = None,
        status: str | None = None,
    ) -> Result[Any]: ...

    async def delete_form_template(self, uid: str) -> Result[bool]:
        """Delete a FormTemplate. Fails if submissions exist (data integrity guard)."""
        ...

    async def link_to_lesson(self, form_template_uid: str, lesson_uid: str) -> Result[bool]: ...

    async def unlink_from_lesson(self, form_template_uid: str, lesson_uid: str) -> Result[bool]: ...

    async def get_for_lesson(self, lesson_uid: str) -> Result[list[dict[str, Any]]]: ...


class FormSubmissionOperations(Protocol):
    """Form submission operations for user-facing submit/list/delete/share.

    Route consumer: form_submissions_api.py
    Implementation: FormSubmissionService
    """

    async def submit_form(
        self,
        user_uid: str,
        form_template_uid: str,
        form_data: dict[str, Any],
        title: str | None = None,
        group_uid: str | None = None,
        recipient_uids: list[str] | None = None,
        share_with_admin: bool = False,
    ) -> Result[Any]: ...

    async def get_submission(self, uid: str, user_uid: str) -> Result[Any]: ...

    async def get_my_submissions(
        self, user_uid: str, limit: int = 50
    ) -> Result[list[dict[str, Any]]]: ...

    async def delete_submission(self, uid: str, user_uid: str) -> Result[bool]: ...

    async def share_submission(
        self,
        uid: str,
        user_uid: str,
        group_uid: str | None = None,
        recipient_uids: list[str] | None = None,
        share_with_admin: bool = False,
    ) -> Result[bool]: ...
