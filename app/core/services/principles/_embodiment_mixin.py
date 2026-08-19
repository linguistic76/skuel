"""
Embodiment Mixin — PrinciplesService
======================================

How Principles are lived — expressions, portfolio, integrity.
This is the values-in-action layer.

Part of principles_service.py decomposition (April 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from core.models.type_hints import UserUID
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports.domain_protocols import PrinciplesOperations


class _EmbodimentMixin:
    """
    Values-in-action methods for PrinciplesService.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by PrinciplesService.__init__
    core: Any
    backend: "PrinciplesOperations"
    relationships: Any
    logger: Any

    # ========================================================================
    # PRINCIPLE EXPRESSIONS — Inline list on Principle entity
    # ========================================================================

    async def create_principle_expression(
        self,
        dto: Any,
    ) -> Result[dict[str, Any]]:
        """
        Create a principle expression (how principle was lived out).

        Stores expression on principle's inline expressions list via PrincipleDTO.

        Args:
            dto: Dict with principle_uid, context, behavior, and optional example

        Returns:
            Result with the created expression dict
        """
        from core.models.principle.principle import Principle
        from core.models.principle.principle_dto import PrincipleDTO
        from core.models.principle.principle_types import PrincipleExpression

        principle_uid = (
            dto.get("principle_uid")
            if isinstance(dto, dict)
            else getattr(dto, "principle_uid", None)
        )
        if not principle_uid:
            return Result.fail(
                Errors.validation(message="principle_uid is required", field="principle_uid")
            )

        context = dto.get("context") if isinstance(dto, dict) else getattr(dto, "context", None)
        behavior = dto.get("behavior") if isinstance(dto, dict) else getattr(dto, "behavior", None)
        if not context or not behavior:
            return Result.fail(
                Errors.validation(message="context and behavior are required", field="context")
            )

        example = dto.get("example") if isinstance(dto, dict) else getattr(dto, "example", None)

        # Get current principle
        principle_result = await self.core.backend.get(principle_uid)
        if principle_result.is_error:
            return Result.fail(principle_result)

        principle_data = principle_result.value
        if isinstance(principle_data, Principle):
            ku_dto = principle_data.to_dto()
        elif isinstance(principle_data, dict):
            ku_dto = PrincipleDTO.from_dict(principle_data)
        else:
            return Result.fail(Errors.not_found(resource="Principle", identifier=principle_uid))

        # Create and append expression. DTO stores expressions as list[dict]
        # (flattened on to_dict via asdict); convert here to keep that contract honest.
        expression = PrincipleExpression(context=context, behavior=behavior, example=example)
        ku_dto.expressions.append(asdict(expression))

        # raw-write: full-DTO entity replace after appending an expression to the DTO's
        # expression list (not a partial property patch). ADR-066's PrincipleUpdateIntent
        # models partial column patches, not whole-entity persistence or expression mutation —
        # dto.to_dict() is the honest shape here.
        await self.core.backend.update(principle_uid, ku_dto.to_dict())
        self.logger.info("Created expression for principle %s", principle_uid)

        return Result.ok({"context": context, "behavior": behavior, "example": example})

    # ========================================================================
    # PORTFOLIO & INTEGRITY
    # ========================================================================

    async def get_user_principle_portfolio(self, user_uid: UserUID) -> Result[dict[str, Any]]:
        """Get user's complete principle portfolio with integrity analysis."""
        # Get all principles for the user
        principles_result = await self.backend.list(filters={"user_uid": user_uid}, limit=100)
        if principles_result.is_error:
            return Result.fail(principles_result)
        # list() returns tuple[list[Principle], int]
        principles, _total = principles_result.value
        return Result.ok(
            {
                "user_uid": user_uid,
                "principles": principles,
                "count": len(principles),
            }
        )

    async def calculate_principle_integrity(
        self, user_uid: UserUID, principle_uid: str
    ) -> Result[dict[str, Any]]:
        """Calculate how well user's actions align with stated principle."""
        # Get the principle and its cross-domain context
        context_result = await self.relationships.get_cross_domain_context(principle_uid)
        if context_result.is_error:
            return context_result
        return Result.ok(
            {
                "principle_uid": principle_uid,
                "user_uid": user_uid,
                "context": context_result.value,
                "integrity_score": 0.5,  # Placeholder - would need actual calculation
            }
        )
