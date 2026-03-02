---
title: User Architecture — User Model, Auth, Roles, and UserContext
updated: 2026-03-03
status: current
category: architecture
tags:
- architecture
- unified
- user
- mega-query
- authentication
- roles
related:
- ADR-015
- ADR-018
- ADR-022
- ADR-029
related_skills:
- user-context-intelligence
---

# User Architecture

SKUEL's user system has two distinct objects that serve different purposes:

| Object | Location | Purpose |
|--------|----------|---------|
| `User` | `core/models/user/user.py` | Frozen domain model — identity, preferences, role |
| `UserContext` | `core/services/user/unified_user_context.py` | Runtime state — everything a user has done (~240 fields) |

`User` is what a user *is*. `UserContext` is what they *have* — all their entities, relationships, and graph neighbourhoods in one object, built by a single MEGA-QUERY.

---

## The `User` Domain Model

**File:** `core/models/user/user.py`

```
User (frozen dataclass, inherits BaseEntity)
├── Identity:     email, display_name
├── Role:         role: UserRole  (REGISTERED / MEMBER / TEACHER / ADMIN)
├── Preferences:  preferences: UserPreferences
│   ├── learning_level, preferred_time_of_day, available_minutes_daily
│   └── energy_pattern: dict[TimeOfDay, EnergyLevel]
└── State:        active_entity_uids: set[str], interests: list[str]
```

Username is stored in the inherited `title` field from `BaseEntity`. Use `user.title`, not `user.username`.

**Role methods:**
```python
user.has_permission(UserRole.TEACHER)  # hierarchy-aware check
user.can_create_curriculum()           # TEACHER+
user.can_manage_users()                # ADMIN only
user.is_subscriber()                   # MEMBER+ (paid)
user.is_trial()                        # REGISTERED only
```

### Three-Tier Architecture

```
External   user_schemas.py   Pydantic — API boundary validation
Transfer   user_dto.py       Mutable DTOs for service communication
Core       user.py           Frozen domain model — this is the User
```

---

## Graph-Native Authentication

All auth state lives in Neo4j. No external auth service.

```
┌──────────────────────────────────────────────────────────┐
│                    GraphAuthService                       │
│   (core/auth/graph_auth.py)                              │
├──────────────────────────────────────────────────────────┤
│  sign_up()   → User node with bcrypt password_hash       │
│  sign_in()   → Verifies password, creates Session node   │
│  sign_out()  → Invalidates Session node                  │
│  validate()  → Checks Session validity                   │
└──────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│                     Neo4j Graph                          │
├──────────────────────────────────────────────────────────┤
│  (User)-[:HAS_SESSION]->(Session)                        │
│  (User)-[:HAD_AUTH_EVENT]->(AuthEvent)                   │
│  (User)-[:HAS_RESET_TOKEN]->(PasswordResetToken)         │
└──────────────────────────────────────────────────────────┘
```

**Key components:**

| Component | Location | Purpose |
|-----------|----------|---------|
| `GraphAuthService` | `core/auth/graph_auth.py` | Main auth service |
| `SessionBackend` | `adapters/persistence/neo4j/session_backend.py` | Neo4j session storage |
| `Session` | `core/models/auth/session.py` | Session frozen dataclass |
| `AuthEvent` | `core/models/auth/auth_event.py` | Audit trail |
| `PasswordResetToken` | `core/models/auth/password_reset_token.py` | Admin-generated reset tokens |

**Security:**
- Bcrypt password hashing stored in Neo4j
- 32-byte secure random session tokens with 30-day expiry
- 5 failed attempts → 15-minute lockout (tracked via graph queries)
- HTTP-only signed cookies
- Admin-initiated password reset — no email service required, tokens valid 1 hour

**Auth flows:**
```python
# Registration
await graph_auth.sign_up(email, password, username, display_name)
# → Creates (User) node with password_hash

# Login
result = await graph_auth.sign_in(email, password, ip_address, user_agent)
# → Creates (User)-[:HAS_SESSION]->(Session)
# → Returns { user_uid, session_token }
set_current_user(request, user_uid, session_token)

# Password reset (admin-initiated)
token = await graph_auth.admin_generate_reset_token(user_uid, admin_uid, ...)
await graph_auth.reset_password_with_token(token_value, new_password, ...)
```

**See:** [ADR-022: Graph-Native Authentication](/docs/decisions/ADR-022-graph-native-authentication.md)

---

## User Roles

Four-tier system stored in `User.role` (Neo4j field):

| Role | Level | Key Permissions |
|------|-------|-----------------|
| `REGISTERED` | 0 | Free trial — unlimited curriculum + activities |
| `MEMBER` | 1 | Paid subscription — unlimited access |
| `TEACHER` | 2 | Member + create/edit KU, LP, MOC |
| `ADMIN` | 3 | Teacher + user management, password reset |

**Route protection:**
```python
# Use named function, not lambda — SKUEL012
def get_user_service():
    return services.user_service

@require_admin(get_user_service)
async def admin_only_route(request, current_user):
    ...
```

