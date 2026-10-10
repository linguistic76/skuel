"""
User Context Intelligence Package
==================================

THE CORE VALUE PROPOSITION: "What should I work on next?"

This package implements learning journey intelligence that synthesizes
user state with graph intelligence to answer: "What should I work on?"

**Architecture:**
UserContextIntelligence = RichUserContext + the eleven domain services
                        = User State + Complete Graph Intelligence

**Package Structure:**
- learning_intelligence.py: Methods 1-4 (path steps, critical path)
- life_path_intelligence.py: Method 7 (life path alignment)
- synergy_intelligence.py: Method 6 (cross-domain synergies)
- schedule_intelligence.py: Method 8 (schedule-aware recommendations)
- daily_planning.py: Method 5 (daily work plan - THE FLAGSHIP)
- perception_intelligence.py: Method 9 (dual-track perception rollup)
- temporal_momentum.py: compute_momentum_signals() (feeds method 5)
- _base.py: IntelligenceMixinBase (the shared attribute surface)
- core.py: Main UserContextIntelligence class (composes mixins)
- factory.py: UserContextIntelligenceFactory

**The nine hub methods:**
1. get_optimal_next_path_steps() - What should I learn next?
2. get_learning_path_critical_path() - Fastest route to life path?
3. get_knowledge_application_opportunities() - Where can I apply this?
4. get_unblocking_priority_order() - What unlocks the most?
5. get_ready_to_work_on_today() - THE FLAGSHIP - What's optimal for TODAY?
6. get_cross_domain_synergies() - Cross-domain synergy detection
7. calculate_life_path_alignment() - Life path alignment scoring
8. get_schedule_aware_recommendations() - Schedule-aware recommendations
9. get_cross_domain_perception_analysis() - Self-rating against the tracked record

Doors: the Insights cards (``GET /insights/hub/{question}``, methods 1, 4, 6, 7, 8, 9),
the Ku page's "Where you can apply this" (method 3), ``/api/context/next-action``
(method 5). Askesis' eight wrappers are the staged second door; method 2 waits on
the LP walk. See /docs/roadmap/askesis-intelligence-doors.md.

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
    PathStep,
    DailyWorkPlan,
    ScheduleAwareRecommendation,
)
```
"""

# Core classes
# Data types
from core.models.context_types import (
    CrossDomainSynergy,
    DailyWorkPlan,
    LifePathAlignment,
    PathStep,
    ScheduleAwareRecommendation,
)
from core.services.user.intelligence.core import UserContextIntelligence

# Mixins (for advanced usage/testing)
from core.services.user.intelligence.daily_planning import DailyPlanningMixin
from core.services.user.intelligence.factory import UserContextIntelligenceFactory
from core.services.user.intelligence.learning_intelligence import LearningIntelligenceMixin
from core.services.user.intelligence.life_path_intelligence import LifePathIntelligenceMixin
from core.services.user.intelligence.schedule_intelligence import ScheduleIntelligenceMixin
from core.services.user.intelligence.synergy_intelligence import SynergyIntelligenceMixin
from core.services.user.intelligence.temporal_momentum import TemporalMomentumMixin

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
    "TemporalMomentumMixin",
    # Data types
    "CrossDomainSynergy",
    "DailyWorkPlan",
    "PathStep",
    "LifePathAlignment",
    "ScheduleAwareRecommendation",
]
