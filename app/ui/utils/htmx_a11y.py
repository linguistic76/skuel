"""HTMX Accessibility Utilities - Task 10: WCAG 2.1 Level AA

Utilities for adding contextual screen reader announcements to HTMX operations.

Usage:
    from ui.utils.htmx_a11y import htmx_attrs, HTMXOperation

    # Basic HTMX form with automatic announcement
    Form(
        Input(name="title", placeholder="Task title"),
        Button("Create Task"),
        **htmx_attrs(
            operation=HTMXOperation.CREATE,
            target="#task-list",
            announce="New task added to your list"
        )
    )

    # Loading state with aria-busy
    Div(
        hx_get="/api/tasks",
        **htmx_attrs(
            operation=HTMXOperation.LOAD,
            target="#task-container",
            announce="Tasks loaded successfully"
        )
    )

WCAG Success Criteria:
    - 4.1.3 Status Messages (Level AA) - Screen reader announcements
    - 1.3.1 Info and Relationships (Level A) - ARIA attributes
    - 3.3.1 Error Identification (Level A) - Error announcements
"""

from enum import Enum
from typing import Any


class HTMXOperation(str, Enum):
    """Common HTMX operation types with default announcements."""

    # Creation operations
    CREATE = "create"
    ADD = "add"
    ENROLL = "enroll"
    UPLOAD = "upload"

    # Update operations
    UPDATE = "update"
    EDIT = "edit"
    SAVE = "save"
    TOGGLE = "toggle"
    TRACK = "track"
    DECIDE = "decide"

    # Deletion operations
    DELETE = "delete"
    REMOVE = "remove"
    CANCEL = "cancel"

    # Query operations
    LOAD = "load"
    REFRESH = "refresh"
    SEARCH = "search"

    # Completion operations
    COMPLETE = "complete"
    SUBMIT = "submit"
    PROCESS = "process"


# Default announcement templates by operation type
DEFAULT_ANNOUNCEMENTS = {
    # Creation
    HTMXOperation.CREATE: "Created successfully",
    HTMXOperation.ADD: "Added successfully",
    HTMXOperation.ENROLL: "Enrolled successfully",
    HTMXOperation.UPLOAD: "Uploaded successfully",
    # Update
    HTMXOperation.UPDATE: "Updated successfully",
    HTMXOperation.EDIT: "Changes saved",
    HTMXOperation.SAVE: "Saved successfully",
    HTMXOperation.TOGGLE: "Status changed",
    HTMXOperation.TRACK: "Tracked successfully",
    HTMXOperation.DECIDE: "Decision recorded",
    # Deletion
    HTMXOperation.DELETE: "Deleted successfully",
    HTMXOperation.REMOVE: "Removed successfully",
    HTMXOperation.CANCEL: "Cancelled successfully",
    # Query
    HTMXOperation.LOAD: "Content loaded",
    HTMXOperation.REFRESH: "Refreshed successfully",
    HTMXOperation.SEARCH: "Search complete",
    # Completion
    HTMXOperation.COMPLETE: "Completed successfully",
    HTMXOperation.SUBMIT: "Submitted successfully",
    HTMXOperation.PROCESS: "Processing complete",
}

# Loading state announcements
LOADING_ANNOUNCEMENTS = {
    HTMXOperation.CREATE: "Creating",
    HTMXOperation.ADD: "Adding",
    HTMXOperation.ENROLL: "Enrolling",
    HTMXOperation.UPLOAD: "Uploading",
    HTMXOperation.UPDATE: "Updating",
    HTMXOperation.EDIT: "Saving changes",
    HTMXOperation.SAVE: "Saving",
    HTMXOperation.TOGGLE: "Updating status",
    HTMXOperation.TRACK: "Tracking",
    HTMXOperation.DECIDE: "Recording decision",
    HTMXOperation.DELETE: "Deleting",
    HTMXOperation.REMOVE: "Removing",
    HTMXOperation.CANCEL: "Cancelling",
    HTMXOperation.LOAD: "Loading",
    HTMXOperation.REFRESH: "Refreshing",
    HTMXOperation.SEARCH: "Searching",
    HTMXOperation.COMPLETE: "Completing",
    HTMXOperation.SUBMIT: "Submitting",
    HTMXOperation.PROCESS: "Processing",
}


