---
title: "ADR-042: Privacy as First-Class Citizen"
updated: 2026-03-01
status: accepted
category: decisions
tags: [privacy, security, sharing, access-control, activity-report]
related:
  - ADR-038-content-sharing-model.md
  - ADR-040-teacher-assignment-workflow.md
  - ADR-022-graph-native-authentication.md
---

# ADR-042: Privacy as First-Class Citizen

**Status:** Accepted
**Date:** 2026-03-01
**Decision Type:** ☑ Pattern/Practice

**Related ADRs:**
- Related to: ADR-038 (Content Sharing Model)
- Related to: ADR-040 (Teacher Assignment Workflow)
- Related to: ADR-022 (Graph-Native Authentication)

---

## Context

SKUEL stores intimate details of a user's life: tasks, goals, habits, choices, principles, journal entries, and activity reports that synthesise patterns across all domains. This is the data that makes the app's intelligence valuable — but it is also the data that a person might reasonably be reluctant to share.

**The core business logic:**

> The degree to which a user trusts SKUEL with their private life determines the value the app can provide.

A user who knows their private reflections might be visible to an admin will self-censor. A self-censoring user is not using SKUEL to its full capability. The app's intelligence degrades proportionally. The app fails at its own purpose.

Privacy protection is therefore not a compliance checkbox. It is a precondition for the app's core function.

**The trust model:**

SKUEL operates on reciprocal trust:
- **The user trusts SKUEL:** private content stays private; what the user enters is not readable by others without explicit sharing
- **SKUEL trusts the user:** what the user submits for sharing is treated as honest and relevant; the app does not need to verify or police content to function

This trust is the business model. Without it, the app cannot work as intended.

**What triggered this decision:**

The design of the `ACTIVITY_REPORT` system (see context below) raised the question of whether a user can annotate their AI-generated activity report before sharing it with a teacher. The answer — yes, both additive annotation and full revision must be options — revealed a deeper architectural principle: the user must be in control of what enters the shared space, because private content may be intimate. That principle generalises beyond `ACTIVITY_REPORT` to the entire application.

---

## Decision

### 1. User content is PRIVATE by default

Every entity a user creates (tasks, goals, habits, choices, principles, journals, submissions, activity reports) is visible only to that user unless they explicitly share it. `Visibility.PRIVATE` is the default at the model level.

This applies to all user-owned content regardless of role. Admin role grants system management capabilities — it does not grant content access.

### 2. Admin sees aggregates, not content

The distinction between what admin CAN and CANNOT see:

| Admin CAN see | Admin CANNOT see |
|---|---|
| Aggregate system metrics (Prometheus — already anonymous) | Individual user's private content |
| System health (query latency, error rates, queue sizes) | A user's tasks, goals, habits, choices, journals |
| Group management data (who belongs to which group) | A user's activity reports unless shared |
| Content flagged via user report or automated signal | Content of any flagged item (flag ≠ read permission) |
| User account metadata (created_at, role, last_active) | The substance of what a user has written |

This is enforced at the **service layer**, not just the UI. Admin-facing service methods return aggregate or system data. No admin-facing method returns raw user content without a `SHARES_WITH` relationship authorising access.

### 3. SHARES_WITH is the sole access gate

A teacher, peer, or admin can only read a user's content if the user has explicitly created a `SHARES_WITH` relationship to them (or to a group they belong to). There is no administrative override that bypasses `SHARES_WITH`.

```
User content is readable by:
    - The owner (always)
    - Any user with an active SHARES_WITH relationship
    - Any member of a group the content was SHARED_WITH_GROUP to

User content is NOT readable by:
    - Admin, unless the above conditions are met
    - Teachers, unless the above conditions are met
    - The system (except for AI processing the user explicitly triggered)
```

### 4. Misuse detection without content access

Admin can be informed that something requires attention without reading the content that triggered the flag. Mechanisms:

- **User-initiated reports:** a user can flag content or another user's behaviour; admin sees the flag and the reporting user, not the flagged content
- **Pattern signals:** unusual upload frequency, account activity anomalies — these are system-level signals, not content-level
- **AI content classification:** automated signals about whether content violates policy, without exposing the content to admin (the classifier sees the content; the admin sees only the signal)

Admin takes action on signals, not on content inspection. This mirrors how a postal service can know a package violated rules without opening the letter inside.

### 5. ACTIVITY_REPORT annotation model

`ACTIVITY_REPORT` is the first entity type to formalise the annotation/revision model that privacy requires. The AI generates a synthesis; the user may add to it or curate it before sharing.

**Two annotation modes:**

