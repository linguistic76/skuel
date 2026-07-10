---
title: SKUEL Activity DSL - Formal Specification
updated: 2026-07-10
status: current
category: dsl
tags: [dsl, grammar, specification, formal, syntax]
related: [DSL_USAGE_GUIDE.md, DSL_IMPLEMENTATION.md]
---

# SKUEL Activity DSL - Formal Specification

*Current Version: v0.5*
*Last Updated: 2026-07-10*

## Purpose

The SKUEL Activity DSL is a **domain-specific language** embedded in Markdown that enables structured representation of human activities, behaviors, and goals while remaining fully human-readable and easy to type.

**Core Principles:**
- Plain Markdown compatibility
- Human-readable syntax (`@tag(value)` pattern)
- Type-safe entity classification via `@context()`
- Gradual complexity (required → optional tags)
- Future-extensible grammar

---

## High-Level Structure

### Activity Line Definition

An Activity Line is any Markdown line containing at minimum one `@context()` tag.

```
ActivityLine ::= LeadingMarkdown Description TagList
LeadingMarkdown ::= "- [ ]" | "- [x]" | "-" | "*" | ""  // optional
Description ::= free-text up to first @tag
TagList ::= Tag+
```

### Tag Structure

All tags follow a consistent pattern:

```
Tag ::= "@" Identifier "(" Value ")"
Identifier ::= letter (letter | digit | "_")*
Value ::= any characters except ")"
```

**Examples:**
```markdown
@context(task,learning)
@when(2025-11-30T09:00)
@priority(1)
```

---

## Tag Specifications

### Version History

| Version | Changes | Description |
|---------|------------|-------------|
| v0.1 | `@context()`, `@when()` | Core entity classification and scheduling |
| v0.2 | `@priority()`, `@ku()`, `@link()` | Prioritization and graph relationships |
| v0.3 | `@energy()`, `@duration()`, `@repeat()` | Behavioral, temporal, and habit patterns |
| v0.5 | Typed contexts; date-only `@when()` | `@context()` values parse to `EntityType`/`NonKuDomain` enum values (the enums ARE the vocabulary — `note`/`reflection`/`metric` from earlier drafts were dropped, never implemented); `@when()` accepts date-only values. v0.4 was never released. |

---

## Core Tags (Required)

### `@context()` - Entity Type Classification

**Status:** Required (at least one per Activity Line)

**Purpose:** Declares what kind of entity this activity represents, enabling type-safe routing and domain-specific processing.

**Grammar:**
```
ContextTag ::= "@context(" ContextList ")"
ContextList ::= DomainIdentifier ("," DomainIdentifier)*
DomainIdentifier ::= Identifier
```

**Extractable Context Types** (each routes to a converter in `ActivityExtractorService` and creates a real entity):

```
task        → one-off or concrete action           (Activity Domain)
habit       → repeated behavior pattern            (Activity Domain)
goal        → desired outcome or state             (Activity Domain)
event       → scheduled occurrence                 (Activity Domain)
principle   → value or belief to embody            (Activity Domain)
choice      → decision to make                     (Activity Domain)
finance     → expense/income item                  (NonKuDomain)
ku          → atomic Knowledge Unit                (Curriculum; creation role-gated)
path_step   → learning step (aliases: ps, step)    (Curriculum; creation role-gated)
learning_path → learning sequence (aliases: lp)    (Curriculum; creation role-gated)
calendar    → scheduled activity view              (NonKuDomain)
life_path   → ultimate life goal alignment         (alias: lifepath)
```

**Modifier context** (valid in combination; creates no entity by itself):

```
learning    → marks the activity as educational, e.g. @context(task,learning)
```

**Parseable vs. extractable:** the parser accepts every `EntityType` (25 values) and `NonKuDomain` (4 values) — but only the contexts above have converters. A line tagged with a parseable-but-unroutable context (e.g. `@context(exercise)`) parses successfully and creates nothing. Stick to the vocabulary above.

**Examples:**
```markdown
@context(task)
@context(habit)
@context(goal,learning)
```

**Type Safety Note:** The `@context()` value maps to `EntityType` (for all entity types) or `NonKuDomain` (for finance, group, calendar, learning) in `/core/models/enums/` for compile-time verification. The union type `DomainIdentifier = EntityType | NonKuDomain` covers all domains.