def htmx_attrs(
    operation: HTMXOperation | None = None,
    target: str | None = None,
    announce: str | None = None,
    announce_loading: str | None = None,
    swap: str = "innerHTML",
    indicator: str | None = None,
) -> dict[str, Any]:
    """Generate HTMX attributes with accessibility enhancements.

    Args:
        operation: Operation type (determines default announcements)
        target: HTMX target selector (e.g., "#task-list")
        announce: Custom success announcement (overrides default)
        announce_loading: Custom loading announcement (overrides default)
        swap: HTMX swap strategy (default: "innerHTML")
        indicator: Loading indicator selector

    Returns:
        Dictionary of HTMX attributes ready for ** unpacking

    Example:
        Button(
            "Create Task",
            **htmx_attrs(
                operation=HTMXOperation.CREATE,
                target="#task-list",
                announce="New task added to your list"
            )
        )
    """
    attrs = {}

    # Add hx-target
    if target:
        attrs["hx-target"] = target

    # Add hx-swap
    attrs["hx-swap"] = swap

    # Add loading indicator
    if indicator:
        attrs["hx-indicator"] = indicator

    # Add accessibility attributes
    if operation:
        # Success announcement (data-announce)
        success_msg = announce or DEFAULT_ANNOUNCEMENTS.get(operation, "Action completed")
        attrs["data-announce"] = success_msg

        # Loading announcement (data-announce-loading)
        loading_msg = announce_loading or LOADING_ANNOUNCEMENTS.get(operation, "Processing")
        attrs["data-announce-loading"] = loading_msg

    return attrs


def htmx_create(
    target: str,
    entity_type: str,
    announce: str | None = None,
) -> dict[str, Any]:
    """Shortcut for CREATE operations with domain-specific announcements.

    Args:
        target: HTMX target selector
        entity_type: Entity type for contextual message (e.g., "task", "goal")
        announce: Custom announcement (overrides default)

    Returns:
        HTMX attributes dictionary

    Example:
        Form(
            Input(name="title"),
            Button("Create"),
            **htmx_create("#task-list", "task")
        )
        # Announces: "New task added to your list"
    """
    default_msg = f"New {entity_type} added to your list"
    return htmx_attrs(
        operation=HTMXOperation.CREATE,
        target=target,
        announce=announce or default_msg,
        announce_loading=f"Creating {entity_type}",
    )


def htmx_update(
    target: str,
    entity_type: str,
    announce: str | None = None,
) -> dict[str, Any]:
    """Shortcut for UPDATE operations with domain-specific announcements.

    Args:
        target: HTMX target selector
        entity_type: Entity type for contextual message
        announce: Custom announcement (overrides default)

    Returns:
        HTMX attributes dictionary

    Example:
        Form(
            Input(name="title"),
            Button("Save"),
            **htmx_update("#task-detail", "task")
        )
        # Announces: "Task updated successfully"
    """
    default_msg = f"{entity_type.capitalize()} updated successfully"
    return htmx_attrs(
        operation=HTMXOperation.UPDATE,
        target=target,
        announce=announce or default_msg,
        announce_loading=f"Updating {entity_type}",
    )


def htmx_delete(
    target: str,
    entity_type: str,
    announce: str | None = None,
) -> dict[str, Any]:
    """Shortcut for DELETE operations with domain-specific announcements.

    Args:
        target: HTMX target selector
        entity_type: Entity type for contextual message
        announce: Custom announcement (overrides default)

    Returns:
        HTMX attributes dictionary

    Example:
        Button(
            "Delete",
            **htmx_delete("#task-list", "task")
        )
        # Announces: "Task deleted successfully"
    """
    default_msg = f"{entity_type.capitalize()} deleted successfully"
    return htmx_attrs(
        operation=HTMXOperation.DELETE,
        target=target,
        announce=announce or default_msg,
        announce_loading=f"Deleting {entity_type}",
    )


def htmx_toggle(
    target: str,
    entity_type: str,
    announce: str | None = None,
) -> dict[str, Any]:
    """Shortcut for TOGGLE operations (completion, status changes).

    Args:
        target: HTMX target selector
        entity_type: Entity type for contextual message
        announce: Custom announcement (overrides default)

    Returns:
        HTMX attributes dictionary

    Example:
        Button(
            "Toggle Complete",
            **htmx_toggle("#task-detail", "task", "Task marked as complete")
        )
    """
    default_msg = f"{entity_type.capitalize()} status updated"
    return htmx_attrs(
        operation=HTMXOperation.TOGGLE,
        target=target,
        announce=announce or default_msg,
        announce_loading="Updating status",
    )


