"""Toast Notification Helpers.

Utilities for adding toast messages to Result responses.
Toast messages are displayed as temporary notifications in the UI.

Usage:
    from core.utils.toast_helpers import with_toast

    # In service methods:
    result = await self.backend.create(entity)
    return with_toast(result, "Task created successfully", "success")

    # In route handlers:
    result = await service.create_task(...)
    return with_toast(result, "Task created!", "success")
"""

from typing import Any, Literal

from core.utils.result_simplified import Result

ToastType = Literal["success", "error", "info", "warning"]


def with_toast(
    result: Result[Any],
    message: str,
    toast_type: ToastType = "success",
) -> Result[Any]:
    """
    Add a toast notification to a Result.

    The toast will be displayed in the UI when the response is received.
    This works by adding special headers to the HTTP response.

    Args:
        result: The Result to add toast to
        message: Toast message text
        toast_type: Toast type (success, error, info, warning)

    Returns:
        Result with toast headers added (if successful)

    Example:
        result = await self.backend.create(entity)
        return with_toast(result, "Entity created", "success")

    Note:
        - Only adds toast to successful results
        - Errors automatically get error toasts from boundary_handler
        - Message should be concise (< 50 characters ideal)
    """
    if result.is_error:
        # Errors already get toast messages from boundary_handler
        return result

    value = result.value

    # Ensure value is a dict (or make it one)
    if not isinstance(value, dict):
        value = {"data": value}

    # Add or update _headers
    if "_headers" not in value:
        value["_headers"] = {}

    value["_headers"]["X-Toast-Message"] = message
    value["_headers"]["X-Toast-Type"] = toast_type

    return Result.ok(value)


def success_toast(result: Result[Any], message: str) -> Result[Any]:
    """Add success toast to result (convenience function)."""
    return with_toast(result, message, "success")


def info_toast(result: Result[Any], message: str) -> Result[Any]:
    """Add info toast to result (convenience function)."""
    return with_toast(result, message, "info")


def warning_toast(result: Result[Any], message: str) -> Result[Any]:
    """Add warning toast to result (convenience function)."""
    return with_toast(result, message, "warning")


# Default toast messages for common operations
DEFAULT_MESSAGES = {
    "created": "{entity} created successfully",
    "updated": "{entity} updated successfully",
    "deleted": "{entity} deleted successfully",
    "completed": "{entity} completed",
    "archived": "{entity} archived",
    "restored": "{entity} restored",
}


def crud_toast(
    result: Result[Any],
    entity_name: str,
    operation: Literal["created", "updated", "deleted", "completed", "archived", "restored"],
) -> Result[Any]:
    """
    Add a standard CRUD operation toast.

    Args:
        result: The Result to add toast to
        entity_name: Name of the entity (e.g., "Task", "Goal")
        operation: Type of operation performed

    Returns:
        Result with toast headers added

    Example:
        result = await self.backend.create(task)
        return crud_toast(result, "Task", "created")
        # Displays: "Task created successfully"
    """
    template = DEFAULT_MESSAGES.get(operation, "{entity} {operation}")
    message = template.format(entity=entity_name, operation=operation)
    return success_toast(result, message)


__all__ = [
    "with_toast",
    "success_toast",
    "info_toast",
    "warning_toast",
    "crud_toast",
    "ToastType",
]
