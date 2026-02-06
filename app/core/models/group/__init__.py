"""
Group Domain Models
====================

Three-tier type system for Groups (teacher-student class management).

See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
"""

from core.models.group.group import (
    Group,
    GroupDTO,
    create_group,
    group_dto_to_pure,
    group_pure_to_dto,
)

__all__ = [
    "Group",
    "GroupDTO",
    "create_group",
    "group_dto_to_pure",
    "group_pure_to_dto",
]