**See:** [ADR-018: User Roles](/docs/decisions/ADR-018-user-roles-four-tier-system.md)

---

## UserContext — The User's Complete Runtime State

**The problem:** Understanding a user without `UserContext` requires 15+ separate queries across all domains. Stats are disconnected from UIDs. Intelligence services can't see across domain boundaries.

**The solution:** One object (~240 fields), built by one query (MEGA-QUERY), consumed by all intelligence services. Stats are computed FROM UIDs — no duplication, no drift.

```
Graph (Neo4j) → MEGA-QUERY → UserContext → UserContextIntelligence → Recommendations
                  ^                              ^
             one query                   "What should I work on?"
```

### Two Depths

| Depth | Method | Fields | When to use |
|-------|--------|--------|-------------|
| **Standard** | `build(user_uid)` | UIDs only (~150) | API responses, ownership checks |
| **Rich** | `build_rich(user_uid, window="30d")` | UIDs + full entities + graph (~240) | Intelligence, daily planning |

`window` controls how far back the activity-window CALL{} blocks look (`"7d"`, `"14d"`, `"30d"`, `"90d"`).

```python
context.is_rich_context      # bool — False for standard, True for rich
context.require_rich_context("operation_name")  # raises ValueError if standard
```

### When to Use UserContext vs Domain Services

```
Need user state data?
├─ Intelligence / planning (cached analysis)
│  → UserContext.build_rich() then pass context into service
│
├─ Real-time API endpoint (fresh data)
│  → ku_service.get_ready_to_learn_for_user(user_uid)
│
└─ Cross-domain graph traversal
   → service.relationships.get_related_uids(...)
```

Two clear paths (ADR-029): **context methods** for cached intelligence analysis, **service methods** for fresh real-time API responses. No intermediate layers.

### UserContext Powers Intelligence

```
UserContext (state)                  UserContextIntelligence (synthesis)
├── active_task_uids            →    get_ready_to_work_on_today()
├── goal_progress               →    calculate_life_path_alignment()
├── habit_streaks               →    get_cross_domain_synergies()
├── knowledge_mastery           →    get_optimal_next_learning_steps()
└── 236 more fields             →    get_schedule_aware_recommendations()
```

Domain intelligence services (`TasksIntelligenceService`, etc.) analyse single domains. `UserContextIntelligence` synthesises across all domains.

---

## UserContextBuilder — 4-Module Architecture

**Location:** `core/services/user/`

```
user_context_builder.py    (~331 lines)   Orchestration — build() vs build_rich()
user_context_queries.py    (~1000 lines)  MEGA_QUERY + CONSOLIDATED_QUERY
user_context_extractor.py  (~351 lines)   Result parsing + relationship extraction
user_context_populator.py  (~235 lines)   Context field population
```

**Primary API:**
```python
class UserContextBuilder:
    async def build(self, user_uid: str) -> Result[UserContext]:
        """Standard context — UIDs only."""

    async def build_rich(
        self,
        user_uid: str,
        min_confidence: float = 0.7,
        window: str = "30d",
    ) -> Result[UserContext]:
        """Rich context — UIDs + entities + graph neighbourhoods."""
```

**Queries:**
```python
class UserContextQueryExecutor:
    async def execute_mega_query(self, user_uid, min_confidence) -> Result[dict]:
        """Single query: UIDs AND rich entity data with graph neighbourhoods."""

    async def execute_consolidated_query(self, user_uid) -> Result[dict]:
        """Optimised standard context (UIDs only)."""
```

**Population methods** (`UserContextPopulator`):

| Method | What it populates | Path |
|--------|-------------------|------|
| `populate_standard_fields()` | `active_task_uids`, `active_goal_uids`, `habit_streaks`, etc. | Both |
| `populate_entities_rich()` | `entities_rich` dict (9 keys) | Rich only |
| `populate_user_properties()` | `learning_level`, `preferred_time`, `energy_level`, etc. | Both |
| `populate_life_path()` | `life_path_uid`, `life_path_alignment_score` | Both |
| `populate_progress_metrics()` | `overall_progress` | Both |
| `populate_derived_fields()` | `tasks_by_goal`, `at_risk_habits`, `blocked_task_uids` | Rich only |
| `populate_activity_report()` | `latest_activity_report_*` fields | Both |
| `populate_cross_domain_insights()` | `cross_domain_insights` | Rich only |

---

## MEGA-QUERY Architecture

The MEGA-QUERY in `user_context_queries.py` fetches UIDs and full entity data with graph neighbourhoods in a single Neo4j round-trip.

`build_rich()` extends MEGA-QUERY with six activity-window CALL{} blocks — one per Activity Domain — and populates `context.entities_rich`.

### `entities_rich` — The Unified Rich Field

`entities_rich: dict[str, list[dict]]` — populated by `build_rich()`. All entries share the shape `{entity: {...}, graph_context: {...}}`:

