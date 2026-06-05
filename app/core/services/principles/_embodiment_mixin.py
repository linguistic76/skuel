"""
Embodiment Mixin — PrinciplesService
======================================

How Principles are lived — expressions, alignment history, portfolio, integrity.
This is the values-in-action layer.

Part of principles_service.py decomposition (April 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from core.models.type_hints import UserUID
from core.utils.result_simplified import Errors, Result


def _by_assessed_date(item: dict[str, Any]) -> str:
    """Sort key for alignment history by assessed_date (SKUEL012: no lambdas)."""
    return item.get("assessed_date", "")


class _EmbodimentMixin:
    """
    Values-in-action methods for PrinciplesService.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by PrinciplesService.__init__
    core: Any
    backend: Any
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

    async def get_principle_expressions(
        self,
        principle_uid: str,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get expressions of a principle (instances where it was lived out).

        Reads from the principle's inline expressions list.

        Args:
            principle_uid: Principle UID

        Returns:
            Result with list of expression dicts
        """
        from core.models.principle.principle import Principle
        from core.models.principle.principle_dto import PrincipleDTO

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

        return Result.ok(
            [
                {
                    "context": e.get("context"),
                    "behavior": e.get("behavior"),
                    "example": e.get("example"),
                }
                for e in ku_dto.expressions
            ]
        )

    # ========================================================================
    # ALIGNMENT HISTORY — Inline list on Principle entity
    # ========================================================================

    async def get_principle_alignment_history(
        self,
        principle_uid: str,
        limit: int = 50,
        days: int = 90,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get historical alignment assessments for a principle.

        Reads from the principle's inline alignment_history list, filtered
        by recency (days) and capped by limit.

        Args:
            principle_uid: Principle UID
            limit: Maximum records
            days: Lookback period in days

        Returns:
            Result with list of alignment assessment dicts
        """
        from datetime import date, timedelta

        from core.models.principle.principle import Principle
        from core.models.principle.principle_dto import PrincipleDTO

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

        cutoff = date.today() - timedelta(days=days)
        history = [
            {
                "assessed_date": str(a.get("assessed_date")),
                "alignment_level": a.get("alignment_level"),
                "evidence": a.get("evidence"),
                "reflection": a.get("reflection"),
            }
            for a in ku_dto.alignment_history
            if (assessed_date := a.get("assessed_date")) and assessed_date >= cutoff
        ]

        # Most recent first, then cap
        history.sort(key=_by_assessed_date, reverse=True)
        return Result.ok(history[:limit])

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
