---
title: ADR-035: Three-Tier vs Two-Tier Pattern Selection Guidelines
updated: 2026-01-29
status: accepted
category: decisions
tags: [adr, decisions, architecture, patterns, three-tier]
related: [three_tier_type_system.md, DOMAIN_PATTERNS_CATALOG.md]
---

# ADR-035: Three-Tier vs Two-Tier Pattern Selection Guidelines

**Status:** Accepted

**Date:** 2026-01-29

**Decision Type:** ☑ Pattern/Practice

**Related ADRs:**
- Related to: ADR-013 (KU UID format)
- Related to: ADR-022 (Graph-native authentication)

---

## Context

**What is the issue we're facing?**

SKUEL uses a three-tier type system (Pydantic → DTO → Domain) for most domains, but some domains (Finance, Journals) use a simplified two-tier approach (Pydantic → DTO only). This inconsistency has caused confusion:

1. **New domain development**: Developers are unsure whether to implement full three-tier or simplified two-tier
2. **Perceived complexity**: The three-tier system appears heavyweight for simple domains
3. **Documentation gaps**: No written guidelines explain when each pattern is appropriate
4. **External feedback**: ChatGPT suggested simplifying curriculum domains, revealing unclear documentation

**What triggered this decision?**

User question (2026-01-29): "Should curriculum domains (KU, LS, LP) use a simpler pattern since they're more stable than Activity domains?"

Investigation revealed:
- Curriculum domains are NOT more stable (users can create them)
- Finance and Journals already use simplified pattern, but it's undocumented
- No decision record exists explaining when to skip Tier 3

**Constraints:**
- Must maintain backward compatibility with existing 14 domains
- Pattern choice affects development velocity (boilerplate vs structure)
- Type safety via `DomainModelProtocol` requires Tier 3 (frozen dataclasses)
- Conversion boilerplate is a legitimate cost that must be justified

---

## Decision

**What is the change we're proposing/making?**

We formalize TWO approved patterns for domain implementation in SKUEL:

### Pattern A: Full Three-Tier (Default)

```
Pydantic Request → DTO (mutable) → Domain (frozen) → Business Logic
Neo4j → DTO → Domain → Business Logic → Pydantic Response
```

**Use for**: Activity domains, Curriculum domains, any domain with business logic

### Pattern B: Simplified Two-Tier (Exception)

```
Pydantic Request → DTO (mutable) → Neo4j
Neo4j → DTO → Pydantic Response (no business logic)
```

**Use for**: Admin-only bookkeeping, simple content storage, minimal logic

### Decision Matrix: When to Use Each Pattern

| Criterion | Pattern A (Three-Tier) | Pattern B (Two-Tier) |
|-----------|------------------------|----------------------|
| **Business Logic** | Methods needed (is_overdue, calculate_score) | Minimal or none |
| **Immutability** | Semantically important | Not important |
| **Protocol Generics** | Used by `BaseService[T]` | Not needed |
| **State Transitions** | Complex (draft→scheduled→in_progress→completed) | Simple CRUD |
| **Computed Fields** | Many (urgency_score, impact_score, etc.) | Few or none |
| **Access Pattern** | User-owned or shared | Admin-only or simple storage |
| **Validation Complexity** | High (cross-field, conditional) | Low (basic types) |

### Implementation Rules

**Always require Tier 1 (Pydantic)**:
- ALL domains use Pydantic request/response models
- Non-negotiable: API boundary validation prevents 500 errors

**Always require Tier 2 (DTO)**:
- ALL domains use DTOs for service layer operations
- Mutability needed for status updates, field modifications
- Database serialization (to_dict / from_dict)

**Tier 3 (Domain) is optional**:
- ✅ **Use when** business logic methods justify the conversion boilerplate
- ❌ **Skip when** domain is pure data storage with minimal logic

---

## Alternatives Considered

### Alternative 1: Always Use Three-Tier

**Description:** Require all domains to implement full three-tier pattern for consistency.

