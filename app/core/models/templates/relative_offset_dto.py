"""
RelativeOffsetDTO — Pydantic Companion for RelativeOffset
=========================================================

Boundary serialization for the :class:`RelativeOffset` value type. Pydantic
sits at the API edge per SKUEL's three-tier type system; the frozen dataclass
sits at the core. This module bridges between the two.

Used by template request models (Phase 5) when parsing POST bodies that
include offset-typed fields like ``due_offset``, ``target_offset``, etc.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from core.models.templates.relative_offset import RelativeOffset


class RelativeOffsetDTO(BaseModel):
    """Pydantic mirror of :class:`RelativeOffset` for API boundaries.

    Components are non-negative integers. ``to_value()`` converts to the
    immutable core type; ``from_value()`` constructs from one.
    """

    days: int = Field(default=0, ge=0)
    hours: int = Field(default=0, ge=0)
    minutes: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _reject_all_negative(self) -> RelativeOffsetDTO:
        # Field-level ge=0 already covers individual components, but keep the
        # constructor invariant in one obvious place so future field additions
        # (e.g., weeks, months) can extend the same check.
        if self.days < 0 or self.hours < 0 or self.minutes < 0:
            raise ValueError("RelativeOffsetDTO components must be non-negative")
        return self

    def to_value(self) -> RelativeOffset:
        """Convert to the frozen core value type."""
        return RelativeOffset(days=self.days, hours=self.hours, minutes=self.minutes)

    @classmethod
    def from_value(cls, offset: RelativeOffset) -> RelativeOffsetDTO:
        """Construct from a :class:`RelativeOffset`."""
        return cls(days=offset.days, hours=offset.hours, minutes=offset.minutes)