def htmx_upload(
    target: str,
    file_type: str = "file",
    announce: str | None = None,
) -> dict[str, Any]:
    """Shortcut for file UPLOAD operations.

    Args:
        target: HTMX target selector
        file_type: Type of file being uploaded (e.g., "audio", "document")
        announce: Custom announcement (overrides default)

    Returns:
        HTMX attributes dictionary with multipart encoding

    Example:
        Form(
            Input(type="file", name="audio_file"),
            Button("Upload"),
            **htmx_upload("#upload-status", "audio file")
        )
        # Announces: "Audio file uploaded successfully"
    """
    default_msg = f"{file_type.capitalize()} uploaded successfully"
    attrs = htmx_attrs(
        operation=HTMXOperation.UPLOAD,
        target=target,
        announce=announce or default_msg,
        announce_loading=f"Uploading {file_type}",
    )

    # Add multipart encoding for file uploads
    attrs["hx-encoding"] = "multipart/form-data"

    return attrs


def htmx_search(
    target: str,
    announce: str | None = None,
) -> dict[str, Any]:
    """Shortcut for SEARCH operations.

    Args:
        target: HTMX target selector
        announce: Custom announcement (overrides default)

    Returns:
        HTMX attributes dictionary

    Example:
        Form(
            Input(name="query", placeholder="Search..."),
            Button("Search"),
            **htmx_search("#search-results")
        )
        # Announces: "Search complete. Results updated."
    """
    default_msg = "Search complete. Results updated."
    return htmx_attrs(
        operation=HTMXOperation.SEARCH,
        target=target,
        announce=announce or default_msg,
        announce_loading="Searching",
    )


# Domain-specific announcement helpers
def task_announcement(operation: HTMXOperation, custom: str | None = None) -> str:
    """Get task-specific announcement message.

    Args:
        operation: Operation type
        custom: Custom message (overrides default)

    Returns:
        Announcement message

    Example:
        announce = task_announcement(HTMXOperation.CREATE)
        # Returns: "New task added to your list"
    """
    if custom:
        return custom

    messages = {
        HTMXOperation.CREATE: "New task added to your list",
        HTMXOperation.UPDATE: "Task updated successfully",
        HTMXOperation.DELETE: "Task deleted successfully",
        HTMXOperation.TOGGLE: "Task status updated",
        HTMXOperation.COMPLETE: "Task marked as complete",
    }
    return messages.get(operation, DEFAULT_ANNOUNCEMENTS.get(operation, "Action completed"))


def habit_announcement(operation: HTMXOperation, custom: str | None = None) -> str:
    """Get habit-specific announcement message."""
    if custom:
        return custom

    messages = {
        HTMXOperation.CREATE: "New habit created",
        HTMXOperation.UPDATE: "Habit updated successfully",
        HTMXOperation.DELETE: "Habit deleted successfully",
        HTMXOperation.TRACK: "Habit tracked for today",
        HTMXOperation.TOGGLE: "Habit status updated",
    }
    return messages.get(operation, DEFAULT_ANNOUNCEMENTS.get(operation, "Action completed"))


def goal_announcement(operation: HTMXOperation, custom: str | None = None) -> str:
    """Get goal-specific announcement message."""
    if custom:
        return custom

    messages = {
        HTMXOperation.CREATE: "New goal created",
        HTMXOperation.UPDATE: "Goal updated successfully",
        HTMXOperation.DELETE: "Goal deleted successfully",
        HTMXOperation.COMPLETE: "Goal marked as achieved",
    }
    return messages.get(operation, DEFAULT_ANNOUNCEMENTS.get(operation, "Action completed"))


__all__ = [
    "HTMXOperation",
    "htmx_attrs",
    "htmx_create",
    "htmx_update",
    "htmx_delete",
    "htmx_toggle",
    "htmx_upload",
    "htmx_search",
    "task_announcement",
    "habit_announcement",
    "goal_announcement",
]
