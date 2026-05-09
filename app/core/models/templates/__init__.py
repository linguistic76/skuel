"""
Activity Templates — PS-Owned Authoring Models
==============================================

PathStep-owned templates that spawn user-owned Activity instances when a student
engages a PathStep. Templates are curriculum content (admin/teacher-authored,
shared); instances are user content. Lifecycle: Template -> Engaged -> Owned.

This package contains the shared value types used across the 6 *Template
entities (added in Phase 2). The 6 entities themselves live in their own
modules within this package.

Value types:
    RelativeOffset    — engagement-relative timing (days/hours/minutes from anchor)
    RelativeOffsetDTO — Pydantic companion for serialization at boundaries

See:
    /home/mike/.claude/plans/skip-when-do-idempotent-shell.md (build plan)
    project_template_relative_offset.md (memory)
    project_engage_pathstep_contract.md (memory)
    project_pathstep_lifecycle_contract.md (memory)
"""

from core.models.templates.relative_offset import RelativeOffset
from core.models.templates.relative_offset_dto import RelativeOffsetDTO

__all__ = [
    "RelativeOffset",
    "RelativeOffsetDTO",
]