**Pros:**
- Complete consistency across all domains
- No decision-making needed (one way to do everything)
- Type safety via `DomainModelProtocol` everywhere

**Cons:**
- Unnecessary boilerplate for simple domains (Finance, Journals)
- Conversion code adds no value when there's no business logic
- Slows development velocity for trivial domains

**Why rejected:** Over-engineering for simple bookkeeping domains. The boilerplate cost outweighs the benefit when there's minimal business logic.

### Alternative 2: Always Use Two-Tier

**Description:** Remove Domain tier entirely, use DTOs directly in business logic.

**Pros:**
- Simpler data flow (one fewer conversion)
- Faster development (less boilerplate)
- Fewer files per domain

**Cons:**
- Loses immutability guarantees (DTOs are mutable)
- Business logic mixed with data transfer concerns
- Can't use `DomainModelProtocol` for generic services
- Intelligence services would operate on mutable DTOs (risky)

**Why rejected:** Complex domains (Tasks, Goals) NEED immutable business logic models. Losing Tier 3 would mean business logic methods on mutable DTOs, which is architecturally wrong.

### Alternative 3: Single Tier (Pydantic Only)

**Description:** Use Pydantic models throughout (validation, business logic, persistence).

**Pros:**
- Minimal boilerplate
- One model per domain
- Pydantic handles validation + serialization

**Cons:**
- Pydantic models are immutable by default but not frozen
- Business logic in Pydantic models violates separation of concerns
- Can't have different shapes for request vs internal representation
- Service layer needs mutability (conflicts with immutability)

**Why rejected:** Violates single responsibility principle. Pydantic is for boundary validation, not business logic.

---

## Consequences

### Positive Consequences

✅ **Clear guidance**: Developers know which pattern to use for new domains
✅ **Justified complexity**: Three-tier pattern used only where it adds value
✅ **Documented exceptions**: Finance/Journals pattern is intentional, not accidental
✅ **Type safety preserved**: Domains with business logic keep `DomainModelProtocol` benefits
✅ **Flexibility**: Simple domains can use simpler pattern without guilt

### Negative Consequences

⚠️ **Inconsistency**: Two patterns in the codebase (but now documented)
⚠️ **Decision overhead**: Developers must choose pattern for new domains
⚠️ **Migration complexity**: Changing pattern requires file reorganization
⚠️ **Learning curve**: New developers must understand both patterns

### Neutral Consequences

ℹ️ **14 domains, 2 patterns**: 12 use Pattern A, 2 use Pattern B
ℹ️ **Conversion boilerplate**: Remains in Pattern A domains (justified by business logic)
ℹ️ **Code generation**: Could reduce boilerplate in future (but not implemented)

### Risks & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Developers choose wrong pattern for new domain | Medium | Medium | Decision matrix in CLAUDE.md, ADR, pattern catalog |
| Pattern B domains gain business logic over time | Medium | High | Revisit pattern if 3+ business logic methods added |
| Inconsistency causes maintenance burden | Low | Medium | Document both patterns clearly, keep to 2 patterns max |

---

## Implementation Details

### Code Location

**Pattern A (Three-Tier) implementations:**
- Activity domains: `/core/models/{task,goal,habit,event,choice,principle}/`
- Curriculum domains: `/core/models/{ku,ls,lp}/`
- Domain models: `{domain}.py` (frozen dataclasses)
- DTOs: `{domain}_dto.py` (mutable dataclasses)
- Requests: `{domain}_request.py` (Pydantic models)
- Converters: `{domain}_converters.py` (tier transitions)

**Pattern B (Two-Tier) implementations:**
- Finance: `/core/models/finance/` (no `finance.py` domain model)
- Journals: `/core/models/journal/` (no `journal.py` domain model)

### Testing Strategy

**Pattern validation:**
- ✅ Pattern A domains: Test business logic methods in domain model tests
- ✅ Pattern B domains: Test DTO operations directly (no separate domain tests)
- ✅ Conversion tests: Verify Pydantic→DTO→Domain→DTO→Pydantic round-trips
- ✅ Type safety: MyPy verifies `DomainModelProtocol` satisfaction for Pattern A

