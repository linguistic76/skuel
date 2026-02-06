# ADR-040: Teacher Assignment Workflow — Groups, ReportProject Evolution, and Human Review

**Status:** Accepted
**Date:** 2026-02-06
**Author:** Claude Code

## Context

SKUEL needs teachers to assign work to students and review submissions. The pieces exist but aren't unified:

- `ReportType.ASSIGNMENT` — exists, no special workflow
- `ProcessorType.HUMAN` — exists, no implementation
- `MEMBER_OF` relationship — exists in enum, pre-wired in `UserRelationshipService`, no Group nodes
- `Visibility.TEAM` — exists, unused
- `ReportSharingService` — sharing infrastructure works, but only for post-completion manual sharing

Two changes unify these into a coherent architecture:
1. **Group** — new entity for teacher-student class management
2. **ReportProject evolution** — add `scope`, `due_date`, `processor_type` to support teacher assignments

No new "Assignment" entity. A teacher assignment IS a ReportProject with `scope=ASSIGNED`.

## Decision

### 1. Group as First-Class Entity

Groups are the ONE PATH for teacher-student relationships. No direct TEACHES relationship.

```
(:Group {uid, name, description, owner_uid, is_active, max_members, created_at, updated_at})
(teacher:User)-[:OWNS]->(group:Group)
(student:User)-[:MEMBER_OF {joined_at, role}]->(group:Group)
```

Group uses Three-Tier type system (Pattern A): Pydantic request → GroupDTO → Group (frozen dataclass).

### 2. ReportProject Evolves (No New Entity)

ReportProject gains four fields:
- `scope: ProjectScope` — PERSONAL (default) or ASSIGNED
- `due_date: date | None` — only for ASSIGNED scope
- `processor_type: ProcessorType` — LLM, HUMAN, or HYBRID
- `group_uid: str | None` — target group for ASSIGNED scope

A teacher assignment IS a ReportProject with `scope=ASSIGNED`.

### 3. Teacher Review Reuses SHARES_WITH

When a student submits a report against an ASSIGNED ReportProject:
1. Report status set to `MANUAL_REVIEW`
2. `SHARES_WITH {role: "teacher"}` auto-created from teacher to report
3. Teacher's review queue = `get_reports_shared_with_me()` filtered by `role="teacher"` and pending status

### 4. Report Ownership Stays with Student

Teacher gets access via SHARES_WITH, not ownership transfer.

### 5. UserRelationshipService: :Team → :Group

One Path Forward — `:Team` label replaced with `:Group`. No backward compatibility.

## Graph Schema

```cypher
// New nodes
(:Group {uid, name, description, owner_uid, is_active, max_members, created_at, updated_at})

// Evolved nodes
(:ReportProject {uid, user_uid, name, instructions, model, context_notes, domain,
                 is_active, scope, due_date, processor_type, group_uid, ...})

// New relationships
(teacher:User)-[:OWNS]->(group:Group)
(student:User)-[:MEMBER_OF {joined_at, role}]->(group:Group)
(project:ReportProject)-[:FOR_GROUP]->(group:Group)
(report:Report)-[:FULFILLS_PROJECT]->(project:ReportProject)
(teacher:User)-[:SHARES_WITH {role: "teacher"}]->(report:Report)  // Auto on submission
```

## Consequences

### Positive
- No new entity type for assignments — ReportProject serves both personal and assigned use cases
- Reuses existing SHARES_WITH infrastructure for teacher access
- Group entity enables future features (team visibility, group analytics, bulk operations)
- Clear ownership model: students own reports, teachers get shared access

### Negative
- ReportProject gains complexity (4 new fields)
- Group management adds CRUD surface area

## Alternatives Considered

1. **Separate Assignment entity** — Rejected. Duplicates ReportProject's purpose. Two entities for "instructions + metadata" violates One Path Forward.
2. **Direct TEACHES relationship** — Rejected. Teacher-student relationship should be mediated by groups for scalability and class management.
3. **Ownership transfer on submission** — Rejected. Student should always own their work. Teacher gets access, not ownership.

## Related

- **ADR-038**: Content Sharing Model (SHARES_WITH infrastructure)
- **Phase 3 (Future)**: Visibility.TEAM implementation, group analytics, bulk operations
