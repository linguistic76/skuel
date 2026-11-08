"""
Embodiment Mixin — PrinciplesService
======================================

How Principles are lived — expressions, portfolio, integrity.
This is the values-in-action layer.

Part of principles_service.py decomposition (April 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.type_hints import UserUID
from core.services.whole_set_read import find_all_by
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports.domain_protocols import PrinciplesOperations
    from core.services.principles.principles_core_service import PrinciplesCoreService


class _EmbodimentMixin:
    """
    Values-in-action methods for PrinciplesService.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by PrinciplesService.__init__
    core: PrinciplesCoreService
    backend: PrinciplesOperations
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
        Append a lived expression (how the principle was lived out) to the principle.

        The append is planned from the principle as it stands under its lock and
        writes ``expressions`` alone (``PrinciplesCoreService.rewrite_principle``), so
        two expressions appended at once are both kept and a status changed meanwhile
        is left as it is.

        Args:
            dto: Dict with principle_uid, context, behavior, and optional example

        Returns:
            Result with the appended expression; not found when no principle has the uid
        """
        from core.models.principle.principle import Principle
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
        expression = PrincipleExpression(context=context, behavior=behavior, example=example)

        # boundary: pre-serialization patch — the expressions are JSON-encoded at the write.
        def append(principle: Principle) -> dict[str, Any]:
            return {"expressions": [*principle.expressions, expression]}

        written = await self.core.rewrite_principle(principle_uid, append)
        if written.is_error:
            return Result.fail(written)
        self.logger.info("Created expression for principle %s", principle_uid)

        return Result.ok({"context": context, "behavior": behavior, "example": example})

    # ========================================================================
    # PORTFOLIO & INTEGRITY
    # ========================================================================

    async def get_user_principle_portfolio(self, user_uid: UserUID) -> Result[dict[str, Any]]:
        """Get user's complete principle portfolio with integrity analysis."""
        principles_result = await find_all_by(
            self.backend, self.logger, "Principle portfolio", user_uid=user_uid
        )
        if principles_result.is_error:
            return Result.fail(principles_result)
        principles = principles_result.value
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