---

## Monitoring & Observability

**How will we know if this decision is working?**

### Success Criteria

- ✅ **Clarity**: Developers can choose pattern without asking for help
- ✅ **Consistency**: All Pattern A domains use same file structure
- ✅ **Simplicity**: Pattern B domains have <30% the code of Pattern A domains
- ✅ **Maintainability**: Adding business logic to Pattern B triggers pattern migration discussion

### Failure Indicators

**Red flags that would trigger revisiting this decision:**

- 🚨 More than 3 domains use Pattern B (indicates overuse of simplified pattern)
- 🚨 Pattern B domain grows 5+ business logic methods (should migrate to Pattern A)
- 🚨 Developers consistently choose wrong pattern (decision matrix inadequate)
- 🚨 New pattern C emerges organically (indicates decision space incomplete)

---

## Documentation & Communication

### Pattern Documentation Checklist

- ✅ Create companion pattern guide: `/docs/patterns/DOMAIN_PATTERNS_CATALOG.md`
- ✅ Update `/docs/patterns/three_tier_type_system.md` with pattern selection
- ✅ Update CLAUDE.md with decision matrix
- ✅ Create tutorial: `/docs/tutorials/DATA_FLOW_WALKTHROUGH.md`
- ✅ Cross-reference: ADR ↔ pattern guide ↔ CLAUDE.md

### Related Documentation

- Pattern guides: `/docs/patterns/three_tier_type_system.md`
- Tutorial: `/docs/tutorials/DATA_FLOW_WALKTHROUGH.md`
- Catalog: `/docs/patterns/DOMAIN_PATTERNS_CATALOG.md` (created with this ADR)
- CLAUDE.md: Quick reference section updated

---

## Future Considerations

### When to Revisit

**Triggers for reconsidering this decision:**

1. **Business logic accumulation**: If Pattern B domain gains 3+ business logic methods, migrate to Pattern A
2. **Code generation**: If boilerplate automation becomes available, three-tier cost reduces
3. **Pattern proliferation**: If more than 2 patterns emerge, consolidate or document third pattern
4. **Protocol changes**: If Python/Pydantic gain better frozen model support, reevaluate tier necessity

### Evolution Path

**How might this decision change over time?**

**Short-term (6 months)**:
- Monitor new domain additions for pattern consistency
- Collect feedback on decision matrix clarity
- Update DOMAIN_PATTERNS_CATALOG with lessons learned

**Long-term (1-2 years)**:
- Consider code generation for converter boilerplate
- Evaluate if Pydantic V3+ features reduce tier count
- Assess if `dataclass_transform` improves frozen model typing

### Technical Debt

**What technical debt does this decision create?**

- ⚠️ **Pattern inconsistency**: 2 patterns in codebase (accepted trade-off)
- ⚠️ **Migration cost**: Moving from Pattern B→A requires significant refactoring
- ⚠️ **Learning overhead**: New developers must understand both patterns

**Mitigation**:
- Keep pattern count to maximum 2 (no new patterns without deprecating old)
- Document migration path if Pattern B domain needs business logic
- Clear examples of each pattern in documentation

---

## Implementation

**Related Skills:**
- [@python](../../.claude/skills/python/SKILL.md) - Python dataclass patterns (frozen vs mutable)
- [@pydantic](../../.claude/skills/pydantic/SKILL.md) - Pydantic request model validation (Tier 1)

**Pattern Documentation:**
- [three_tier_type_system.md](/docs/patterns/three_tier_type_system.md) - Complete pattern guide
- [DOMAIN_PATTERNS_CATALOG.md](/docs/patterns/DOMAIN_PATTERNS_CATALOG.md) - Working examples

