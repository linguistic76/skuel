# Trial Limits Infrastructure
*Last updated: 2026-01-04*

**Location:** `/core/services/trial_limits.py`

## Overview

The Trial Limits Service manages consumption limits for REGISTERED (free trial) users. It integrates with SKUEL's four-tier role system to enforce usage quotas.

**Current Policy (January 2026):** All domains are UNLIMITED for all users. The infrastructure exists for future monetization.

## Role Hierarchy Context

| Role | Limits Apply? | Description |
|------|---------------|-------------|
| **REGISTERED** | Yes (when enabled) | Free trial users |
| **MEMBER** | No | Paid subscription - unlimited |
| **TEACHER** | No | Inherits MEMBER permissions |
| **ADMIN** | No | Inherits all permissions |

## Configuration

```python
from core.services.trial_limits import TrialLimits, UNLIMITED

# Default configuration (all unlimited)
@dataclass(frozen=True)
class TrialLimits:
    # Curriculum domains
    max_knowledge_units: int = UNLIMITED  # -1
    max_learning_steps: int = UNLIMITED
    max_learning_paths: int = UNLIMITED

    # Activity domains
    max_tasks: int = UNLIMITED
    max_goals: int = UNLIMITED
    max_habits: int = UNLIMITED
    max_events: int = UNLIMITED
    max_choices: int = UNLIMITED

    # Rate limiting (future use)
    max_daily_api_calls: int = 100
```

Use `UNLIMITED` (-1) to indicate no limit for any category.

## Service API

### Initialization

```python
from core.services.trial_limits import create_trial_limits_service

trial_limits = create_trial_limits_service(
    user_service=user_service,
    driver=neo4j_driver,
    limits=None  # Uses TRIAL_LIMITS singleton
)
```

### Check Limit Before Creation

```python
async def create_task(self, user_uid: str, data: TaskCreateRequest) -> Result[Task]:
    # Check trial limit first
    limit_check = await trial_limits.check_limit(user_uid, "task")
    if limit_check.is_error:
        return limit_check  # Returns error with upgrade message

    # Proceed with creation
    return await self._create_task(data)
```

**Entity types:** `task`, `goal`, `habit`, `event`, `choice`, `ku_access`, `ls_access`, `lp_enrollment`

### Get Usage Summary (for UI)

```python
summary = await trial_limits.get_usage_summary(user_uid)
# Returns:
# {
#     "unlimited": False,  # True for MEMBER+
#     "role": "registered",
#     "usage": {
#         "task": {"current": 5, "limit": "unlimited", "remaining": "unlimited", "unlimited": True},
#         "goal": {"current": 2, "limit": "unlimited", "remaining": "unlimited", "unlimited": True},
#         ...
#     }
# }
```

## Implementation Details

### Usage Counting

Each entity type has a dedicated Cypher query:

```python
# Task count (excludes archived)
MATCH (u:User {uid: $uid})-[:HAS_TASK]->(t:Task)
WHERE t.status <> 'archived'
RETURN count(t) as count

# KU access count
MATCH (u:User {uid: $uid})-[:LEARNING|MASTERED]->(k:Ku)
RETURN count(DISTINCT k) as count

# LP enrollment count
MATCH (u:User {uid: $uid})-[:ENROLLED_IN]->(lp:Lp)
RETURN count(lp) as count
```

### Limit Enforcement Flow

```
User Action (create task)
    ↓
check_limit(user_uid, "task")
    ↓
Get user role from UserService
    ↓
is_subscriber()? → Yes → Return OK (no limits)
    ↓ No
Query current count
    ↓
Compare to limit
    ↓
current >= limit? → Return business error with upgrade message
    ↓ No
Return OK
```

### Error Response

When limit is exceeded:
```python
Result.fail(
    Errors.business(
        rule="trial_limit",
        message="Trial limit reached: 10/10 tasks. Upgrade to Member for unlimited access."
    )
)
```

## Future Monetization

When ready to enable limits:

1. **Update configuration:**
```python
PAID_LIMITS = TrialLimits(
    max_tasks=10,
    max_goals=3,
    max_habits=5,
    max_events=20,
    max_choices=UNLIMITED,
    max_knowledge_units=UNLIMITED,
    max_learning_steps=UNLIMITED,
    max_learning_paths=3,
    max_daily_api_calls=100,
)
```

2. **Bootstrap with custom limits:**
```python
trial_limits = create_trial_limits_service(
    user_service=user_service,
    driver=driver,
    limits=PAID_LIMITS
)
```

3. **Add limit checks to domain services:**
```python
# In TasksService.create()
limit_check = await self.trial_limits.check_limit(user_uid, "task")
if limit_check.is_error:
    return limit_check
```

## Integration Points

- **UserService:** Required for role lookup
- **Neo4j Driver:** Required for usage count queries
- **Domain Services:** Call `check_limit()` before entity creation
- **UI:** Use `get_usage_summary()` for progress bars/warnings

## Key Files

| File | Purpose |
|------|---------|
| `/core/services/trial_limits.py` | Service implementation (~400 lines) |
| `/core/models/enums/user_enums.py` | UserRole enum with `is_subscriber()` |
| `/docs/decisions/ADR-018-user-roles-four-tier-system.md` | Role system ADR |

## See Also

- **ADR-018:** User Roles Four-Tier System
- **CLAUDE.md:** User Roles & Authentication section
