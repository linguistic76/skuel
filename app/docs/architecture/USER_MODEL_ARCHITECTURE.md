---
title: User Model Architecture
updated: 2026-01-04
status: current
category: architecture
tags: [architecture, model, user, roles, authentication]
related: [ADR-018-user-roles-four-tier-system.md, ADR-022-graph-native-authentication.md]
---

# User Model Architecture

## Overview

SKUEL uses a **three-tier architecture** for user models following the "Pydantic at the edges" pattern. This ensures clean separation between external validation, data transfer, and core business logic.

**Recent Updates (2025)**: Complete refactoring to align with [THREE_TIER_ARCHITECTURE.md](./THREE_TIER_ARCHITECTURE.md):
- User domain model now inherits from `BaseEntity`
- Clear separation between frozen domain models, mutable DTOs, and Pydantic schemas
- Unified context system replaced with proper DTO pattern

## Graph-Native Authentication
*Added: January 2026*

SKUEL uses **graph-native authentication** - all authentication state lives in Neo4j with no external dependencies.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    GraphAuthService                          │
│   (core/auth/graph_auth.py)                                  │
├─────────────────────────────────────────────────────────────┤
│  sign_up()     → Creates User node with bcrypt password_hash │
│  sign_in()     → Verifies password, creates Session node     │
│  sign_out()    → Invalidates Session node                    │
│  validate()    → Checks Session validity                     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     Neo4j Graph                              │
├─────────────────────────────────────────────────────────────┤
│  (User)-[:HAS_SESSION]->(Session)                            │
│  (User)-[:HAD_AUTH_EVENT]->(AuthEvent)                       │
│  (User)-[:HAS_RESET_TOKEN]->(PasswordResetToken)             │
└─────────────────────────────────────────────────────────────┘
```

### Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| **GraphAuthService** | `core/auth/graph_auth.py` | Main authentication service |
| **SessionBackend** | `adapters/persistence/neo4j/session_backend.py` | Neo4j session storage |
| **Session** | `core/models/auth/session.py` | Session frozen dataclass |
| **AuthEvent** | `core/models/auth/auth_event.py` | Audit trail events |
| **PasswordResetToken** | `core/models/auth/password_reset_token.py` | Admin-generated reset tokens |

### Security Features

- **Bcrypt password hashing** - Passwords stored as bcrypt hashes in Neo4j
- **Session tokens** - 32-byte secure random tokens with 30-day expiry
- **Rate limiting** - 5 failed attempts = 15-minute lockout (tracked via graph queries)
- **Audit trail** - All auth events stored as AuthEvent nodes
- **HTTP-only cookies** - Session tokens stored in signed cookies
- **Admin password reset** - No email service required, tokens valid for 1 hour

### Authentication Flow

```python
# Registration
result = await graph_auth.sign_up(
    email="user@example.com",
    password="secure123",
    username="newuser",
    display_name="New User"
)
# Creates: (User) node with password_hash

# Login
result = await graph_auth.sign_in(
    email="user@example.com",
    password="secure123",
    ip_address="127.0.0.1",
    user_agent="Browser/1.0"
)
# Creates: (User)-[:HAS_SESSION]->(Session)
# Returns: { user_uid, session_token }

# Session stored in cookie
set_current_user(request, user_uid, session_token)

# Logout
await graph_auth.sign_out(session_token, ip_address, user_agent)
# Updates: Session.is_valid = false
# Creates: (User)-[:HAD_AUTH_EVENT]->(AuthEvent{type: LOGOUT})
```

### Password Reset (Admin-Initiated)

```python
# Admin generates reset token
token = await graph_auth.admin_generate_reset_token(
    user_uid="user_johndoe",
    admin_uid="user_admin",
    ip_address="...",
    user_agent="..."
)
# Creates: (User)-[:HAS_RESET_TOKEN]->(PasswordResetToken)

