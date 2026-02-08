# YAML Ingestion Templates

Reference templates for files uploaded via `/ingest`. Each template shows the
exact YAML frontmatter fields the ingestion pipeline parses.

## Quick Rules

| Rule | Detail |
|------|--------|
| **Format** | Markdown files with YAML frontmatter (`---` fences) |
| **Type detection** | Markdown without `type:` defaults to KU |
| **UID** | Auto-generated as `{type}.{filename}` if omitted |
| **Title** | Auto-generated from filename if omitted |
| **Timestamps** | `created_at`, `updated_at` injected automatically |
| **User ownership** | Activity domains default `user_uid: user:system` if omitted |
| **Content** | Markdown body (below frontmatter) becomes `content` field for KU/Journal |

## Templates

| File | Domain | Type Field | Notes |
|------|--------|------------|-------|
| `ku_template.md` | Knowledge Unit | *(none — default)* | Body becomes `content` |
| `moc_template.md` | Map of Content | *(none — it's a KU)* | `organizes:` makes it a MOC |
| `task_template.md` | Task | `type: Task` | Requires `user_uid` |
| `goal_template.md` | Goal | `type: Goal` | Requires `user_uid` |
| `habit_template.md` | Habit | `type: Habit` | Requires `user_uid` |
| `event_template.md` | Event | `type: Event` | Requires `user_uid` |
| `choice_template.md` | Choice | `type: Choice` | Requires `user_uid` |
| `principle_template.md` | Principle | `type: Principle` | Uses `name:` not `title:` |
| `ls_template.md` | Learning Step | `type: LearningStep` | Curriculum (shared) |
| `lp_template.md` | Learning Path | `type: LearningPath` | Uses `name:` not `title:` |

## Relationship Fields by Domain

Each domain has specific relationship fields under `connections:`. These are
defined in the relationship registry and processed during ingestion.

### Curriculum Domains (shared, admin-created)

**KU** — `connections:`
- `requires` → REQUIRES_KNOWLEDGE (→ Ku)
- `enables` → ENABLES_KNOWLEDGE (→ Ku)
- `related` → RELATED_TO (↔ Ku)

**MOC** — top-level field (not under connections):
- `organizes` → ORGANIZES (→ Ku, with `order` edge property)

**LS** — `connections:`
- `teaches_knowledge` → CONTAINS_KNOWLEDGE (→ Ku)

**LP** — `connections:`
- `contains_steps` → HAS_STEP (→ Ls, with `sequence` edge property)

### Activity Domains (user-owned)

**Task** — `connections:`
- `applies_knowledge` → APPLIES_KNOWLEDGE (→ Ku)
- `fulfills_goal` → FULFILLS_GOAL (→ Goal)
- `depends_on` → DEPENDS_ON (→ Task)

**Goal** — `connections:`
- `requires_knowledge` → REQUIRES_KNOWLEDGE (→ Ku)
- `aligned_with_principle` → GUIDED_BY_PRINCIPLE (→ Principle)

**Habit** — `connections:`
- `reinforces_knowledge` → REINFORCES_KNOWLEDGE (→ Ku)
- `supports_goal` → SUPPORTS_GOAL (→ Goal)

**Event** — `connections:`
- `applies_knowledge` → APPLIES_KNOWLEDGE (→ Ku)

**Choice** — `connections:`
- `guided_by_principle` → INFORMED_BY_PRINCIPLE (→ Principle)

**Principle** — `connections:`
- `guides_goal` → GUIDES_GOAL (→ Goal)
- `inspires_habit` → INSPIRES_HABIT (→ Habit)

## UID Format

UIDs referenced in relationship fields use dot notation:

```
ku.meditation-basics        # Knowledge Unit
goal.master-python          # Goal
task.python-chapter-2       # Task
habit.daily-reading         # Habit
principle.continuous-learning  # Principle
ls.python-variables         # Learning Step
lp.python-fundamentals      # Learning Path
```

## Content Scope

| Scope | Domains | Who Creates | Who Reads |
|-------|---------|-------------|-----------|
| **Shared** | KU, LS, LP, MOC | Admin only | Everyone |
| **User-owned** | Task, Goal, Habit, Event, Choice, Principle | User (set `user_uid`) | Owner only |
