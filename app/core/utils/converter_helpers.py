"""
Converter Helpers - Generic Utilities for Model Conversion
===========================================================

Generic helper functions to eliminate duplicate conversion logic across domains.

Core Principle: "Leverage Pydantic's built-in features instead of manual field iteration"

This module provides DRY utilities for the three-tier type system:
- External (Pydantic) ↔ Transfer (DTO) ↔ Core (Domain)

Version: 1.0.0
Date: 2025-11-06
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


def update_request_to_dict(
    request: BaseModel,
    exclude_none: bool = True,
    exclude_unset: bool = True,
    add_timestamp: bool = True,
    exclude_fields: set[str] | None = None,
) -> dict[str, Any]:
    """
    Convert Pydantic update request to update dictionary.

    Eliminates repetitive field-by-field checking (if request.field is not None...)
    by leveraging Pydantic's built-in model_dump() method.

    This replaces 20-40 lines of manual field checking with a single function call.

    Args:
        request: Pydantic update request model
        exclude_none: Exclude fields with None values (default True)
        exclude_unset: Exclude fields that weren't explicitly set (default True)
        add_timestamp: Add updated_at timestamp (default True)
        exclude_fields: Additional fields to exclude from output

    Returns:
        Dictionary of fields to update

    Example:
        # Before (20+ lines of manual checking)
        def task_update_request_to_dto_updates(request: TaskUpdateRequest) -> dict[str, Any]:
            updates = {}
            if request.title is not None:
                updates["title"] = request.title
            if request.description is not None:
                updates["description"] = request.description
            # ... 15+ more fields
            updates["updated_at"] = datetime.now()
            return updates

        # After (1 line)
        def task_update_request_to_dto_updates(request: TaskUpdateRequest) -> dict[str, Any]:
            return update_request_to_dict(request)

    Benefits:
        - DRY: Single source of truth for update conversion
        - Maintainability: Add fields to Pydantic model, conversion auto-updates
        - Type Safety: Pydantic validates field types
        - Performance: No manual iteration overhead
        - Consistency: Same pattern across all 11 converter files

    Pattern Note:
        This leverages Pydantic's model_dump() which:
        - exclude_none=True → excludes fields with None values
        - exclude_unset=True → excludes fields not explicitly set in request

        This is exactly what the manual "if field is not None" checks do,
        but implemented efficiently by Pydantic itself.
    """
    # Use Pydantic's built-in model_dump to get only set fields
    updates = request.model_dump(
        exclude_none=exclude_none,
        exclude_unset=exclude_unset,
        exclude=exclude_fields,
    )

    # Add updated_at timestamp if requested
    if add_timestamp:
        updates["updated_at"] = datetime.now()

    return updates


def create_request_to_dict(
    request: BaseModel,
    user_uid: str,
    exclude_fields: set[str] | None = None,
    add_timestamp: bool = True,
) -> dict[str, Any]:
    """
    Convert Pydantic create request to dictionary for DTO creation.

    Similar to update_request_to_dict but for create operations:
    - Always includes all fields (no exclude_unset)
    - Adds user_uid to the result
    - Adds created_at and updated_at timestamps

    Args:
        request: Pydantic create request model
        user_uid: User UID to add to the result
        exclude_fields: Fields to exclude from output
        add_timestamp: Add created_at/updated_at timestamps (default True)

    Returns:
        Dictionary ready for DTO.create()

    Example:
        # Before
        def task_create_request_to_dto(request: TaskCreateRequest, user_uid: str) -> TaskDTO:
            return TaskDTO.create(
                user_uid=user_uid,
                title=request.title,
                priority=request.priority,
                due_date=request.due_date,
                # ... 10+ more fields
            )

        # After
        def task_create_request_to_dto(request: TaskCreateRequest, user_uid: str) -> TaskDTO:
            data = create_request_to_dict(request, user_uid)
            return TaskDTO.create(**data)
    """
    # Get all fields (exclude_unset=False for create operations)
    data = request.model_dump(exclude_none=False, exclude_unset=False, exclude=exclude_fields)

    # Add user_uid
    data["user_uid"] = user_uid

    # Add timestamps if requested
    if add_timestamp:
        now = datetime.now()
        data["created_at"] = now
        data["updated_at"] = now

    return data


__all__ = ["create_request_to_dict", "update_request_to_dict"]