# User resets password with token
await graph_auth.reset_password_with_token(
    token_value=token,
    new_password="newsecure123",
    ip_address="...",
    user_agent="..."
)
# Updates: User.password_hash, invalidates token
```

**See:** [ADR-022: Graph-Native Authentication](/docs/decisions/ADR-022-graph-native-authentication.md)

---

## User Roles: Four-Tier Authorization System
*Added: December 2025*

SKUEL uses a four-tier role system stored in Neo4j:

| Role | Level | Description | Key Permissions |
|------|-------|-------------|-----------------|
| **REGISTERED** | 0 | Free trial | Unlimited curriculum + activities |
| **MEMBER** | 1 | Paid subscription | Unlimited access |
| **TEACHER** | 2 | Content creator | Member + create/edit KU, LP, MOC |
| **ADMIN** | 3 | System manager | Teacher + user management, password reset |

**Key Design Decisions:**
- Roles stored in Neo4j `User.role` field
- Hierarchy-aware: `user.role.has_permission(UserRole.TEACHER)` checks level
- Admin-only role management via `/api/admin/users/*` routes
- Admin password reset via `/api/admin/users/{uid}/reset-password`
- New users default to REGISTERED, existing users grandfathered as MEMBER

**Usage in Code:**
```python
# Check permissions
if user.can_create_curriculum():  # TEACHER+
    await ku_service.create(...)

# Route protection (use named function, not lambda - SKUEL012)
def get_user_service():
    return services.user_service

@require_admin(get_user_service)
async def admin_only_route(request, current_user):
    ...
```

**See:** [ADR-018: User Roles](/docs/decisions/ADR-018-user-roles-four-tier-system.md)

---

## 🏗️ Architecture: Three-Tier System with Principle Awareness

```
┌─────────────────────────────┐
│    External Layer           │
│    user_schemas.py          │
│    (Pydantic validation)    │
└──────────┬──────────────────┘
           │
┌──────────▼──────────────────┐
│    Transfer Layer           │
│    user_dto.py              │
│    (Mutable DTOs)           │
│  + Principle Awareness      │
└──────────┬──────────────────┘
           │
┌──────────▼──────────────────┐
│    Core Domain              │
│    user.py                  │
│    (Frozen, immutable)      │
│  + principle_pure.py        │
└─────────────────────────────┘
```

**New in 2025**: Principle integration adds a motivational layer that connects user values with their goals and habits.

## 📁 File Organization

### 1. **user.py** - Core Domain Model
**Purpose**: Immutable domain model representing the core user entity

```python
@dataclass(frozen=True)
class User(BaseEntity):
    """
    Core user domain model - frozen and immutable.
    Inherits from BaseEntity for consistency.
    """
    # Identity (title used as username from BaseEntity)
    email: str = ""
    display_name: str = ""

    # Authorization (December 2025)
    role: UserRole = UserRole.REGISTERED  # Four-tier: REGISTERED < MEMBER < TEACHER < ADMIN

    # Preferences and state
    preferences: UserPreferences
    active_entity_uids: set[str]
    interests: list[str]

    # Role helper methods
    def has_permission(self, required: UserRole) -> bool: ...
    def can_create_curriculum(self) -> bool: ...  # TEACHER+
    def can_manage_users(self) -> bool: ...       # ADMIN only
    def is_subscriber(self) -> bool: ...          # MEMBER+ (paid)
    def is_trial(self) -> bool: ...               # REGISTERED only

    # Delegated responsibilities:
    # - Progress → UnifiedProgress
    # - Activities → CalendarTrackable entities
    # - Relationships → unified_relationships.py
```

**Key Features:**
- Frozen dataclass (immutable)
- Inherits from `BaseEntity`
- Username stored in `title` field
- **Role-based authorization** via `UserRole` enum (REGISTERED/MEMBER/TEACHER/ADMIN)
- Delegates progress tracking to `UnifiedProgress`
- Clean separation of concerns

### 2. **user_dto.py** - Data Transfer Objects
**Purpose**: Mutable DTOs for transferring user data between layers

```python
@dataclass
class UnifiedUserContextDTO(BaseDTO):
    """
    Mutable DTO for user context transfer.
    Used by services needing user context information.
    Now includes principle awareness for motivation tracking.
    """
    user_uid: str
    username: str
    context_type: str

    # Principle Awareness (NEW)
    core_principle_uids: list[str]  # User's core values/principles
    current_principle_focus: str | None  # Principle being actively practiced
    principle_priorities: dict[str, float]  # principle_uid -> importance (0-1)
    principle_conflicts: list[tuple[str, str]]  # Known principle conflicts

    # Flexible fields for different services
    learning_level: LearningLevel
    active_entity_uids: set[str]
    interests: list[str]
    # ... services use only what they need
```

**Key Features:**
- Mutable dataclass
- Inherits from `BaseDTO`
- Can be modified during transfer
- No business logic
- Services use only needed fields

### 3. **user_schemas.py** - Pydantic Schemas
**Purpose**: External validation and serialization at API boundaries

```python
class UserPreferencesSchema(BaseModel):
    """Pydantic schema for API validation"""
    learning_level: LearningLevel  # Uses enum directly
    preferred_time_of_day: TimeOfDay
    energy_pattern: dict[TimeOfDay, EnergyLevel]
```

**Key Features:**
- Pydantic models for API boundaries
- Uses enums directly (not literals)
- Input validation and serialization
- Never used in core domain

## 🔄 Data Flow

### Creating a User

```python
# 1. External Request (Pydantic validates)
request = UserCreateRequest(
    username="john_doe",
    email="john@example.com",
    learning_level=LearningLevel.INTERMEDIATE
)

# 2. Convert to DTO for service layer
dto = UserDTO(
    uid=generate_uid(),
    username=request.username,
    email=request.email,
    # ... transform as needed
)

# 3. Create domain model
user = User(
    uid=dto.uid,
    title=dto.username,  # Username in title field
    email=dto.email,
    preferences=UserPreferences(
        learning_level=dto.learning_level
    )
)

# 4. Return response (domain → DTO → Pydantic)
response = UserResponse.from_domain(user)
```

### User Context Flow

```python
# 1. Load user domain model
user = user_repository.get(user_id)

# 2. Create context DTO for service
context = UnifiedUserContextDTO(
    uid=f"ctx_{uuid4()}",
    user_uid=user.uid,
    username=user.title,  # From title field
    context_type="search",
    learning_level=user.preferences.learning_level
)

# 3. Service uses only needed fields
search_results = search_service.search(
    query=query,
    user_level=context.learning_level,
    interests=context.interests
)
```

## 🎯 Key Design Principles

### 1. Immutable Domain Models
- `User` is a frozen dataclass
- Cannot be accidentally modified
- Thread-safe and cacheable

### 2. Proper Inheritance
- `User` inherits from `BaseEntity`
- `UnifiedUserContextDTO` inherits from `BaseDTO`
- Consistent with other domain models

### 3. Clear Separation
- **Domain**: Business logic and rules
- **DTO**: Data transfer and transformation
- **Schema**: External validation

### 4. Delegation Pattern
- User doesn't track progress directly → `UnifiedProgress`
- User doesn't manage activities → `CalendarTrackable` entities
- User doesn't handle relationships → `unified_relationships.py`
- User doesn't define principles → `principle_pure.py`

## 🔧 Technical Details

### User Model Features

```python
# Factory functions
user = create_user(
    username="jane",
    email="jane@example.com",
    display_name="Jane Doe"
)

# Service context creation
context = UserServiceContext.from_user(user)

# User statistics (computed, not stored)
stats = UserStatistics(
    total_active_items=len(user.active_entity_uids),
    # ... computed metrics
)
```

### Context Builder Pattern

```python
builder = UserContextBuilder()
context = (builder
    .with_user(user.uid, user.title)
    .with_type("learning")
    .with_learning_profile(
        level=user.preferences.learning_level
    )
    .with_principles(
        core_principles=["growth", "discipline"],
        current_focus="discipline"
    )
    .build())
```

### Principle-Aware Context

```python
# User context now includes principle awareness
context = UnifiedUserContextDTO(
    user_uid=user.uid,
    username=user.title,
    context_type='motivation',
    # Principle fields
    core_principle_uids=["principle_growth_123", "principle_discipline_456"],
    current_principle_focus="principle_discipline_456",
    principle_priorities={
        "principle_growth_123": 0.9,
        "principle_discipline_456": 0.8
    }
)

# Services can use principle information
if context.has_principles:
    primary = context.primary_principle  # Highest priority
    active = context.get_active_principles(threshold=0.7)  # High importance
```

## 🚀 Migration from Old Architecture

### What Changed

| Old | New | Reason |
|-----|-----|--------|
| `user_pure.py` | `user.py` | Renamed, now inherits from BaseEntity |
| `UserPure` class | `User` class | Proper domain model naming |
| `user.py` (re-exports) | Removed | Was just re-exporting, not needed |
| `user_context_simplified.py` | `user_dto.py` | Proper DTO pattern |
| `UnifiedUserContext` | `UnifiedUserContextDTO` | Clear DTO naming |
| Literal types in schemas | Direct enum usage | Standardization |

### Key Improvements

1. **Consistent Architecture**: Follows three-tier pattern
2. **Proper Inheritance**: Uses base classes from `base_models_consolidated.py`
3. **Clear Naming**: DTOs named as DTOs, domain models clear
4. **Type Safety**: Enums used directly, no duplicate literals
5. **Immutability**: Domain models frozen, DTOs mutable

## 📊 Performance Characteristics

### Domain Model (user.py)
- **Immutable**: Thread-safe, cacheable
- **Lightweight**: Delegates to specialized models
- **Focused**: Only core user data

### DTOs (user_dto.py)
- **Flexible**: Can be modified during transfer
- **Service-specific**: Each service uses only needed fields
- **Efficient**: No unnecessary data transfer

### Schemas (user_schemas.py)
- **Validation**: At boundaries only
- **Serialization**: Automatic enum handling
- **Type-safe**: Direct enum usage

## 🔒 Why This Architecture

### Benefits

1. **Type Safety**: Clear types at each layer
2. **Maintainability**: Each layer has single responsibility
3. **Performance**: Immutable models are cacheable
4. **Flexibility**: DTOs can transform data as needed
5. **Consistency**: Same pattern across all domains

### Trade-offs

- More files (3 instead of 1)
- Explicit transformations needed
- Must maintain consistency across layers

But these trade-offs are worth it for:
- Clear architecture
- Better testing
- Easier maintenance
- Type safety

## 🎯 Usage Guidelines

### DO ✅
- Use `User` for core business logic
- Use `UnifiedUserContextDTO` for service communication
- Use schemas for API validation
- Keep domain models frozen
- Use factory functions for creation
- Include principles when creating user context for motivation-aware services
- Use `PrinciplePure` for defining user values

### DON'T ❌
- Mix Pydantic in domain models
- Mutate domain models
- Use DTOs for business logic
- Skip validation at boundaries
- Access user.username (use user.title)

## 🔄 Shared Learning Context (v2.0)

### Overview

The **SharedLearningContext** system provides a unified context that flows between all learning services, eliminating duplicate computations and ensuring consistency.

### Architecture

```python
from core.services.shared_context import SharedLearningContext, ContextManager, get_context_manager

@dataclass
class SharedLearningContext:
    """
    Shared context that flows between all learning services.
    This eliminates duplicate computations and ensures consistency.
    """
    user_uid: str

    # From ContentAnalysisService
    content_metadata: Optional[Dict[str, Any]]
    content_keywords: list[str]
    reading_time_estimate: float

    # From PedagogicalService
    pedagogical_context: Optional[Any]
    learning_recommendation: Optional[str]
    needs_intervention: bool

    # From LearningBridge
    available_units: list[str]
    progress_summary: Optional[Dict[str, Any]]
    recommended_next: Optional[str]

    # From PathOrchestratorService
    active_paths: list[Any]
    path_synergies: list[Any]
    unified_progress: float
    principle_alignment_scores: dict[str, float]  # How goals/habits align with principles

    # From ProgressReviewService
    daily_review: Optional[Any]
    weekly_insights: Optional[Any]
    at_risk_goals: list[str]

    # From AskesisService
    learning_state: Optional[Dict[str, Any]]
    current_learning_path: Optional[Any]
    guidance_provided: Optional[str]
```

### Usage Patterns

#### 1. Service Updates Context
```python
# In ContentAnalysisService
context_manager = get_context_manager()
context_manager.update(user_uid, {
    "content_metadata": metadata,
    "content_keywords": keywords,
    "reading_time_estimate": 15.5
})
```

#### 2. Service Reads Context
```python
# In AskesisService
context = context_manager.get_or_create(user_uid)
if context.pedagogical_context:
    # Use pedagogical insights for guidance
    guidance = generate_guidance_with_pedagogy(context.pedagogical_context)
```

#### 3. Coordinator Manages Flow
```python
# In LearningCoordinator
async def process_learning_request(self, user_uid, request, user_context):
    # Each service updates shared context
    await self.content.analyze_content(content_uid, user_uid)  # → Updates context
    self.pedagogy.analyze_learning_context(...)  # → Updates context

    # Later services read enriched context
    context = self.context_manager.get_or_create(user_uid)
    guidance = await self.askesis.generate_guidance(context)  # Uses full context
```

### Benefits

1. **Eliminates Redundancy**: Content analyzed once, shared with all services
2. **Ensures Consistency**: All services work from same state
3. **Enables Rich Integration**: Services can leverage insights from other services
4. **Improves Performance**: No duplicate API calls or computations
5. **Simplifies Debugging**: Single source of truth for user state

### Context Lifecycle

1. **Creation**: Context created on first request for user
2. **Updates**: Services update their portions as they process
3. **Merging**: Context manager handles merging updates
4. **Cleanup**: Stale contexts removed after 24 hours
5. **Persistence**: Context can be persisted for long-term tracking

### Integration with UnifiedUserContextDTO

The `SharedLearningContext` complements the `UnifiedUserContextDTO`:

- **UnifiedUserContextDTO**: User profile, preferences, and **principles** (input)
- **SharedLearningContext**: Service-computed state (output/working state)

Principles flow through the system:
```python
# User context includes principles
user_context = UnifiedUserContextDTO(
    user_uid="123",
    core_principle_uids=["growth", "discipline"],
    current_principle_focus="discipline"
)

# Services assess principle alignment
if "discipline" in user_context.core_principle_uids:
    # Suggest habits that practice discipline
    habits = generate_discipline_aligned_habits()
```

```python
# UnifiedUserContextDTO flows IN to services
user_context = UnifiedUserContextDTO(user_uid="123", ...)

# SharedLearningContext accumulates service outputs
shared_context = SharedLearningContext(user_uid="123", ...)
shared_context.content_metadata = analyze_result  # Service adds data
```

## 📚 Related Documentation

- [THREE_TIER_ARCHITECTURE.md](./THREE_TIER_ARCHITECTURE.md) - Overall pattern
- [MODEL_ARCHITECTURE.md](./MODEL_ARCHITECTURE.md) - Model organization
- [BASE_MODELS_MIGRATION.md](./BASE_MODELS_MIGRATION.md) - Migration guide
- [LEARNING_API_DOCUMENTATION.md](./LEARNING_API_DOCUMENTATION.md) - Learning coordinator APIs

## 🎯 Event-Driven Service Integration (v2.1)

### Overview

The learning services now communicate through an event-driven architecture, enabling reactive and loosely-coupled interactions.

### Event Bus Architecture

```python
from core.services.learning_events import (
    LearningEventBus,
    LearningEvent,
    LearningEventType,
    get_event_bus
)

# Singleton event bus for all services
event_bus = get_event_bus()

# Services publish events when state changes
event = LearningEvent(
    event_type=LearningEventType.STEP_COMPLETED,
    user_uid="user_123",
    entity_uid="step_456",
    timestamp=datetime.now(),
    data={"mastery": 0.85},
    source_service="LearningBridge"
)
event_bus.publish(event)

# Services subscribe to relevant events
event_bus.subscribe(
    LearningEventType.STEP_COMPLETED,
    handle_step_completed,
    "PedagogicalService"
)
```

### Event Flow Between Services

```
User Action
    └→ LearningBridge
        └→ Publishes: PROGRESS_UPDATED
            ├→ PedagogicalService (subscriber)
            │   └→ May publish: INTERVENTION_NEEDED
            ├→ PathOrchestrator (subscriber)
            │   └→ May publish: STEP_UNLOCKED
            └→ ProgressReviewService (subscriber)
                └→ Updates analytics

Intervention Flow:
    INTERVENTION_NEEDED event
        └→ LearningCoordinator (subscriber)
            └→ Triggers help content
            └→ May adjust difficulty
            └→ Publishes: LEARNING_PAUSED
```

### Service Event Integration

Each service now integrates with the event bus:

#### LearningBridge
```python
class LearningBridge:
    def __init__(self, event_bus=None):
        self.event_bus = event_bus or get_event_bus()

    def update_progress(self, user_uid, unit_uid, completion, mastery):
        # Update progress...

        # Publish events
        self.event_bus.publish(LearningEvent(
            event_type=LearningEventType.PROGRESS_UPDATED,
            user_uid=user_uid,
            entity_uid=unit_uid,
            data={"completion": completion, "mastery": mastery}
        ))

        if completion >= 100:
            self.event_bus.publish(LearningEvent(
                event_type=LearningEventType.STEP_COMPLETED,
                ...
            ))
```

#### PedagogicalService
```python
class PedagogicalService:
    def __init__(self, event_bus=None):
        self.event_bus = event_bus or get_event_bus()
        self._setup_event_subscriptions()

    def _setup_event_subscriptions(self):
        self.event_bus.subscribe(
            LearningEventType.STEP_COMPLETED,
            self._on_step_completed,
            "PedagogicalService"
        )

    def _on_step_completed(self, event):
        # Check mastery and trigger interventions if needed
        if event.data.get("mastery", 0) < 0.7:
            self.event_bus.publish(LearningEvent(
                event_type=LearningEventType.REVIEW_NEEDED,
                ...
            ))
```

### Event-Driven Benefits

1. **Loose Coupling**: Services don't directly call each other
2. **Real-time Reactions**: Immediate response to state changes
3. **Extensibility**: Easy to add new event types and handlers
4. **Audit Trail**: Event history provides learning analytics
5. **Resilience**: Services can operate independently

### Event Types Reference

#### Progress Events
- `STEP_COMPLETED`: Learning step finished
- `PATH_COMPLETED`: Entire path completed
- `MASTERY_ACHIEVED`: Mastery threshold reached
- `PROGRESS_UPDATED`: Any progress change

#### Path Events
- `PATH_CREATED`: New learning path created
- `PATH_MODIFIED`: Path structure changed
- `STEP_UNLOCKED`: New step available

#### Learning State Events
- `LEARNING_STARTED`: Session began
- `LEARNING_PAUSED`: Session paused
- `LEARNING_RESUMED`: Session resumed

#### Intervention Events
- `REVIEW_NEEDED`: Content needs review
- `INTERVENTION_NEEDED`: Help required

### Integration with SharedLearningContext

The event system complements SharedLearningContext:

- **SharedLearningContext**: Stores computed state
- **Event Bus**: Triggers reactive updates

```python
# Service updates context
context_manager.update(user_uid, {"mastery": 0.85})

# Then publishes event
event_bus.publish(LearningEvent(
    event_type=LearningEventType.MASTERY_ACHIEVED,
    ...
))

# Other services react to event and may read context
def _on_mastery_achieved(self, event):
    context = context_manager.get_or_create(event.user_uid)
    # Use both event data and shared context
```

## 🎯 Principle Integration (v3.0)

### Overview

Principles provide the motivational foundation for the entire user model, answering "WHY" users pursue goals and maintain habits.

### Principle Model

```python
@dataclass(frozen=True)
class PrinciplePure:
    """
    Core values that guide behavior and decision-making.
    Principles sit above goals and habits as motivational drivers.
    """
    uid: str
    label: str  # e.g., "Continuous Learning", "Health First"
    description: str
    why_matters: str  # Personal importance
    category: PrincipleCategory
    strength: PrincipleStrength  # CORE, STRONG, MODERATE, etc.
    priority_rank: int  # 1-10, higher = more important

    # Related entities
    supporting_goal_uids: list[str]
    supporting_habit_uids: list[str]
```

### Principle-Aware User Context

```python
# UnifiedUserContextDTO now includes principle awareness
class UnifiedUserContextDTO(BaseDTO):
    # ... existing fields ...

    # Principle Awareness
    core_principle_uids: list[str]
    current_principle_focus: str | None
    principle_priorities: dict[str, float]
    principle_conflicts: list[tuple[str, str]]

    # Helper methods
    @property
    def has_principles(self) -> bool:
        return bool(self.core_principle_uids)

    @property
    def primary_principle(self) -> str | None:
        """Get highest priority principle"""
        if self.principle_priorities:
            return max(self.principle_priorities.items(), key=lambda x: x[1])[0]
        return self.core_principle_uids[0] if self.core_principle_uids else None

    def get_active_principles(self, threshold: float = 0.7) -> list[str]:
        """Get principles above importance threshold"""
        return [
            p_uid for p_uid, importance in self.principle_priorities.items()
            if importance >= threshold
        ]
```

### Principle Alignment Service

```python
class PrincipleAlignmentService:
    """
    Service for managing principles and their alignment with goals/habits.
    Provides the motivational intelligence layer.
    """

    async def assess_goal_alignment(self, goal_uid: str, user_uid: str) -> AlignmentAssessment:
        """Assess how well a goal aligns with user's principles"""

    async def generate_principle_based_habits(self, principle_uid: str) -> list[HabitPure]:
        """Generate habits that practice a specific principle"""

    async def resolve_principle_conflict(self, p1_uid: str, p2_uid: str) -> ConflictResolution:
        """Suggest resolution when principles conflict"""
```

### Integration Flow

```
User defines principle: "Continuous Learning"
         ↓
System suggests aligned goals:
- "Master Machine Learning"
- "Read 52 books this year"
         ↓
System generates supporting habits:
- "Daily 30-min learning session"
- "Weekly deep dive study"
         ↓
Progress tracking shows principle alignment:
- Goal progress: 65%
- Principle alignment: 92% ✨
```

### Benefits of Principle Integration

1. **Deeper Motivation**: Goals connected to values are more meaningful
2. **Better Decision Making**: Principles guide choices when goals conflict
3. **Authentic Progress**: Success measured by value alignment, not just completion
4. **Personalized Guidance**: AI can provide value-based recommendations
5. **Long-term Consistency**: Principles persist even as goals change

## Current Implementation Status

✅ **Completed**:
- User inherits from BaseEntity
- UnifiedUserContextDTO is proper DTO with principle awareness
- PrinciplePure domain model created
- GoalPure includes principle integration
- HabitPure includes principle practice
- PrincipleAlignmentService for motivation tracking
- Schemas use enums directly
- Three-tier architecture implemented
- SharedLearningContext for service integration (v2.0)
- LearningCoordinator for orchestration (v2.0)
- Event-driven architecture with LearningEventBus (v2.1)
- All core services integrated with event bus
- PedagogicalService provides reactive interventions
- Principle integration architecture (v3.0)
- All tests passing

The user model architecture now fully conforms to the three-tier "Pydantic at the edges" pattern, with enhanced service integration through SharedLearningContext and reactive event-driven communication, ensuring clean separation of concerns and type safety throughout the system.