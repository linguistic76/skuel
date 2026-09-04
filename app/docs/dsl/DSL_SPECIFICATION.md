---
title: SKUEL Activity DSL - Formal Specification
updated: 2026-09-04
status: current
category: dsl
tags: [dsl, grammar, specification, formal, syntax]
related: [DSL_USAGE_GUIDE.md, DSL_IMPLEMENTATION.md]
---

# SKUEL Activity DSL - Formal Specification

*Current Version: v0.6*
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

**One physical line.** The parser processes each line independently — description and ALL tags must share the line. Splitting tags onto indented continuation lines produces a metadata-less checkbox task (via the obsidian-tasks fallback) plus an empty-description tag line, not one entity.

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
| v0.5 | Typed contexts; date-only `@when()` | `@context()` values parse to `EntityType`/`NonKuDomain` enum values (`note`/`reflection`/`metric` from earlier drafts were dropped, never implemented); `@when()` accepts date-only values. v0.4 was never released. |
| v0.6 | Vocabulary shortened to 13; non-empty description | `@context()` validates against the DSL's own vocabulary (12 domain types + `learning`) instead of the full 29-value enum catalog — system-side types (`interaction`, `form_template`, …) now fail like typos instead of parsing into inert lines. Tags-only lines (empty description) are rejected. |

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

**Literal text is not a marker.** A `@context()` (or any `@tag()`) inside Markdown inline code
(`` `…` ``) is documentation-by-example — a legend line, a note about the tag itself — and is
never parsed: it neither makes the line an Activity Line nor counts as a tag, and it stays in
the description verbatim. A marker outside the code span on the same line still counts.
(Ruled 2026-08-27 after a daily-note legend line minted a junk Event.)

**Entity-creating context types** (wired to a live create surface in production — `services_bootstrap/compose.py`):

```
task        → one-off or concrete action           (Activity Domain)
habit       → repeated behavior pattern            (Activity Domain)
goal        → desired outcome or state             (Activity Domain)
event       → scheduled occurrence                 (Activity Domain)
principle   → value or belief to embody            (Activity Domain)
choice      → decision to make                     (Activity Domain)
ku          → atomic Knowledge Unit — alias: knowledge   (Curriculum; creation role-gated)
```

**Modifier context** (valid ONLY in combination — `@context(learning)` alone fails validation, since a modifier with no base type creates nothing):

```
learning    → marks the activity as educational, e.g. @context(task,learning)
```

**Parse-only context types** (recognized and counted in extraction stats, but skip cleanly — the extractor has converters, yet production wires no create surface for them):

```
path_step     → aliases: ps, step, learningstep    (no create-capable facade method today)
learning_path → aliases: lp, path, learningpath    (no create-capable facade method today)
calendar      →                                    (no create-capable facade method today)
life_path     → alias: lifepath                    (no create-capable facade method today)
finance       →                                    (retired as in-app domain — ADR-052 Firefly sidecar)
```

**The vocabulary is closed (v0.6+):** the three lists above — entity-creating, modifier, parse-only — are the complete `@context()` vocabulary (13 values, `_DSL_CONTEXT_VOCABULARY` in the parser). Anything else fails the line with a validation error, whether it's a typo (`@context(taks)`) or a system-side enum member (`@context(interaction)`, `@context(form_template)`) — those are records the system writes, not things a note line can mean. Parse-only contexts additionally surface an "unrouted" warning in the extraction summary — even when combined with an entity-creating context on the same line (`@context(task,ps)` creates the Task and reports the skipped `ps`) — so recognized-but-skipped is never silent.

**Examples:**
```markdown
@context(task)
@context(habit)
@context(goal,learning)
```

**Type Safety Note:** The `@context()` value maps to `EntityType` (for all entity types) or `NonKuDomain` (for finance, group, calendar, learning) in `/core/models/enums/` for compile-time verification. The union type `DomainIdentifier = EntityType | NonKuDomain` covers all domains.

Values are validated via `EntityType.from_string()`, which supports aliases (e.g., `"knowledge"` resolves to `EntityType.KU`; `"ps"` and `"path-step"` both resolve to `EntityType.PATH_STEP`). Any invalid context value fails the **entire line** with a clear error listing the valid options — the strict failure is deliberate (a silently dropped context would disguise typos as success, and partial creation would produce duplicates when the corrected line re-syncs under line-hash dedup). The enum IS the specification of valid context values. Aliases are **input-only**: a note line may say `ps`, but once `from_string()` resolves it, the system speaks canonical values (`path_step`) on every machine channel — see [Enum Architecture § Canonical Values vs Aliases](/docs/architecture/ENUM_ARCHITECTURE.md) for the emission rule, the complete `EntityType` value list, and alias mappings.

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

