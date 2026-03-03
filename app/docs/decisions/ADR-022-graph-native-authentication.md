---
title: ADR-022: Graph-Native Authentication
updated: 2026-01-04
status: current
category: decisions
tags: [adr, decisions, authentication, security, neo4j]
related: [UNIFIED_USER_ARCHITECTURE.md, ADR-018-user-roles-four-tier-system.md]
---

# ADR-022: Graph-Native Authentication

**Status:** Accepted

**Date:** 2026-01-04

**Decision Type:** Pattern/Practice

**Related ADRs:**
- Related to: ADR-018 (User Roles)
- Related to: UNIFIED_USER_ARCHITECTURE.md

---

## Context

**What is the issue we're facing?**

SKUEL previously used Supabase for authentication, which created challenges:
1. User data split across two systems (Supabase auth + Neo4j profile)
2. External dependency for core functionality
3. Complexity in syncing user state between systems
4. Limited control over authentication behavior
5. Password reset originally required email service integration

Key requirements:
- Unified user data model (all data in Neo4j)
- No external authentication dependencies
- Password reset flow (self-service email + admin-initiated)
- Session management with security features (rate limiting, audit logging)
- Bcrypt password hashing for security

---

## Decision

**Graph-Native Authentication Architecture**

All authentication data lives in Neo4j alongside user data:

```
(User)-[:HAS_SESSION]->(Session)
     |-[:HAS_RESET_TOKEN]->(PasswordResetToken)
     |-[:HAS_AUTH_EVENT]->(AuthEvent)
```

**Key Components:**

| Component | Location | Purpose |
|-----------|----------|---------|
| `GraphAuthService` | `/core/auth/graph_auth.py` | Main authentication orchestrator |
| `SessionBackend` | `/adapters/persistence/neo4j/session_backend.py` | Neo4j session persistence |
| `Session` | `/core/models/auth/session.py` | Frozen session dataclass |
| `AuthEvent` | `/core/models/auth/auth_event.py` | Audit log entry |
| `PasswordResetToken` | `/core/models/auth/password_reset_token.py` | Reset token (email or admin-generated) |
| Password utilities | `/core/auth/password.py` | Bcrypt hash/verify functions |
| Session helpers | `/core/auth/session.py` | Cookie config, decorators, helpers |

**Authentication Flow:**

```python
# Sign up
result = await graph_auth.sign_up(
    email="user@example.com",
    password="securepass123",
    username="johndoe",
    display_name="John Doe",
    ip_address=request_ip,
    user_agent=request_ua
)

# Sign in (creates session, returns token)
result = await graph_auth.sign_in(
    email="user@example.com",
    password="securepass123",
    ip_address=request_ip,
    user_agent=request_ua
)
# result.value = {"user_uid": "user_johndoe", "session_token": "abc123..."}

# Validate session on each request
result = await graph_auth.validate_session(session_token)
```

**Password Reset (Two Paths):**

```python
# Self-service: user enters email at /forgot-password
await graph_auth.reset_password_email(email)  # sends Resend email with token link

# Admin-initiated: admin generates token and shares out-of-band
token_result = await graph_auth.admin_generate_reset_token(
    user_uid="user_johndoe",
    admin_uid="user_admin",
    ip_address=admin_ip,
    user_agent=admin_ua
)

# User resets password with token (from email link or admin)
result = await graph_auth.reset_password_with_token(
    token_value=token,
    new_password="newsecurepass123",
    ip_address=user_ip,
    user_agent=user_ua
)
```

---

## Implementation

**Related Skills:**
- [@python](../../.claude/skills/python/SKILL.md) - Python security patterns (password hashing, sessions)
- [@result-pattern](../../.claude/skills/result-pattern/SKILL.md) - Error handling for auth failures

**Pattern Documentation:**
- [AUTH_PATTERNS.md](/docs/patterns/AUTH_PATTERNS.md) - Authentication patterns and decorators

**Code Locations:**
- `/core/auth/authentication.py` - Core auth logic (require_authenticated_user, password hashing)
- `/core/auth/session.py` - Session management (create_session, validate_session)
- `/core/services/user/user_core_service.py` - User CRUD operations
- `/adapters/inbound/auth_routes.py` - Login/logout routes
- `/core/models/user/user.py` - User domain model with auth fields

---