| Key | Contents |
|-----|----------|
| `"tasks"`, `"goals"`, `"habits"`, `"events"`, `"choices"`, `"principles"` | 6 Activity Domains — active always included, completed included if touched within `window` |
| `"learning_paths"` | LP entities (normalised from `paths_rich`) |
| `"learning_steps"` | LS entities (normalised from `steps_rich`) |
| `"ku"` | Window-engaged KUs only (mastered or viewed within window); `graph_context.interaction_type` = `"mastered"` or `"viewed"` |

`enrolled_paths_rich` and `active_learning_steps_rich` remain populated for backward compat (same data, old shape). `knowledge_units_rich` (all KUs, static dict) also remains.

### ActivityReport Fields — Both Paths

Both CONSOLIDATED_QUERY (standard) and MEGA-QUERY (rich) fetch the latest `ActivityReport` and populate the same fields:

| UserContext Field | What |
|-----------------|------|
| `latest_activity_report_uid` | UID of the most recent report |
| `latest_activity_report_period` | `"7d"` / `"14d"` / `"30d"` / `"90d"` |
| `latest_activity_report_generated_at` | When it was generated |
| `latest_activity_report_content` | The AI synthesis or human text |
| `latest_activity_report_user_annotation` | User's own annotation (feeds next LLM prompt) |

`latest_activity_report_user_annotation` is included in `Askesis.build_llm_context()` when the query mentions feedback/patterns/reflection keywords.

### Caching

`UserContextCache` (`core/services/user/user_context_cache.py`) caches `UserContext` with a 5-minute TTL. `ProfileHubData` (`core/services/user_stats_types.py`) is a frozen, serialisable view computed FROM `UserContext` — stats derived from UIDs, not queried separately.

---

## Consuming UserContext Correctly

**Always accept `UserContext` as a parameter — never re-query user state inside a service.**

```python
# ✅ CORRECT
async def get_advancing_goals(self, context: UserContext) -> Result[list[ContextualGoal]]:
    context.require_rich_context("get_advancing_goals")
    goals_data = context.entities_rich["goals"]
    ...

# ❌ WRONG — duplicates what MEGA-QUERY already provides
async def get_advancing_goals(self, user_uid: str) -> Result[list[ContextualGoal]]:
    goals = await self.goals_service.get_user_goals(user_uid)  # unnecessary query
    ...
```

**Orchestration layer builds context once:**
```python
context = await context_builder.build_rich(user_uid)  # ONE query
result = await service.some_method(context)            # zero re-queries
```

### Mutation Rules

`UserContext` is a read-only aggregate. Mutations happen via domain services.

| Field type | Mutable in context? |
|-----------|---------------------|
| Cache-local derived values (alignment score, workload) | Yes |
| Session state (`is_rich_context`) | Yes |
| Domain state (UIDs, progress) | **No** — go through domain service |
| Graph-sourced data (dependencies, blockers) | **No** — go through domain service |

---

## Key Files Reference

| Purpose | File |
|---------|------|
| User domain model | `core/models/user/user.py` |
| User DTOs | `core/models/user/user_dto.py` |
| User Pydantic schemas | `core/models/user/user_schemas.py` |
| Graph auth service | `core/auth/graph_auth.py` |
| Session backend | `adapters/persistence/neo4j/session_backend.py` |
| UserContext class | `core/services/user/unified_user_context.py` |
| Context builder | `core/services/user/user_context_builder.py` |
| MEGA-QUERY | `core/services/user/user_context_queries.py` |
| Extractor | `core/services/user/user_context_extractor.py` |
| Populator | `core/services/user/user_context_populator.py` |
| Context cache | `core/services/user/user_context_cache.py` |
| ProfileHubData + DomainStats | `core/services/user_stats_types.py` |
| Intelligence factory | `core/services/user/intelligence/factory.py` |
| UserContextIntelligence | `core/services/user/intelligence/core.py` |

---

## See Also

| Document | What it covers |
|----------|---------------|
| [ADR-015](/docs/decisions/ADR-015-mega-query-rich-queries-completion.md) | MEGA-QUERY architecture decision |
| [ADR-016](/docs/decisions/ADR-016-context-builder-decomposition.md) | Context builder 4-module decomposition |
| [ADR-018](/docs/decisions/ADR-018-user-roles-four-tier-system.md) | Four-tier role system |
| [ADR-022](/docs/decisions/ADR-022-graph-native-authentication.md) | Graph-native authentication |
| [ADR-029](/docs/decisions/ADR-029-graphnative-service-removal.md) | Two-path rule (context vs service) |
| [USER_CONTEXT_INTELLIGENCE.md](/docs/intelligence/USER_CONTEXT_INTELLIGENCE.md) | Intelligence methods, flagship API, daily planning |
| [AUTH_PATTERNS.md](/docs/patterns/AUTH_PATTERNS.md) | Route auth patterns, `require_authenticated_user` |
| `.claude/skills/user-context-intelligence/SKILL.md` | Implementation guidance |
