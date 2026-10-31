"""
LifePath Service Package
=========================

Domain #14: The Destination - "Everything flows toward the life path"

This package provides services for:
1. Vision capture (user's words -> themes)
2. Life path designation (LP selection via ULTIMATE_PATH)
3. Alignment calculation (vision->action measurement)
4. Intelligence (recommendations)

LifePath is NOT a stored entity - it's a designation that elevates a
Learning Path to life-path status. The ULTIMATE_PATH relationship is the
mechanism, and the ONLY one: the node is never mutated, so a designated path
remains an ordinary LearningPath and reads back as one.

Sub-Services:
- LifePathVisionService: Capture and analyze user's vision statement
- LifePathCoreService: Designation CRUD operations
- LifePathAlignmentService: Calculate alignment score (5 dimensions)
- LifePathIntelligenceService: Generate recommendations

Main Entry Point:
    from core.services.lifepath import LifePathService

    lifepath = LifePathService(
        backend, lp_service, ku_service, user_service, llm_service, cross_domain_backend
    )

    # Capture the vision: extract its themes and save both
    vision = await lifepath.capture_vision(user_uid, "I want to become...")

    # Designate life path
    await lifepath.designate_and_calculate(user_uid, lp_uid)

    # Calculate alignment
    alignment = await lifepath.get_alignment(user_uid)
"""

from .lifepath_alignment_service import LifePathAlignmentService
from .lifepath_core_service import LifePathCoreService
from .lifepath_intelligence_service import LifePathIntelligenceService
from .lifepath_service import LifePathService
from .lifepath_vision_service import LifePathVisionService

__all__ = [
    # Main facade
    "LifePathService",
    # Sub-services
    "LifePathVisionService",
    "LifePathCoreService",
    "LifePathAlignmentService",
    "LifePathIntelligenceService",
]