Values are validated via `EntityType.from_string()`, which supports aliases (e.g., `"knowledge"` resolves to `EntityType.KU`, `"path-step"` resolves to `EntityType.PATH_STEP`). Any invalid context value fails the **entire line** with a clear error listing the valid options — the strict failure is deliberate (a silently dropped context would disguise typos as success, and partial creation would produce duplicates when the corrected line re-syncs under line-hash dedup). The enum IS the specification of valid context values. See [Enum Architecture](/docs/architecture/ENUM_ARCHITECTURE.md) for the complete `EntityType` value list and alias mappings.

---

## Temporal Tags (Optional)

### `@when()` - Scheduled Time

**Status:** Optional (v0.1+)

**Purpose:** Declares planned execution time for calendar integration and timeline visualization.

**Grammar:**
```
WhenTag ::= "@when(" Timestamp ")"
Timestamp ::= ISODate "T" ISOTime | ISODate " " ISOTime | ISODate
ISODate ::= Digit{4} "-" Digit{2} "-" Digit{2}
ISOTime ::= Digit{2} ":" Digit{2}
```

**Examples:**
```markdown
@when(2025-11-30T09:30)    # Canonical ISO 8601
@when(2025-11-30 09:30)    # Relaxed format (space instead of T)
@when(2025-11-30)          # Date only (v0.5+) — midnight; matches obsidian-tasks 📅 granularity
```

**Timezone:** If no timezone specified, defaults to user's configured timezone. Future versions may support explicit offsets (`+07:00`).

**Unparseable values:** a `@when()` value that matches none of the formats (e.g. `@when(Friday)`) or names an impossible calendar date (e.g. `@when(2026-02-31)`) does not fail the line — the schedule is dropped with a server-side warning. Use real ISO dates for reliable scheduling.

---

### `@duration()` - Time Estimate

**Status:** Optional (v0.3+)

**Purpose:** Records expected duration for time-aware scheduling and capacity planning.

**Grammar:**
```
DurationTag ::= "@duration(" DurationValue ")"
DurationValue ::= DurationUnit+
DurationUnit ::= Number "m" | Number "h"
```

**Units:**
- `m` → minutes
- `h` → hours

**Examples:**
```markdown
@duration(20m)           # 20 minutes
@duration(1h)            # 1 hour
@duration(1h30m)         # 1 hour 30 minutes
@duration(90m)           # Alternative: 90 minutes
```

**Normalization:** Implementations should normalize to minutes internally.

---

### `@repeat()` - Habit Patterns

**Status:** Optional (v0.3+)

**Purpose:** Defines repetition schedule for habits, enabling streak tracking and recurring task generation.

**Grammar:**
```
RepeatTag ::= "@repeat(" RepeatPattern ")"

RepeatPattern ::= "daily"
                | "weekly:" DayList
                | "monthly:" DayOfMonthList
                | "every:" Interval
                | "custom"

DayList ::= Day ("," Day)*
Day ::= "Mon" | "Tue" | "Wed" | "Thu" | "Fri" | "Sat" | "Sun"

DayOfMonthList ::= DayOfMonth ("," DayOfMonth)*
DayOfMonth ::= Integer  // 1-31

Interval ::= Number "d"
```

**Examples:**
```markdown
@repeat(daily)                    # Every day
@repeat(weekly:Mon,Wed,Fri)       # Specific weekdays
@repeat(monthly:1,15)             # 1st and 15th of month
@repeat(every:2d)                 # Every 2 days
@repeat(custom)                   # User-defined pattern
```

---

## Prioritization Tags (Optional)

### `@priority()` - Importance Rating

**Status:** Optional (v0.2+)

**Purpose:** Indicates task importance for sorting and filtering.

**Grammar:**
```
PriorityTag ::= "@priority(" PriorityNumber ")"
PriorityNumber ::= "1" | "2" | "3" | "4" | "5"
```

**Scale:**
- `1` → Highest priority
- `5` → Lowest priority

**Examples:**
```markdown
@priority(1)    # Critical
@priority(3)    # Normal
@priority(5)    # Low
```

---

## Energy & State Tags (Optional)

### `@energy()` - Energy State

**Status:** Optional (v0.3+)

**Purpose:** Captures energy state required or produced by activity, enabling energy-aware scheduling and habit stacking.

**Grammar:**
```
EnergyTag ::= "@energy(" EnergyList ")"
EnergyList ::= EnergyState ("," EnergyState)*
EnergyState ::= Identifier
```

**Recommended States:**
```
focus      → deep work, thinking, creation
light      → easy tasks, maintenance
social     → connection, meeting, messaging
physical   → movement, walking, exercise
creative   → ideation, writing, designing
rest       → restoration, low-energy periods
spiritual  → meditation, journaling, contemplation
emotion    → emotional check-in, EQ practice
```

