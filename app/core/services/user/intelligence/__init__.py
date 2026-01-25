"""
User Context Intelligence Package
==================================

THE CORE VALUE PROPOSITION: "What should I work on next?"

This package implements learning journey intelligence that synthesizes
user state with graph intelligence to answer: "What should I work on?"

**Architecture:**
UserContextIntelligence = UserContext + 13 Domain Services
                        = User State + Complete Graph Intelligence

**Package Structure:**
- types.py: Data classes (LifePathAlignment, DailyWorkPlan, etc.)
- learning_intelligence.py: Methods 1-4 (learning steps, critical path)
- life_path_intelligence.py: Method 7 (life path alignment)
- synergy_intelligence.py: Method 6 (cross-domain synergies)
- schedule_intelligence.py: Method 8 (schedule-aware recommendations)
- daily_planning.py: Method 5 (daily work plan - THE FLAGSHIP)
- core.py: Main UserContextIntelligence class (composes mixins)
- factory.py: UserContextIntelligenceFactory

**The 8 Core Methods:**
1. get_optimal_next_learning_steps() - What should I learn next?
2. get_learning_path_critical_path() - Fastest route to life path?
3. get_knowledge_application_opportunities() - Where can I apply this?
4. get_unblocking_priority_order() - What unlocks the most?
5. get_ready_to_work_on_today() - THE FLAGSHIP - What's optimal for TODAY?
6. get_cross_domain_synergies() - Cross-domain synergy detection
7. calculate_life_path_alignment() - Life path alignment scoring
8. get_schedule_aware_recommendations() - Schedule-aware recommendations

**Context-Based Queries:**
Simple context queries (get_ready_to_learn, etc.) are accessed directly
via UserContext methods following the "One Path Forward" principle.

**Usage:**
```python
# Primary import
from core.services.user.intelligence import (
    UserContextIntelligence,
    UserContextIntelligenceFactory,
)

# Or import types
from core.services.user.intelligence import (
    LifePathAlignment,
    CrossDomainSynergy,
    LearningStep,
    DailyWorkPlan,
    ScheduleAwareRecommendation,
)
```

Version: 5.0.0 (Removed GraphNativeMixin - One Path Forward)
Date: 2026-01-08
"""

# Core classes
from core.services.user.intelligence.core import UserContextIntelligence

# Mixins (for advanced usage/testing)
from core.services.user.intelligence.daily_planning import DailyPlanningMixin
from core.services.user.intelligence.factory import UserContextIntelligenceFactory
from core.services.user.intelligence.learning_intelligence import LearningIntelligenceMixin
from core.services.user.intelligence.life_path_intelligence import LifePathIntelligenceMixin
from core.services.user.intelligence.schedule_intelligence import ScheduleIntelligenceMixin
from core.services.user.intelligence.synergy_intelligence import SynergyIntelligenceMixin

# Data types
from core.services.user.intelligence.types import (
    CrossDomainSynergy,
    DailyWorkPlan,
    LearningStep,
    LifePathAlignment,
    ScheduleAwareRecommendation,
)

__all__ = [
    # Core classes
    "UserContextIntelligence",
    "UserContextIntelligenceFactory",
    # Mixins
    "DailyPlanningMixin",
    "LearningIntelligenceMixin",
    "LifePathIntelligenceMixin",
    "ScheduleIntelligenceMixin",
    "SynergyIntelligenceMixin",
    # Data types
    "CrossDomainSynergy",
    "DailyWorkPlan",
    "LearningStep",
    "LifePathAlignment",
    "ScheduleAwareRecommendation",
]