## Alternatives Considered

### Alternative 1: Keep Supabase
**Description:** Continue using Supabase for authentication.

**Pros:**
- Already implemented
- Managed email verification and password reset
- Industry-standard JWT tokens

**Cons:**
- User data split across two systems
- External dependency for core auth
- Sync complexity between Supabase and Neo4j
- Limited customization of auth behavior
- Ongoing SaaS cost

**Why rejected:** Unified data model in Neo4j is cleaner and eliminates sync issues.


### Alternative 2: JWT-Based Sessions (Stateless)
**Description:** Use signed JWTs instead of Neo4j-stored sessions.

**Pros:**
- Stateless (no database lookup on each request)
- Industry standard
- Can include claims in token

**Cons:**
- Can't invalidate tokens before expiry
- Session hijacking harder to detect
- Token size grows with claims

**Why rejected:** Graph-stored sessions allow immediate invalidation and audit logging.


### Alternative 3: Email-Based Password Reset
**Description:** Implement email service for self-service password reset.

**Pros:**
- Standard user experience
- Self-service (no admin intervention)

**Cons:**
- Requires email service integration
- Email deliverability issues
- More attack surface (email account compromise)

**Originally deferred; implemented March 2026** via Resend integration (`EmailOperations` protocol + `ResendEmailService` adapter). Admin-initiated path remains available as fallback. `RESEND_API_KEY` env var controls availability.

---

## Consequences

### Positive Consequences
- ✅ Unified data model (all user data in Neo4j)
- ✅ No external authentication dependencies
- ✅ Complete session control (immediate invalidation)
- ✅ Full audit trail of auth events
- ✅ Rate limiting via graph queries
- ✅ Simpler deployment (no Supabase credentials needed)

### Negative Consequences
- ✅ Password reset via email (March 2026) — admin-initiated remains as fallback
- ⚠️ No email verification flow (manual admin approval)
- ⚠️ Session validation requires database query (not stateless)

### Neutral Consequences
- ℹ️ Existing users migrated with password reset required
- ℹ️ Session tokens stored as HTTP-only signed cookies

### Risks & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Session token theft | Low | High | HTTP-only cookies, secure flag, session binding to IP/UA |
| Brute force attack | Medium | Medium | Rate limiting (5 failures = 15-minute lockout) |
| Password hash compromise | Low | High | Bcrypt with cost factor, unique salts |
| Admin account compromise | Low | High | Multiple admin accounts, audit logging |

---

## Implementation Details

### Code Location
- **GraphAuthService:** `/core/auth/graph_auth.py`
- **Session helpers:** `/core/auth/session.py` (cookie config, decorators)
- **Auth models:** `/core/models/auth/` (session.py, auth_event.py, password_reset_token.py)
- **Password utilities:** `/core/auth/password.py`
- **Session backend:** `/adapters/persistence/neo4j/session_backend.py`
- **Auth routes:** `/adapters/inbound/auth_routes.py`
- **Admin routes:** `/adapters/inbound/admin_routes.py`

### Security Features

1. **Password Hashing:** Bcrypt with automatic salt generation
2. **Rate Limiting:** 5 failed attempts triggers 15-minute lockout
3. **Session Binding:** Sessions optionally bound to IP and user agent
4. **Audit Logging:** All auth events stored as graph nodes
5. **Token Expiry:** Sessions expire after configurable duration (default 30 days)
6. **Reset Token Expiry:** Password reset tokens expire after 24 hours

### Testing Strategy
- [x] Unit tests: GraphAuthService methods
- [x] Integration tests: Auth routes with mocked Neo4j
- [x] Security tests: Rate limiting, password hashing
- [x] Manual testing: Full auth flow

---

## Future Considerations

### When to Revisit
- If user base grows significantly (email-based reset may be needed)
- If stateless auth required for horizontal scaling
- If multi-factor authentication needed
- If OAuth/social login required

### Evolution Path
1. **Email Integration:** Add email service for self-service password reset
2. **MFA:** Add TOTP-based two-factor authentication
3. **OAuth:** Add Google/GitHub social login
4. **JWT Hybrid:** Issue JWTs for API access while keeping graph sessions for web

---

## Changelog

| Date | Author | Change | Version |
|------|--------|--------|---------|
| 2026-01-04 | Claude | Initial implementation | 1.0 |