**Unparseable values:** a `@when()` value that matches none of the formats (e.g. `@when(Friday)`) or names an impossible calendar date (e.g. `@when(2026-02-31)`) does not fail the line — the schedule is dropped, and the drop is reported as a `tag_warnings` entry in the extraction summary (surfaced by the vault-sync warnings). The same soft-drop-plus-warning applies to invalid `@priority()`, `@duration()`, and `@repeat()` values. Use real ISO dates for reliable scheduling.

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

Interval ::= Number Unit
Unit ::= "d" | "h" | "w" | "m"   // long forms accepted: days/hours/weeks/months
```

**Strict values (v0.6+):** malformed-but-prefixed patterns (`weekly:Funday`, `monthly:32`, `every:2dfoo`) drop the whole `@repeat()` value with a `tag_warnings` report — partial acceptance would hide the typo.

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
KuIdentifier ::= "ku." Namespace "." Slug      (authored, vault)
               | "ku_" Slug "_" Random          (generated, API)
Namespace ::= Identifier
Slug ::= Identifier ("-" Identifier)*
```

**Examples:**
```markdown
@ku(ku.sel.thought-not-reality)
@ku(ku.teens-yoga.focus-lesson)
@ku(ku.math.algebra-basics)
```

**Constraint:** One `@ku()` per Activity Line (v0.3). Multiple KU links use `@link()`.

---

### `@link()` - Secondary Relationships

**Status:** Optional (v0.2+)

**Purpose:** Creates graph connections from the activity to goals, principles and knowledge
(Kus, PathSteps, LearningPaths) that already exist.

**The id is the stored uid.** What follows the prefix is the entity's uid, copied verbatim
from where it lives (the entity page, or the vault file's `uid:`), in either sanctioned
spelling — authored `goal.{grouping}.{slug}` / `ku.{ns}.{slug}` or generated
`goal_{random}` / `ku_{slug}_{random}`. The prefix only names which label the sink checks;
it is never prepended, and nothing resolves a title, a slug or a path to a uid. A `@link`
whose uid names no node writes no edge — the sync reports it as a link error.

**Authorship:** `@link(goal:…)` is written by the user, never by the LLM bridge. The bridge
grounds recognition in active-goal *titles* through a non-extractable prompt slot and emits no
`@link`; in the DSL a goal edge (`FULFILLS_GOAL`) comes from the user's own
`@link(goal:<uid>)` and from nothing the bridge adds. Ruled 2026-09-02 (goal links stay
user-authored only) — see
`docs/roadmap/deferred-work.md` § DSL-Bridge Grounding.

**Grammar:**
```
LinkTag ::= "@link(" LinkList ")"
LinkList ::= LinkRef ("," LinkRef)*
LinkRef ::= LinkType ":" UID
LinkType ::= "goal" | "principle" | "ku" | "ps" | "lp"
UID ::= the entity's stored uid, verbatim (authored dot form or generated underscore form)
```

**Link types and where they land:**
```
goal:       → Task.fulfills_goal_uid · Habit/Event linked_goal_uids
principle:  → linked_principle_uids / guiding_principle_uids
ku:  ps:    → applies_knowledge_uids (+ the entry's APPLIES_KNOWLEDGE edge) — the door
              for Kus beyond the one @ku() a line may carry
lp:         → the learning-path anchor of a @context(ps) line
```
Any other prefix parses but reaches no sink.

**Examples:**
```markdown
@link(goal:goal.teens-yoga.ten-members)
@link(principle:principle.sel.discernment-first, goal:goal_3f9a2b1c)
@link(ku:ku.sel.thought-not-reality, ku:ku_algebra-basics_a1b2c3d4)
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
- [ ] Draft Teens.yoga lesson on focus @context(task,learning) @when(2025-11-30T09:00) @priority(1) @duration(90m) @energy(focus,creative) @ku(ku.teens-yoga.focus-lesson) @link(goal:goal.teens-yoga.twenty-members, principle:principle.sel.discernment-first)
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
  "primary_ku": "ku.teens-yoga/focus-lesson",
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

**Current:** v0.6 (the version lives in this spec and the parser module docstring — keep them in step)

---

## References

- **Usage Guide:** `DSL_USAGE_GUIDE.md` - Examples and patterns
- **Implementation Guide:** `DSL_IMPLEMENTATION.md` - Parser architecture
- **EntityType / NonKuDomain Enums:** `/core/models/enums/entity_enums.py` (`DomainIdentifier = EntityType | NonKuDomain`)
- **Activity DSL Parser:** `/core/services/dsl/`
