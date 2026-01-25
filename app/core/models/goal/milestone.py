"""
Milestone Bridge
================

Bridge file for backward compatibility during three-tier migration.
Re-exports the new three-tier models with the old names.

MIGRATION COMPLETE: All models now use three-tier architecture.

Note: This handles standalone milestone management. For milestones embedded
within goals, see the Goal model which has its own embedded Milestone class.
"""

# Import the new three-tier models
from .goal_milestone_request import (
    StandaloneMilestoneCompleteRequest,
    StandaloneMilestoneCreateRequest,
    StandaloneMilestoneFilterRequest,
    StandaloneMilestoneUpdateRequest,
)
from .milestone_converters import (
    milestone_create_request_to_dto,
    milestone_dict_to_dto,
    milestone_domain_to_dto,
    milestone_dto_to_dict,
    milestone_dto_to_domain,
)
from .milestone_dto import MilestoneDTO
from .milestone_pure import Milestone

# No aliases needed - use Milestone directly

__all__ = [
    # New three-tier models
    "Milestone",
    "MilestoneDTO",
    "StandaloneMilestoneCompleteRequest",
    "StandaloneMilestoneCreateRequest",
    "StandaloneMilestoneFilterRequest",
    "StandaloneMilestoneUpdateRequest",
    # Converters
    "milestone_create_request_to_dto",
    "milestone_dict_to_dto",
    "milestone_domain_to_dto",
    "milestone_dto_to_dict",
    "milestone_dto_to_domain",
]