**Examples:**
```markdown
@energy(focus)                # Single state
@energy(creative,focus)       # Multiple states
@energy(physical,spiritual)   # Walking meditation
```

---

## Graph Relationship Tags (Optional)

### `@ku()` - Primary Knowledge Unit

**Status:** Optional (v0.2+)

**Purpose:** Links activity to primary Knowledge Unit for knowledge substance tracking.

**Grammar:**
```
KuTag ::= "@ku(" KuIdentifier ")"
KuIdentifier ::= "ku:" Namespace "/" Slug
Namespace ::= Identifier
Slug ::= Identifier ("-" Identifier)*
```

**Examples:**
```markdown
@ku(ku:sel/thought-not-reality)
@ku(ku:teens-yoga/focus-lesson)
@ku(ku:math/algebra-basics)
```

**Constraint:** One `@ku()` per Activity Line (v0.3). Multiple KU links use `@link()`.

---

### `@link()` - Secondary Relationships

**Status:** Optional (v0.2+)

**Purpose:** Creates graph connections to goals, principles, projects, and other entities.

**Grammar:**
```
LinkTag ::= "@link(" LinkList ")"
LinkList ::= LinkRef ("," LinkRef)*
LinkRef ::= LinkType ":" LinkId
LinkType ::= Identifier
LinkId ::= Identifier ("/" Identifier)*
```

**Common Link Types:**
```
goal:       → Goal entities
principle:  → Guiding principles
project:    → Projects
ku:         → Additional Knowledge Units
person:     → People
vortex:     → Vortexes
```

**Examples:**
```markdown
@link(goal:teens-yoga/10-members)
@link(principle:discernment-first, project:askesis-v1)
@link(ku:sel/thought-not-reality, goal:wisdom-development)
```

---

## Tag Ordering Conventions

**Recommended Order (not enforced):**
```markdown
@context(...)    # Required: Entity type
@when(...)       # Temporal: Scheduled time
@priority(...)   # Importance
@duration(...)   # Time estimate
@repeat(...)     # Habit pattern
@energy(...)     # Energy state
@ku(...)         # Primary knowledge link
@link(...)       # Secondary relationships
```

**Flexibility:** Tags may appear in any order on the line, but consistent ordering improves readability.

---

## Complete Example

```markdown
- [ ] Draft Teens.yoga lesson on focus
      @context(task,learning)
      @when(2025-11-30T09:00)
      @priority(1)
      @duration(90m)
      @energy(focus,creative)
      @ku(ku:teens-yoga/focus-lesson)
      @link(goal:teens-yoga/20-members, principle:discernment-first)
```

**Parsing yields:**
```python
{
  "description": "Draft Teens.yoga lesson on focus",
  "contexts": ["task", "learning"],
  "when": datetime(2025, 11, 30, 9, 0),
  "priority": 1,
  "duration_minutes": 90,
  "energy_states": ["focus", "creative"],
  "primary_ku": "ku:teens-yoga/focus-lesson",
  "links": [
    {"type": "goal", "id": "teens-yoga/20-members"},
    {"type": "principle", "id": "discernment-first"}
  ]
}
```

---

## Future Extensions (v0.6+)

Planned additions for future versions (none implemented — staged backlog, visible by design):

```markdown
@window()     # Time windows (morning/afternoon/evening)
@after()      # Task dependencies (must complete X before Y)
@result()     # Outcome annotation for completed activities
@feeling()    # Post-action emotional state
@estimate()   # Separate from @duration() (estimate vs actual)
@domain()     # Alternative context grouping
```

---

## Versioning Policy

**Backward Compatibility:** New tag additions are always optional. Existing Activity Lines remain valid across version upgrades.

**Version Format:** `vX.Y` where:
- `X` = Major version (breaking grammar changes)
- `Y` = Minor version (new optional tags)

**Current:** v0.5 (the version lives in this spec and the parser module docstring — keep them in step)

---

## References

- **Usage Guide:** `DSL_USAGE_GUIDE.md` - Examples and patterns
- **Implementation Guide:** `DSL_IMPLEMENTATION.md` - Parser architecture
- **EntityType / NonKuDomain Enums:** `/core/models/enums/entity_enums.py` (`DomainIdentifier = EntityType | NonKuDomain`)
- **Activity DSL Parser:** `/core/services/dsl/`
