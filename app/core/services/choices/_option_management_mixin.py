"""
Option Management Mixin — ChoicesService
==========================================

Option CRUD and decision-making operations.

Part of choices_service.py decomposition (April 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.choice.choice import Choice


class _OptionManagementMixin:
    """
    Option CRUD and decision-making for ChoicesService.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by ChoicesService.__init__
    core: Any

    # ========================================================================
    # OPTION MANAGEMENT - Delegate to ChoicesCoreService
    # ========================================================================

    async def add_option(
        self,
        choice_uid: str,
        title: str,
        description: str,
        feasibility_score: float = 0.5,
        risk_level: float = 0.5,
        potential_impact: float = 0.5,
        resource_requirement: float = 0.5,
        estimated_duration: int | None = None,
        dependencies: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> Result[Choice]:
        """Add a new option to an existing choice."""
        return await self.core.add_option(
            choice_uid=choice_uid,
            title=title,
            description=description,
            feasibility_score=feasibility_score,
            risk_level=risk_level,
            potential_impact=potential_impact,
            resource_requirement=resource_requirement,
            estimated_duration=estimated_duration,
            dependencies=dependencies,
            tags=tags,
        )

    async def update_option(
        self,
        choice_uid: str,
        option_uid: str,
        title: str | None = None,
        description: str | None = None,
        feasibility_score: float | None = None,
        risk_level: float | None = None,
        potential_impact: float | None = None,
        resource_requirement: float | None = None,
        estimated_duration: int | None = None,
        dependencies: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> Result[Choice]:
        """Update an existing option in a choice."""
        return await self.core.update_option(
            choice_uid=choice_uid,
            option_uid=option_uid,
            title=title,
            description=description,
            feasibility_score=feasibility_score,
            risk_level=risk_level,
            potential_impact=potential_impact,
            resource_requirement=resource_requirement,
            estimated_duration=estimated_duration,
            dependencies=dependencies,
            tags=tags,
        )

    async def remove_option(
        self,
        choice_uid: str,
        option_uid: str,
    ) -> Result[Choice]:
        """Remove an option from a choice."""
        return await self.core.remove_option(choice_uid=choice_uid, option_uid=option_uid)

    async def make_decision(
        self,
        choice_uid: str,
        selected_option_uid: str,
        decision_rationale: str | None = None,
        confidence: float = 0.5,
    ) -> Result[Choice]:
        """Make a decision on a choice (select an option)."""
        return await self.core.make_decision(
            choice_uid=choice_uid,
            selected_option_uid=selected_option_uid,
            decision_rationale=decision_rationale,
            confidence=confidence,
        )