| Mode | Field | Description | Teacher sees |
|---|---|---|---|
| `ADDITIVE` | `user_annotation` | User writes commentary alongside AI synthesis | Both voices — AI synthesis + user response |
| `REVISION` | `user_revision` | User writes their own curated version | Only what user chose to write |

**Why both modes are required:**

- `ADDITIVE` is richer pedagogically — the teacher sees both the AI's observation and the student's interpretation. Two voices, not one.
- `REVISION` is required for privacy — a user may not wish to share the AI's synthesis of their intimate life patterns, but may be willing to share a curated reflection they wrote themselves. Without the revision option, the user cannot share safely, so they do not share at all.

**Model fields on `ActivityReport`:**

```python
@dataclass(frozen=True)
class ActivityReport(UserOwnedEntity):
    processed_content: str | None = None       # AI-generated synthesis (immutable — system created)
    user_annotation: str | None = None          # Additive commentary alongside original
    user_revision: str | None = None            # User-curated replacement for sharing
    annotation_mode: str | None = None          # "additive" | "revision" | None (not annotated)
    annotation_updated_at: datetime | None = None
    # ... other fields (time_period, domains_covered, etc.)
```

`processed_content` is never overwritten. The AI's original observation is preserved as an honest record regardless of what the user chooses to annotate or revise.

### 6. Share version — what the recipient sees

When sharing an `ACTIVITY_REPORT`, the user controls what the recipient receives:

| Share version | What recipient sees |
|---|---|
| `ORIGINAL` | AI-generated synthesis only |
| `ANNOTATION` | User's additive commentary only |
| `REVISION` | User's curated version only |
| `BOTH` | AI synthesis + user annotation (additive mode only) |

This is stored on the `SHARES_WITH` (or `SHARED_WITH_GROUP`) relationship:

```cypher
(user)-[:SHARES_WITH {
    shared_at: datetime,
    role: "teacher",
    share_version: "both"   // "original" | "annotation" | "revision" | "both"
}]->(activity_report:ActivityReport)
```

### 7. Group sharing — membership-level access

When a user shares content with a group, each current member of the group gets access. This is modelled as a single relationship to the group, with membership checked at read time:

```cypher
// Sharing with a group
(entity)-[:SHARED_WITH_GROUP {shared_at, share_version}]->(group:Group)

// Access check at read time
MATCH (viewer:User)-[:MEMBER_OF]->(group)<-[:SHARED_WITH_GROUP]-(entity)
```

This handles group membership changes naturally: new members can see shared content; removed members lose access. No cleanup of individual `SHARES_WITH` relationships required.

### 8. UnifiedSharingService — sharing as cross-cutting concern

`SHARES_WITH` and `SHARED_WITH_GROUP` management is extracted from `SubmissionsSharingService` into a `UnifiedSharingService` that any domain can call. Sharing is not owned by the submissions domain.

```
UnifiedSharingService
    share(entity_uid, owner_uid, recipient_uid, role, share_version)
    share_with_group(entity_uid, owner_uid, group_uid, share_version)
    unshare(entity_uid, owner_uid, recipient_uid)
    check_access(entity_uid, viewer_uid) → bool
    get_shared_with(entity_uid) → list[SharedWith]
```

Any entity type — `SUBMISSION`, `ACTIVITY_REPORT`, or future types — calls this service. No domain reimplements sharing logic.

---

## Alternatives Considered

### Alternative 1: Admin has full content access by default

**Description:** Admin role grants unrestricted read access to all user content, as is common in many SaaS platforms.

**Pros:**
- Simpler to implement
- Enables content moderation
- Easier abuse investigation

**Cons:**
- Causes user self-censorship
- Defeats the app's core purpose
- Users using SKUEL fully means sharing intimate life details; admin visibility makes this impossible
- Trust, once broken by design, cannot be restored by policy

**Why rejected:** The business case is clear — if users cannot trust privacy, they do not use the full app, and the app produces no value.

### Alternative 2: Encryption at rest with user-held keys

**Description:** All user content encrypted with keys only the user holds. Even database access cannot expose content.

**Pros:**
- Strongest possible privacy guarantee
- Technically verifiable — not a policy claim but a cryptographic guarantee

**Cons:**
- Significant implementation complexity
- Key management is a hard problem (what if user loses key?)
- Prevents server-side AI processing of user content

**Why not chosen now:** Correct ambition, wrong time. Service-layer access control gives the user trust they need to use the app. Encryption is the natural evolution path as the app matures. Noted as future evolution below.

### Alternative 3: Opt-in privacy (public by default)

**Description:** Content is visible to admin and teachers by default; user must actively mark things private.

**Pros:**
- Simpler sharing model
- Teachers see all student activity without student action

**Cons:**
- Wrong default — users do not expect their private journal to be visible
- Actively hostile to the trust model the app requires

