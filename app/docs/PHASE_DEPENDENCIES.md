# SKUEL Phase Dependencies

**Purpose:** Document the dependency chain between migration phases so future work is properly sequenced.

**Created:** 2026-01-03
**Related:** `/docs/PHASES.md` (status tracking), `/home/mike/.claude/plans/phase2-graph-native-migration-plan.md` (detailed plan)

---

## Dependency Graph

The 8 phase systems in PHASES.md are not independent. This document captures their relationships.

```
                    ┌─────────────────────────────────────────────────────────────┐
                    │           GRAPH-NATIVE ARCHITECTURE MIGRATION               │
                    │                    (4 Dependent Layers)                     │
                    └─────────────────────────────────────────────────────────────┘
                                              │
    ┌─────────────────────────────────────────┼─────────────────────────────────────────┐
    │                                         │                                         │
    ▼                                         ▼                                         ▼
┌───────────────────┐                 ┌───────────────────┐                 ┌───────────────────┐
│ Layer 1           │                 │ Layer 2           │                 │ Layer 3           │
│ Universal Backend │────────────────▶│ Graph-Native      │────────────────▶│ Event-Driven      │
│ Migration         │                 │ Pattern           │                 │ Architecture      │
│ ✅ COMPLETE       │                 │ ✅ COMPLETE       │                 │ ✅ COMPLETE       │
└───────────────────┘                 └───────────────────┘                 └───────────────────┘
         │                                     │                                     │
         │                                     │                                     │
         │                                     ▼                                     │
         │                            ┌───────────────────┐                          │
         │                            │ Layer 4           │                          │
         └───────────────────────────▶│ Test Migration    │◀─────────────────────────┘
                                      │ ✅ COMPLETE       │
                                      └───────────────────┘
                                               │
                                               ▼
                                      ┌───────────────────┐
                                      │ Refactoring       │
                                      │ Roadmap Phase 3   │
                                      │ 🟡 READY          │
                                      └───────────────────┘
```

---

## Layer Descriptions

### Layer 1: Universal Backend Migration
**PHASES.md Section:** #3 (Universal Backend Migration)
**Status:** ✅ COMPLETE

**What:** Replace domain-specific backend wrappers with `UniversalNeo4jBackend[T]`.

**Why First:** The generic backend doesn't serialize relationship lists as node properties. This architectural change enables graph-native patterns.

**Key File:** `/adapters/persistence/neo4j/universal_backend.py`

---

### Layer 2: Graph-Native Pattern
**PHASES.md Section:** (Embedded in model changes)
**Status:** ✅ COMPLETE

**What:** Domain models no longer have `*_uids` fields. Relationships exist as Neo4j edges, queried on demand.

**Depends On:** Layer 1 (Universal Backend must not expect relationship fields)

**Key Change:**
```python
# Before: Relationships stored as properties
class Task:
    subtask_uids: list[str]
    applies_knowledge_uids: list[str]

# After: Relationships queried from graph
class Task:
    # GRAPH-NATIVE: subtask_uids removed - query via service.relationships
    parent_uid: str | None  # Only single refs kept
```

---

### Layer 3: Event-Driven Architecture
**PHASES.md Section:** #8 (Event-Driven Architecture Migration)
**Status:** ✅ COMPLETE

**What:** Services publish domain events instead of calling each other directly.

**Depends On:** Layer 2 (Graph-native pattern enables cleaner event payloads)

**Key Benefits:**
- Zero coupling between services
- Any initialization order in bootstrap
- Full audit trail of state changes

**Services Integrated (7/7):**
| Service | Events Published |
|---------|-----------------|
| TasksCoreService | TaskCreated, TaskUpdated, TaskDeleted, TaskPriorityChanged, TasksBulkCompleted, KnowledgeAppliedInTask |
| GoalsCoreService | GoalCreated, GoalAchieved, GoalProgressUpdated, GoalAbandoned |
| HabitsCoreService | HabitCreated, HabitCompleted, HabitStreakBroken, HabitStreakMilestone |
| EventsCoreService | CalendarEventCreated, CalendarEventUpdated, CalendarEventCompleted, CalendarEventDeleted, CalendarEventRescheduled |
| ChoicesCoreService | ChoiceCreated, ChoiceUpdated, ChoiceDeleted, ChoiceOutcomeRecorded, ChoiceMade, KnowledgeInformedChoice |
| PrinciplesCoreService | PrincipleCreated, PrincipleUpdated, PrincipleDeleted, PrincipleStrengthChanged |
| FinanceCoreService | ExpenseCreated, ExpenseUpdated, ExpensePaid, ExpenseDeleted |

---

### Layer 4: Test Migration
**PHASES.md Section:** #7 (Test Migration Phase 2)
**Status:** ✅ COMPLETE

**What:** Update tests to work with graph-native architecture.

**Depends On:** All three previous layers (tests verify the new architecture)

**Results:**
| Category | Count | Status |
|----------|-------|--------|
| Unit Tests | 1,209 | ✅ All pass |
| Integration Tests | 654 | ✅ All pass |
| Route Tests | 173 | ✅ All pass |

**Note (2026-01-03):** Route test isolation issue resolved. Root cause was `asyncio.get_event_loop().run_until_complete()` pattern; fixed by converting to proper async tests.

---

## Blocking Relationships

| Blocked | Blocked By | Relationship Type |
|---------|------------|-------------------|
| Graph-Native Pattern | Universal Backend | REQUIRES (can't have graph relationships if backend serializes lists) |
| Event-Driven | Graph-Native | SHOULD_FOLLOW (cleaner events without embedded UIDs) |
| Test Migration | All 3 Layers | REQUIRES (tests verify the architecture) |
| Refactoring Phase 3 | Test Migration | SHOULD_FOLLOW (refactoring needs test coverage) |

---

## Critical Path

The graph-native migration follows a strict dependency order:

```
1. ✅ Universal Backend Migration
       ↓
2. ✅ Graph-Native Pattern (models)
       ↓
3. ✅ Event-Driven Architecture (services)
       ↓
4. ✅ Test Migration (verification)
       ↓
5. 🟡 Refactoring Roadmap Phase 3 (cleanup)
```

---

## Parallel Work Streams

Some phase systems can proceed in parallel:

| Phase System | Can Run In Parallel With |
|--------------|--------------------------|
| Route Factory Migration | Everything (infrastructure) |
| Neo4j Label Standardization | Everything (naming convention) |
| Mock Data Migration | Everything (data location) |
| Return Value Error Fixes | Everything (error patterns) |
| Refactoring Phases 1-2 | Event-Driven (independent cleanup) |

---

## Future Phases

When adding new phases to SKUEL, document dependencies here:

```markdown
## New Phase: [Name]

**Depends On:**
- [Phase X] - [Why]
- [Phase Y] - [Why]

**Blocks:**
- [Phase Z] - [Why]

**Can Parallel:**
- [Phase A], [Phase B]
```

---

## Related Documentation

- `/docs/PHASES.md` - Status tracking for all 8 phase systems
- `/docs/REFACTORING_CHECKLIST.md` - Detailed refactoring tasks
- `/docs/patterns/event_driven_architecture.md` - Event-driven patterns
- `/docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md` - Universal backend pattern
- `/docs/patterns/DOMAIN_RELATIONSHIPS_PATTERN.md` - Graph-native relationship pattern
