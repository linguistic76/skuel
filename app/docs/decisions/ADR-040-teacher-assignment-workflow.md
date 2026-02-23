# ADR-040: Teacher Assignment Workflow — Groups, Assignments, and Human Review

**Status:** Accepted
**Date:** 2026-02-06
**Updated:** 2026-02-16 (ReportProject → Assignment rename)
**Author:** Claude Code

## Context

SKUEL needs teachers to assign work to students and review submissions. The pieces exist but aren't unified:

- `ReportType.ASSIGNMENT` — exists, no special workflow
- `ProcessorType.HUMAN` — exists, no implementation
- `MEMBER_OF` relationship — exists in enum, pre-wired in `UserRelationshipService`, no Group nodes
- `Visibility.TEAM` — exists, unused
- `ReportsSharingService` — sharing infrastructure works, but only for post-completion manual sharing

Two changes unify these into a coherent architecture:
1. **Group** — new entity for teacher-student class management
2. **Assignment** — instruction template with `scope`, `due_date`, `processor_type` to support teacher assignments

A teacher assignment IS an Assignment with `scope=ASSIGNED`.

## Decision

### 1. Group as First-Class Entity

Groups are the ONE PATH for teacher-student relationships. No direct TEACHES relationship.

```
(:Group {uid, name, description, owner_uid, is_active, max_members, created_at, updated_at})
(teacher:User)-[:OWNS]->(group:Group)
(student:User)-[:MEMBER_OF {joined_at, role}]->(group:Group)
```

Group uses Three-Tier type system (Pattern A): Pydantic request → GroupDTO → Group (frozen dataclass).

### 2. Assignment (Instruction Template)

Assignment provides fields for both personal and teacher-assigned workflows:
- `scope: ProjectScope` — PERSONAL (default) or ASSIGNED
- `due_date: date | None` — only for ASSIGNED scope
- `processor_type: ProcessorType` — LLM, HUMAN, or HYBRID
- `group_uid: str | None` — target group for ASSIGNED scope

A teacher assignment IS an Assignment with `scope=ASSIGNED`.

### 3. Teacher Review Reuses SHARES_WITH

When a student submits a Ku against an ASSIGNED Assignment:
1. Ku status set to `MANUAL_REVIEW`
2. `SHARES_WITH {role: "teacher"}` auto-created from teacher to submission
3. Teacher's review queue = `get_kus_shared_with_me()` filtered by `role="teacher"` and pending status

### 4. Submission Ownership Stays with Student

Teacher gets access via SHARES_WITH, not ownership transfer.

### 5. UserRelationshipService: :Team → :Group

One Path Forward — `:Team` label replaced with `:Group`. No backward compatibility.

## Graph Schema

```cypher
// New nodes
(:Group {uid, name, description, owner_uid, is_active, max_members, created_at, updated_at})

// Assignment nodes
(:Assignment {uid, user_uid, name, instructions, model, context_notes, domain,
              is_active, scope, due_date, processor_type, group_uid, ...})

// Relationships
(teacher:User)-[:OWNS]->(group:Group)
(student:User)-[:MEMBER_OF {joined_at, role}]->(group:Group)
(project:Assignment)-[:FOR_GROUP]->(group:Group)
(submission:Ku)-[:FULFILLS_PROJECT]->(project:Assignment)
(teacher:User)-[:SHARES_WITH {role: "teacher"}]->(submission:Ku)  // Auto on submission
```

## Consequences

### Positive
- Assignment serves both personal and teacher-assigned use cases
- Reuses existing SHARES_WITH infrastructure for teacher access
- Group entity enables future features (team visibility, group analytics, bulk operations)
- Clear ownership model: students own submissions, teachers get shared access

### Negative
- Assignment has 4 fields that are only relevant to ASSIGNED scope
- Group management adds CRUD surface area

## Alternatives Considered

1. **Separate entity for teacher vs personal assignments** — Rejected. One Assignment model with `scope` discriminator follows One Path Forward.
2. **Direct TEACHES relationship** — Rejected. Teacher-student relationship should be mediated by groups for scalability and class management.
3. **Ownership transfer on submission** — Rejected. Student should always own their work. Teacher gets access, not ownership.

## Naming History

Originally implemented as `KuProject` / `ReportProject` in code. Renamed to `Assignment` in February 2026 to align with pipeline vocabulary (Assign → Submit → Analyze → Review). The word "report" was doing triple duty — naming things by their pipeline role eliminates ambiguity.

## Related

- **ADR-038**: Content Sharing Model (SHARES_WITH infrastructure)
- **Phase 3 (Future)**: Visibility.TEAM implementation, group analytics, bulk operations
