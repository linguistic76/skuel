---
title: ADR-018: Four-Tier User Role System
updated: 2026-01-04
status: current
category: decisions
tags: [adr, decisions, user, roles, authorization, authentication]
related: [UNIFIED_USER_ARCHITECTURE.md, ADR-022-graph-native-authentication.md]
---

# ADR-018: Four-Tier User Role System

**Status:** Accepted

**Date:** 2025-12-06

**Decision Type:** Pattern/Practice

**Related ADRs:**
- Related to: User Model Architecture

---

## Context

**What is the issue we're facing?**

SKUEL needed a user authorization system to support:
1. Free trial users with potential future consumption limits
2. Paid subscribers with unlimited access
3. Content creators (teachers) who can author curriculum
4. System administrators who can manage users

Key constraints:
- Graph-native authentication stores all auth data in Neo4j (January 2026)
- User data, sessions, and roles all in Neo4j (unified data model)
- Password reset is admin-initiated (no email service required)
- Role hierarchy should be clear and enforceable

---

## Decision

**Four-Tier Role Hierarchy**

| Role | Level | Description | Key Permissions |
|------|-------|-------------|-----------------|
| **REGISTERED** | 0 | Free trial | Unlimited curriculum + activities (Dec 2025 policy) |
| **MEMBER** | 1 | Paid subscription | Unlimited access |
| **TEACHER** | 2 | Content creator | Member + create/edit KU, LP, MOC |
| **ADMIN** | 3 | System manager | Teacher + user management, role assignment |

**Implementation:**

1. **UserRole Enum** (`/core/models/enums/user_enums.py`):
   - Hierarchy-aware permission checking
   - Helper methods: `is_subscriber()`, `can_create_curriculum()`, `can_manage_users()`

2. **User Model** (`/core/models/user/user.py`):
   - Added `role: UserRole` field (default: REGISTERED)
   - Delegation methods to role enum

3. **Role-Checking Decorators** (`/core/auth/roles.py`):
   - `@require_role(UserRole.ADMIN, user_service_getter)`
   - `@require_admin(user_service_getter)`
   - `@require_teacher(user_service_getter)`
   - `@require_member(user_service_getter)`

4. **Admin API Routes** (`/adapters/inbound/admin_routes.py`):
   - `GET /api/admin/users` - List users
   - `GET /api/admin/users/{uid}` - Get user details
   - `POST /api/admin/users/{uid}/role` - Change role
   - `POST /api/admin/users/{uid}/deactivate` - Deactivate
   - `POST /api/admin/users/{uid}/activate` - Activate
   - `POST /api/admin/users/{uid}/reset-password` - Generate reset token (ADMIN only)

5. **Trial Limits Service** (`/core/services/trial_limits.py`):
   - Infrastructure for consumption limits (currently all unlimited)
   - Rate limiting reserved for future use

---

## Alternatives Considered

### Alternative 1: Boolean Flags (is_admin, is_teacher)
**Description:** Use boolean flags on User model for each permission.

**Pros:**
- Simple to implement
- Easy to query

**Cons:**
- Combinatorial explosion as permissions grow
- No clear hierarchy
- Harder to add new roles

**Why rejected:** Doesn't scale, no hierarchy semantics.


### Alternative 2: External Auth Provider (e.g., Supabase, Auth0)
**Description:** Use external service for auth with role in metadata/claims.

**Pros:**
- Centralized auth
- JWT claims would include role

**Cons:**
- Couples to external provider
- Harder to migrate away
- Requires external admin API for role changes
- Splits user data across systems

**Why rejected:** SKUEL chose graph-native authentication (January 2026) for unified data model. All auth data in Neo4j simplifies operations and eliminates external dependencies.


### Alternative 3: Permission-Based (RBAC with granular permissions)
**Description:** Define granular permissions and assign sets to roles.

**Pros:**
- Very flexible
- Fine-grained control

**Cons:**
- Overkill for current needs
- Complex permission checking
- More infrastructure required

**Why rejected:** Premature complexity. Four roles sufficient for current needs.

---

## Consequences

### Positive Consequences
- ✅ Clear role hierarchy with inheritance
- ✅ Simple permission checks (`user.role.has_permission(required)`)
- ✅ Roles stored in Neo4j (unified with all user data)
- ✅ Admin-only role management (secure)
- ✅ Admin-initiated password reset (no email service required)
- ✅ Future-proof trial limits infrastructure

### Negative Consequences
- ⚠️ Role changes require admin intervention
- ⚠️ No self-service upgrade (payment integration needed later)

### Neutral Consequences
- ℹ️ Existing users grandfathered as MEMBER
- ℹ️ New users default to REGISTERED

### Risks & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Admin loses access | Low | High | Multiple admin accounts |
| Role escalation attack | Low | High | Server-side role checks, no client trust |

---

## Implementation Details

### Code Location
- **Enum:** `/core/models/enums/user_enums.py`
- **Decorators:** `/core/auth/roles.py`
- **Admin Routes:** `/adapters/inbound/admin_routes.py`
- **Trial Limits:** `/core/services/trial_limits.py`
- **Migration:** `/scripts/migrations/add_user_role.py`

### Key Code Patterns

```python
# Role enum with hierarchy
class UserRole(str, Enum):
    REGISTERED = "registered"
    MEMBER = "member"
    TEACHER = "teacher"
    ADMIN = "admin"

    def has_permission(self, required: "UserRole") -> bool:
        return self._hierarchy_level >= required._hierarchy_level

    def is_subscriber(self) -> bool:
        """MEMBER and above (paid users)."""
        return self.has_permission(UserRole.MEMBER)
```

```python
# Decorator usage (SKUEL012: use named function, not lambda)
def get_user_service():
    return services.user_service

@rt("/api/admin/users")
@require_admin(get_user_service)
@boundary_handler()
async def list_users(request, current_user):
    # Only admins reach here
    ...
```

```python
# Permission check in services
if not user.can_create_curriculum():
    return Result.fail(Errors.business(
        rule="teacher_required",
        message="Teacher role required to create curriculum"
    ))
```

### Testing Strategy
- [x] Unit tests: Role hierarchy, permission methods
- [x] Integration tests: Admin route protection
- [x] Manual testing: Role change operations

---

## Trial Limits Policy (December 2025)

Current policy: **All domains unlimited for all users.**

| Domain | Limit |
|--------|-------|
| Curriculum (KU, LS, LP) | Unlimited |
| Activity (Tasks, Goals, Habits, Events, Choices) | Unlimited |
| API rate limiting | Reserved for future |

Infrastructure exists to add limits when business requires.

---

## Future Considerations

### When to Revisit
- If payment integration added (REGISTERED → MEMBER upgrade flow)
- If more granular permissions needed
- If trial limits need enforcement

### Evolution Path
1. Payment integration: Add Stripe webhook to upgrade REGISTERED → MEMBER
2. Curriculum permissions: Teachers get create/edit, admins get delete
3. Rate limiting: Enable API call limits for abuse prevention

---

## Changelog

| Date | Author | Change | Version |
|------|--------|--------|---------|
| 2025-12-06 | Claude | Initial implementation | 1.0 |
| 2025-12-06 | Claude | Lifted all trial limits | 1.1 |
| 2026-01-04 | Claude | Updated for graph-native auth (admin password reset) | 1.2 |
