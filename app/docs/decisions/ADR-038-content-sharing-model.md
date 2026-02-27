# ADR-038: Content Sharing Model

**Status:** Accepted
**Date:** 2026-02-02
**Author:** Claude Code (Phase 1 Implementation)

## Context

SKUEL needs a way for users to share reports and events with specific users (teachers, peers, mentors). The primary use case is **report portfolios** - students submitting work and sharing it with teachers for review.

Current state: All content is strictly `USER_OWNED` with no sharing infrastructure.

Target state: Users can share reports and events with specific users and view content shared with them.

## Decision

We implement a **three-level visibility model** with **relationship-based access control**:

### 1. Visibility Levels (Enum)

Using existing `Visibility` enum from `core/models/enums/metadata_enums.py`:

```python
class Visibility(str, Enum):
    PRIVATE = "private"  # Only owner can see (default)
    SHARED = "shared"    # Visible to specific users via SHARES_WITH
    PUBLIC = "public"    # Anyone can view (portfolio showcase)
    TEAM = "team"        # Reserved for Group-based visibility (see ADR-040)
```

### 2. Access Control via Neo4j Relationships

New relationship type: `SHARES_WITH`

```cypher
(user:User)-[:SHARES_WITH {shared_at: datetime, role: str}]->(report:Report)
```

Properties:
- `shared_at`: Timestamp when shared
- `role`: Recipient's role (e.g., "teacher", "peer", "mentor", "viewer")

### 3. Access Control Rules

A user can view a report if ANY of these conditions are true:

1. **Ownership**: User is the owner (`report.user_uid == user_uid`)
2. **Public**: Report visibility is `PUBLIC`
3. **Shared**: Report visibility is `SHARED` AND user has `SHARES_WITH` relationship

Query pattern:
```cypher
MATCH (report:Report {uid: $uid})
WHERE report.user_uid = $current_user
   OR report.visibility = 'public'
   OR (report.visibility = 'shared' AND
       EXISTS(($current_user)-[:SHARES_WITH]->(report)))
RETURN report
```

### 4. Quality Control: Only Completed Reports Shareable

```python
def is_shareable(self) -> bool:
    return self.status == ReportStatus.COMPLETED
```

This prevents users from sharing failed/processing reports, ensuring portfolio quality.

## Architecture

### Service Layer

**ReportSharingService** (`/core/services/submissions/ + core/services/feedback/report_sharing_service.py`):
- `share_report()` - Create SHARES_WITH relationship
- `unshare_report()` - Delete SHARES_WITH relationship
- `set_visibility()` - Update visibility level
- `check_access()` - Verify user can view report
- `get_shared_with_users()` - List users with access
- `get_reports_shared_with_me()` - Query shared reports

**SubmissionsCoreService** integration:
- Added `get_with_access_check()` method that wraps `get_report()` with access verification
- Prevents leaking "not found" vs "forbidden" (both return 404)

### API Layer

**6 new endpoints** (`/adapters/inbound/reports_sharing_api.py`):

1. `POST /api/submissions/share` - Share with user
2. `POST /api/submissions/unshare` - Revoke access
3. `POST /api/submissions/set-visibility` - Change visibility
4. `GET /api/submissions/shared-with-me` - Shared content inbox
5. `GET /api/submissions/shared-users?uid=` - List recipients
6. `GET /api/submissions/public` - Browse public portfolios

All routes use `@boundary_handler` for Result[T] -> HTTP conversion.

### Data Model Changes

**Report model** (`/core/models/report/report.py`):
- Added field: `visibility: Visibility = Visibility.PRIVATE`
- Added method: `is_shareable() -> bool`
- Added method: `can_view(user_uid, owner_uid, shared_uids) -> bool`

**ReportDTO**:
- Added field: `visibility: str = "private"`

**RelationshipName enum** (`/core/models/relationship_names.py`):
- Added: `SHARES_WITH = "SHARES_WITH"`

## Consequences

### Positive

1. **Clear Access Model**: Three-level visibility is easy to understand and implement
2. **Graph-Native**: Uses Neo4j relationships (no join tables, efficient queries)
3. **Extensible**: SHARES_WITH relationship can store metadata (role, timestamp, permissions)
4. **Secure by Default**: PRIVATE visibility, only completed reports shareable
5. **No Leakage**: "Not found" response for both missing and forbidden reports
6. **Portfolio Ready**: PUBLIC visibility enables portfolio showcase feature

### Negative

1. **No Bulk Sharing**: Users must share reports one-at-a-time (can be added later)
2. **No Notifications**: Recipients don't get notified when content is shared (Phase 2)
3. **No Comments**: Teachers can't leave feedback on shared reports (Phase 2)
4. **Single Domain**: Only reports in Phase 1 (events in Phase 2)

### Migration

- **Backward Compatible**: Existing reports default to `visibility=PRIVATE`
- **No Breaking Changes**: All existing routes continue to work
- **Additive Only**: New routes, new service, new relationship type

## Implementation Status

**Phase 1 (Completed - 2026-02-02):**
- Data model changes (Report.visibility, SHARES_WITH relationship)
- ReportSharingService with 6 methods
- 6 API routes for sharing operations
- Service bootstrapping in services_bootstrap.py
- Route registration in scripts/dev/bootstrap.py
- UI components (pending)
- "Shared With Me" profile tab (pending)
- Tests (pending)

**Phase 2 (Planned):**
- Event sharing (reuse same infrastructure)
- Notifications when content is shared
- Comments/feedback on shared reports

**Phase 3 (Future):**
- User following system
- Public portfolio pages
- Groups/teams sharing
- Report templates

## Alternatives Considered

### 1. Permission Table Pattern (Rejected)

Traditional RBAC with permission table:
```
reports_permissions (report_id, user_id, permission)
```

**Rejected because:**
- Requires separate table/node type (more complexity)
- Less efficient than relationship queries
- Doesn't leverage graph database strengths
- More code to maintain

### 2. Role-Based Access Control (Deferred)

Fine-grained permissions (read, write, comment, grade):
```
SHARES_WITH {permissions: ["read", "comment"]}
```

**Deferred because:**
- Over-engineering for Phase 1
- Simple viewer role sufficient for MVP
- Can add later if needed

### 3. ACL Lists on Report Node (Rejected)

Store shared user UIDs as array property:
```
report.shared_with = ["user_1", "user_2"]
```

**Rejected because:**
- Can't store metadata (role, timestamp)
- Array queries less efficient than relationships
- Doesn't scale to large sharing lists
- Loses graph relationship benefits

## References

- `/core/services/submissions/ + core/services/feedback/report_sharing_service.py` - Service implementation
- `/adapters/inbound/reports_sharing_api.py` - API routes
- `/core/models/report/report.py` - Data model changes
- `/docs/patterns/SHARING_PATTERNS.md` - Usage patterns (to be created)
- `/docs/architecture/CONTENT_SHARING_ARCHITECTURE.md` - Full architecture (to be created)

## Related ADRs

- ADR-022: Graph-Native Authentication (relationship-based auth model)
- ADR-030: UserContext File Consolidation (context-aware features)
- ADR-037: Embedding Infrastructure Separation (content processing)
- ADR-040: Teacher Assignment Workflow (auto-sharing via SHARES_WITH for teacher review)

---

**Decision:** Implement three-level visibility model with SHARES_WITH relationships for Phase 1 (reports only), extend to events in Phase 2.

**Rationale:** Simple, secure, graph-native, extensible. Solves the teacher-student portfolio use case without over-engineering.
