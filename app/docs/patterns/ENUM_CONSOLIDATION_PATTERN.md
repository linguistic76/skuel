---
title: Enum Consolidation Pattern
updated: '2026-02-02'
category: patterns
related_skills: []
related_docs: []
---
# Enum Consolidation Pattern

*Last updated: 2026-01-07*

**Status:** Established pattern for domain enums

## Overview

SKUEL consolidates domain-specific enums into dedicated files in `/core/models/enums/` to ensure a single source of truth. This eliminates the dual-definition problem where the same enum was defined in both `*_pure.py` and `*_dto.py` files.

## The Problem: Dual-Source Enums

Before consolidation, domain enums were duplicated:

```python
# finance_pure.py
class ExpenseStatus(Enum):
    PENDING = "pending"
    PAID = "paid"
    ...

# finance_dto.py (DUPLICATE)
class ExpenseStatus(Enum):
    PENDING = "pending"
    CLEARED = "cleared"  # Different values - drift!
    ...
```

**Problems:**
- Maintenance burden: Two files to update
- Drift risk: Values can diverge silently
- Confusion: Which is canonical?

## The Solution: Single Source of Truth

All domain enums are defined ONCE in `/core/models/enums/{domain}_enums.py`:

```
core/models/enums/
├── __init__.py           # Re-exports common enums
├── activity_enums.py     # GoalStatus, TaskPriority, HabitFrequency
├── finance_enums.py      # ExpenseStatus, PaymentMethod, ExpenseCategory, ...
├── journal_enums.py      # ContentType, ContentStatus, ContentVisibility, ...
├── learning_enums.py     # MasteryLevel, LearningState
├── transcription_enums.py # ProcessingStatus, AudioFormat, LanguageCode, ...
└── ...
```

## Implementation Pattern

### Step 1: Create the Consolidated Enum File

```python
# /core/models/enums/finance_enums.py
"""
Finance Enums - Single Source of Truth
======================================

Consolidated enums for the Finance domain (January 2026).
Previously duplicated in finance_dto.py and finance_pure.py.

Per One Path Forward: One definition, imported everywhere.
"""

from enum import Enum


class ExpenseStatus(Enum):
    """Status for expense tracking."""

    PENDING = "pending"
    PAID = "paid"
    CLEARED = "cleared"
    RECONCILED = "reconciled"
    DISPUTED = "disputed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class PaymentMethod(Enum):
    """Payment method for expenses."""
    ...
```

### Step 2: Update Both Source Files

Replace inline enum definitions with imports:

```python
# finance_pure.py and finance_dto.py
from core.models.enums.finance_enums import (
    BudgetPeriod,
    ExpenseCategory,
    ExpenseStatus,
    PaymentMethod,
    RecurrencePattern,
)
```

### Step 3: Merge Values (If Different)

When consolidating, include ALL values from BOTH files:

```python
# If pure.py has PAID and REFUNDED but dto.py doesn't:
# The consolidated enum should have ALL values
class ExpenseStatus(Enum):
    PENDING = "pending"
    PAID = "paid"           # From pure.py
    CLEARED = "cleared"
    RECONCILED = "reconciled"
    DISPUTED = "disputed"
    REFUNDED = "refunded"   # From pure.py
    CANCELLED = "cancelled"
```

## Consolidated Enum Registry

| Domain | File | Enums |
|--------|------|-------|
| **Finance** | `finance_enums.py` | ExpenseStatus, PaymentMethod, ExpenseCategory, RecurrencePattern, BudgetPeriod |
| **Transcription** | `transcription_enums.py` | ProcessingStatus, AudioFormat, TranscriptionService, LanguageCode |
| **Journal** | `journal_enums.py` | ContentType, ContentStatus, ContentVisibility, JournalCategory |
| **Activity** | `activity_enums.py` | GoalStatus, TaskPriority, HabitFrequency |
| **Learning** | `learning_enums.py` | MasteryLevel, LearningState |
| **User** | `user_enums.py` | UserRole, ContextHealthScore |
| **Shared** | `enums/` directory | Domain, KuType, NonKuDomain, Priority, ActivityStatus |

## When to Consolidate

Consolidate enums when:
1. The same enum is defined in multiple files
2. A domain has both `*_pure.py` and `*_dto.py` with shared enums
3. Enums are used across multiple modules

Do NOT consolidate:
1. Enums used only within a single file
2. Enums that are truly different despite similar names

## Cross-Domain Enum Considerations

Some enums appear in multiple domains:
- `RecurrencePattern`: Finance, Scheduling
- `EnergyLevel`: Tasks, Habits, Scheduling
- `MasteryLevel`: KU, LS

For these, evaluate:
1. Are they semantically identical? → Consolidate to one location
2. Are they domain-specific variations? → Keep separate with clear naming

## Migration Checklist

- [ ] Identify all locations where the enum is defined
- [ ] Create `/core/models/enums/{domain}_enums.py`
- [ ] Merge all values into the consolidated definition
- [ ] Update all source files to import from new location
- [ ] Remove inline enum definitions
- [ ] Verify syntax with `python -m py_compile`
- [ ] Update CLAUDE.md enum documentation

## Related

- **CLAUDE.md** § "Dynamic Enum Pattern & Centralized Constants"
- **One Path Forward** philosophy - no duplicate definitions
- `/core/models/enums/` - Cross-domain shared enums
