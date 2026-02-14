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
Learning Path (Ku with ku_type='learning_path') to life-path status
(ku_type='life_path'). The ULTIMATE_PATH relationship is the mechanism.

Sub-Services:
- LifePathVisionService: Capture and analyze user's vision statement
- LifePathCoreService: Designation CRUD operations
- LifePathAlignmentService: Calculate alignment score (5 dimensions)
- LifePathIntelligenceService: Generate recommendations

Main Entry Point:
    from core.services.lifepath import LifePathService

    lifepath = LifePathService(driver, lp_service, ku_service, user_service, llm_service)

    # Capture vision
    vision = await lifepath.vision.capture_vision(user_uid, "I want to become...")

    # Designate life path
    await lifepath.core.designate_life_path(user_uid, lp_uid)

    # Calculate alignment
    alignment = await lifepath.alignment.calculate_alignment(user_uid)
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