**Why rejected:** Private-by-default is not a preference, it is the correct model for an app storing intimate life details.

---

## Consequences

### Positive Consequences
- ✅ Users trust the app → use it fully → richer data → better intelligence
- ✅ The pedagogical relationship (teacher-student) is consent-based, not surveillance-based
- ✅ `ACTIVITY_REPORT` sharing becomes a genuine act of trust, not an involuntary exposure
- ✅ Sharing as first-class concern means any future entity type inherits the model automatically
- ✅ Misuse detection via signals rather than content inspection protects all parties

### Negative Consequences
- ⚠️ Admin cannot easily investigate disputed content — this is the cost of the trust model
- ⚠️ Moderation requires user-initiated signals or automated classifiers, not admin reads
- ⚠️ Service-layer access control must be enforced consistently — any gap in enforcement breaks the guarantee

### Neutral Consequences
- ℹ️ `SubmissionsSharingService` is absorbed into `UnifiedSharingService` — sharing logic centralised
- ℹ️ `ACTIVITY_REPORT` model gains additional fields (annotation, revision, share_version)
- ℹ️ Group sharing adds `SHARED_WITH_GROUP` relationship type to Neo4j schema

### Risks & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Service-layer gap allows admin to read private content | Low | High | Protocol-level enforcement; no admin method returns raw user content without SHARES_WITH check |
| User loses annotation before sharing (draft loss) | Medium | Low | Auto-save drafts; annotation stored progressively |
| Group membership change creates access confusion | Low | Medium | SHARED_WITH_GROUP checked at read time, not write time — changes propagate automatically |
| AI processing pipeline reads content user expected to be private | Low | High | AI processing only runs when user explicitly triggers it; no background scan of private content |

---

## Implementation Details

### Code Location

- `UnifiedSharingService`: `core/services/sharing/unified_sharing_service.py` (new)
- `ActivityReport` model: `core/models/activity_report/activity_report.py` (rename from `ai_feedback.py`)
- `UnifiedSharingService` protocol: `core/ports/sharing_protocols.py` (new)
- Existing: `core/services/submissions/submissions_sharing_service.py` → absorbed into UnifiedSharingService

### Neo4j Schema Changes

```cypher
// New relationship type for group sharing
(entity:Entity)-[:SHARED_WITH_GROUP {
    shared_at: datetime,
    share_version: string   // "original" | "annotation" | "revision" | "both"
}]->(group:Group)

// Extended SHARES_WITH with share_version
(user:User)-[:SHARES_WITH {
    shared_at: datetime,
    role: string,
    share_version: string   // "original" | "annotation" | "revision" | "both"
}]->(entity:Entity)
```

### Testing Strategy
- [ ] Unit tests: `UnifiedSharingService` — share, unshare, check_access, group sharing
- [ ] Unit tests: `ActivityReport` annotation modes (additive, revision, neither)
- [ ] Integration tests: teacher cannot access ACTIVITY_REPORT without SHARES_WITH
- [ ] Integration tests: admin cannot access user private content via any service method
- [ ] Integration tests: group sharing — member access, post-membership-change access

---

## Future Considerations

### Evolution Path

**Phase 1 (this ADR):** Service-layer access control. Admin cannot access private content via any service method. `SHARES_WITH` is the sole access gate. This gives users the trust they need.

**Phase 2 (future):** Encryption at rest for highest-sensitivity content (journals, activity reports). User-triggered AI processing uses temporary decryption. Admin literally cannot read content even with database access.

**Phase 3 (future):** User data export and deletion — full control over own data. GDPR-aligned.

### When to Revisit
- If a legal/regulatory requirement changes what admin must be able to access
- If the misuse detection system proves insufficient without content access
- If the encryption-at-rest phase is ready to implement

---

## Documentation & Communication

### Pattern Documentation Checklist
- [ ] Create companion pattern guide: `/docs/patterns/PRIVACY_PATTERNS.md`
- [ ] Add to `/docs/INDEX.md`
- [ ] Update CLAUDE.md: add Privacy section with pointer to this ADR
- [ ] Update `REPORT_ARCHITECTURE.md`: reference this ADR for ACTIVITY_REPORT sharing model

### Related Documentation
- `docs/patterns/SHARING_PATTERNS.md` — update to reference UnifiedSharingService
- `docs/architecture/REPORT_ARCHITECTURE.md` — ACTIVITY_REPORT annotation model
- `ADR-038-content-sharing-model.md` — original sharing decision (SHARES_WITH relationship)

---

## Changelog

| Date | Author | Change | Version |
|------|--------|--------|---------|
| 2026-03-01 | Claude Code | Initial draft | 0.1 |