**Code Locations:**
- `/core/models/{domain}/{domain}.py` - Pattern A: Domain models (frozen dataclasses)
- `/core/models/{domain}/{domain}_dto.py` - Pattern A/B: DTOs (mutable)
- `/core/models/{domain}/{domain}_request.py` - Pattern A/B: Pydantic request models
- `/core/models/{domain}/{domain}_converters.py` - Pattern A: Tier conversion logic

---

## Approval

**Decision Maker:** Mike (SKUEL architect)

**Status:** Accepted (2026-01-29)

**Rationale:** Formalizes existing practice (Finance/Journals already use Pattern B), provides clear guidance for future domains, addresses user confusion about curriculum domain simplification.

---

## Changelog

| Date | Author | Change | Version |
|------|--------|--------|---------|
| 2026-01-29 | Claude (via Mike) | Initial draft based on codebase investigation | 0.1 |
| 2026-01-29 | Claude (via Mike) | Approved - codifies existing practice | 1.0 |

---

## Appendix

### Current Domain Distribution

**Pattern A (Three-Tier) - 12 domains:**
1. Tasks ✅
2. Goals ✅
3. Habits ✅
4. Events ✅
5. Choices ✅
6. Principles ✅
7. KU (Knowledge Units) ✅
8. LS (Learning Steps) ✅
9. LP (Learning Paths) ✅
10. Assignments ✅
11. User ✅ (special case - uses UserBackend, not UniversalBackend)
12. LifePath ✅

**Pattern B (Two-Tier) - 2 domains:**
1. Finance ✅
2. Journals ✅

### Decision Matrix Quick Reference

```
Does the domain have 3+ business logic methods?
├─ YES → Pattern A (Three-Tier)
└─ NO → Continue...
    └─ Is immutability semantically important?
        ├─ YES → Pattern A (Three-Tier)
        └─ NO → Continue...
            └─ Is domain admin-only bookkeeping?
                ├─ YES → Pattern B (Two-Tier)
                └─ NO → Pattern A (Three-Tier) [default]
```

### Code Examples

**Pattern A - Task Domain (Three-Tier)**:

```python
# Tier 1: Pydantic Request
class TaskCreateRequest(CreateRequestBase):
    title: str = Field(min_length=1, max_length=200)
    due_date: date | None = None
    priority: Priority = Priority.MEDIUM

# Tier 2: DTO (mutable)
@dataclass
class TaskDTO:
    uid: str
    title: str
    due_date: date | None
    priority: Priority
    status: ActivityStatus

    def complete(self) -> None:
        """Mutate status."""
        self.status = ActivityStatus.COMPLETED

# Tier 3: Domain (frozen, business logic)
@dataclass(frozen=True)
class Task:
    uid: str
    title: str
    due_date: date | None
    priority: Priority
    status: ActivityStatus

    def is_overdue(self) -> bool:
        """Business logic."""
        if not self.due_date or not self.is_active():
            return False
        return date.today() > self.due_date

    def urgency_score(self) -> int:
        """Complex business logic."""
        score = 0
        score += {Priority.LOW: 1, Priority.HIGH: 3}[self.priority]
        if self.is_overdue():
            score += 3
        return min(score, 10)
```

**Pattern B - Finance Domain (Two-Tier)**:

```python
# Tier 1: Pydantic Request
class ExpenseCreateRequest(CreateRequestBase):
    amount: float = Field(gt=0)
    category: str
    description: str | None = None

# Tier 2: DTO (used directly, no domain model)
@dataclass
class ExpenseDTO:
    uid: str
    amount: float
    category: str
    description: str | None
    status: str

    # Simple mutations only (no complex business logic)
    def mark_paid(self) -> None:
        self.status = "paid"

# NO Tier 3 - DTO is sufficient for simple bookkeeping
```

### References

**Internal:**
- `/docs/patterns/three_tier_type_system.md` - Pattern documentation
- `/docs/tutorials/DATA_FLOW_WALKTHROUGH.md` - Complete example
- CLAUDE.md - Quick reference section

**External influences:**
- Pydantic documentation on validation patterns
- Domain-Driven Design principles (immutable domain models)
- Python dataclasses and frozen patterns
