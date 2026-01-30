# YAML Template Reference Guide
**Last Updated**: October 4, 2025

This directory contains **template examples** (NOT validation schemas) showing all valid fields for each YAML entity type in SKUEL.

## Purpose

These templates are **documentation**, not validation. They show:
- All valid fields for each entity type
- Required vs optional fields
- Valid enum values
- Field descriptions and examples
- Common mistakes to avoid

**Validation happens via Pydantic Request models** in the Python code.

---

## Quick Reference

| Entity Type | Template File | Primary Use Case |
|-------------|---------------|------------------|
| **KnowledgeUnit** | [knowledge_unit_template.yaml](knowledge_unit_template.yaml) | Core learning content with markdown |
| **LearningStep** | [learning_step_template.yaml](learning_step_template.yaml) | Steps within a learning path |
| **LearningPath** | [learning_path_template.yaml](learning_path_template.yaml) | Structured learning sequences |
| **Principle** | [principle_template.yaml](principle_template.yaml) | Guiding principles and values |
| **Choice** | [choice_template.yaml](choice_template.yaml) | Decision points for learners |
| **Habit** | [habit_template.yaml](habit_template.yaml) | Recurring behaviors to build/break |
| **Task** | [task_template.yaml](task_template.yaml) | Actionable work items |
| **Event** | [event_template.yaml](event_template.yaml) | Calendar events and milestones |
| **Goal** | [goal_template.yaml](goal_template.yaml) | Objectives and outcomes |

---

## Common Field Patterns

### UID Patterns

Follow these conventions for unique identifiers:

```yaml
# Knowledge Units
uid: ku:topic-name

# Learning Steps
uid: ls:path-name:step-number

# Learning Paths
uid: lp:path-name

# Principles
uid: principle:principle-name

# Choices
uid: choice:choice-name

# Habits
uid: habit:habit-name

# Tasks
uid: task:task-name

# Events
uid: event:event-name

# Goals
uid: goal:goal-name
```

**Rules**:
- Lowercase only
- Use kebab-case (hyphens, not underscores)
- Prefix indicates entity type
- Descriptive, readable names

---

## Critical Differences Between Models

### Field Name Variations

**⚠️ Important**: Different models use different field names for similar concepts!

| Concept | KnowledgeUnit | Habit | Task/Event/Goal | Choice |
|---------|---------------|-------|-----------------|--------|
| **Display Name** | `title` | `name` ⚠️ | `title` | `title` |
| **User Ownership** | N/A | N/A | N/A | `user_uid` ⚠️ |
| **Timestamps** | `created_at`, `updated_at` | `created_at`, `updated_at` | `created_at`, `updated_at` | `created_at` only ⚠️ |

**Key Differences**:
1. **Habit** uses `name` not `title`
2. **Choice** requires `user_uid`, others don't
3. **Choice** has no `updated_at` field

### Enum Value Differences

**⚠️ Important**: Similar concepts use different enum values!

| Field | KnowledgeUnit | Goal | Other |
|-------|---------------|------|-------|
| **Difficulty** | `basic`, `medium`, `advanced` | N/A | N/A |
| **Difficulty** (Goal) | N/A | `beginner`, `intermediate`, `advanced`, `expert` | N/A |

**Common Mistake**: Using `beginner` for KnowledgeUnit complexity → Should be `basic`!

---

## Validation Flow

```
YAML File
    ↓
Load as Python dict
    ↓
[Pydantic Request Model] ← Validation happens HERE
    ↓
DTO (mutable transfer object)
    ↓
Pure Domain Model (frozen dataclass)
    ↓
Neo4j Database
```

**Validation is done by Pydantic**, not by these YAML templates.

---

## How to Use These Templates

### 1. Creating New Entities

**Step 1**: Copy the relevant template
```bash
cp yaml_templates/_schemas/knowledge_unit_template.yaml \
   /home/mike/0bsidian/skuel/domains/my-domain/ku_my-topic.yaml
```

**Step 2**: Remove template comments

**Step 3**: Fill in your content

**Step 4**: Remove unused optional fields

**Step 5**: Validate via ingestion (Pydantic will catch errors)

### 2. Understanding Validation Errors

When you get a Pydantic validation error:

```
1 validation error for KnowledgeCreateRequest
complexity
  String should match pattern '^(basic|medium|advanced)$'
  [input_value='beginner']
```

**Fix**: Check the template for valid enum values
- Open `knowledge_unit_template.yaml`
- Find the `complexity` field
- See valid values: `basic`, `medium`, `advanced`
- Change `beginner` → `basic`

### 3. Finding Required Fields

Look for `# REQUIRED FIELDS` section in each template.

**Example** (KnowledgeUnit):
```yaml
# REQUIRED FIELDS
version: 1.0        # Always required
type: KnowledgeUnit # Always required
uid: ku:...         # Required
title: ...          # Required
content: |          # Required
  ...
```

All other fields are optional with defaults.

---

## Common Mistakes & Solutions

### Mistake 1: Wrong Enum Value

**Problem**:
```yaml
complexity: beginner  # ❌ Invalid for KnowledgeUnit
```

**Solution**:
```yaml
complexity: basic  # ✅ Valid value
```

**How to Avoid**: Check template for valid enum values in comments.

### Mistake 2: Wrong Field Name

**Problem**:
```yaml
type: Habit
title: My Habit  # ❌ Habit uses 'name' not 'title'
```

**Solution**:
```yaml
type: Habit
name: My Habit  # ✅ Correct field name
```

**How to Avoid**: Reference the template for correct field names.

### Mistake 3: Missing user_uid in Choice

**Problem**:
```yaml
type: Choice
uid: choice:my-choice
title: My Choice
# ❌ Missing user_uid (required for Choice!)
```

**Solution**:
```yaml
type: Choice
uid: choice:my-choice
title: My Choice
user_uid: system  # ✅ Required field
```

**How to Avoid**: Check "REQUIRED FIELDS" in choice_template.yaml.

### Mistake 4: Old Field Names

**Problem** (from old stubs):
```yaml
type: Habit
habit_type: daily    # ❌ Old field name
frequency: daily     # ❌ Old field name
```

**Solution**:
```yaml
type: Habit
recurrence_pattern: daily  # ✅ Current field name
target_days_per_week: 7    # ✅ Related field
```

**How to Avoid**: Always use the latest templates, not old stubs.

---

## Domain-Specific Guidelines

### KnowledgeUnit

**Use Case**: Core learning content

**Key Fields**:
- `content`: Full markdown (required)
- `complexity`: `basic`, `medium`, or `advanced`
- `prerequisites`: List of ku: UIDs
- `enables`: List of ku: UIDs this unlocks

**Best Practice**: Rich markdown with headers, code, examples.

### LearningStep

**Use Case**: Steps in a learning path

**Key Fields**:
- `title` + `intent`: What and why (both required)
- `knowledge_uid`: The knowledge for this step
- `sequence`: Order in path (0-based)
- `prerequisites`: Other steps needed first

**Best Practice**: Clear, actionable intent statements.

### LearningPath

**Use Case**: Structured learning sequence

**Key Fields**:
- `goal`: What learner achieves
- `steps`: List of step UIDs
- `outcomes`: Concrete learning objectives

**Best Practice**: Clear progression from simple to complex.

### Principle

**Use Case**: Guiding values and beliefs

**Key Fields**:
- `statement`: Core principle
- `category`: personal, professional, etc.
- `source`: Where it comes from

**Best Practice**: Actionable, measurable principles.

### Habit

**Use Case**: Recurring behaviors

**Key Fields**:
- `name`: NOT title! ⚠️
- `recurrence_pattern`: daily, weekly, monthly
- `cue`, `routine`, `reward`: Habit loop

**Best Practice**: Use cue-routine-reward pattern.

### Task

**Use Case**: One-time actions

**Key Fields**:
- `status`: draft → ready → in_progress → completed
- `priority`: low, medium, high, critical
- `fulfills_goal_uid`: Single goal UID

**Best Practice**: Clear, actionable descriptions.

### Event

**Use Case**: Calendar items

**Key Fields**:
- `event_type`: ONE_TIME or RECURRING
- `recurrence_rule`: RRULE format for recurring
- `is_online`: true/false for virtual events

**Best Practice**: Use null for flexible timing.

### Goal

**Use Case**: Objectives and outcomes

**Key Fields**:
- `goal_type`: outcome, process, learning, etc.
- `measurement_type`: How to track progress
- `target_value`: Numeric goal (if applicable)

**Best Practice**: SMART goals (Specific, Measurable, Achievable, Relevant, Time-bound).

---

## Architecture Notes

### Why Templates, Not Schemas?

**Decision**: Use Pydantic for validation, YAML templates for documentation.

**Reasons**:
1. **One path forward**: Single validation system (Pydantic)
2. **No schema drift**: Can't get out of sync
3. **Type safety**: Python types throughout
4. **Clear errors**: Pydantic errors are actionable
5. **IDE support**: Autocomplete from Python types

**Not using**:
- ❌ JSONSchema files (redundant)
- ❌ YAML schema validation (unnecessary)
- ❌ Pre-flight validation (Pydantic is fast enough)

### Three-Tier Architecture

```
External → Transfer → Core

Pydantic   DTO      Pure
Request → DTO   → Domain
Model              Model
```

**Validation happens at Tier 1** (Pydantic Request models).

These templates document what Pydantic validates.

---

## Next Steps

### Creating New Domain Bundles

**Step 1**: Create domain directory
```bash
mkdir -p /home/mike/0bsidian/skuel/domains/my-new-domain
```

**Step 2**: Create manifest.yaml
```yaml
version: 1.0
bundle_name: my_new_domain
title: My New Domain
description: ...

import_order:
  1_knowledge:
    - ku:topic-1
    - ku:topic-2
  2_supporting_entities:
    - principle:...
    - habit:...
  3_learning_steps:
    - ls:...
  4_learning_paths:
    - lp:...
```

**Step 3**: Create entity YAML files using templates as reference

**Step 4**: Test ingestion
```bash
poetry run python scripts/auto_fresh_start.py
```

**Step 5**: Fix validation errors using template reference

### Getting Help

**If you get validation errors**:
1. Read the error message (Pydantic errors are clear!)
2. Check the relevant template file
3. Compare your YAML to the template example
4. Fix the invalid field/value
5. Re-run ingestion

**If a field is confusing**:
1. Open the template file
2. Read the comments for that field
3. Check "ENUM VALUE REFERENCE" section
4. Look at "IMPORTANT NOTES" section

**If you need a new field**:
1. This is a domain model change, not a YAML issue
2. Update the Pydantic Request model first
3. Then update the template to document it

---

## Maintenance

**When adding new fields to domain models**:

1. Update Pydantic Request model (`*_request.py`)
2. Update DTO (`*_dto.py`)
3. Update Pure model (`*.py`)
4. Update template (`*_template.yaml`) in this directory
5. Update domain README (if exists)

**When changing enum values**:

1. Update enum in `core/models/shared_enums.py` or domain-specific enum
2. Update template to show new valid values
3. Update any example YAML files

**Template Review Schedule**:
- After any model changes
- Monthly review for accuracy
- When validation errors become common

---

## Resources

**Template Files**:
- [knowledge_unit_template.yaml](knowledge_unit_template.yaml)
- [learning_step_template.yaml](learning_step_template.yaml)
- [learning_path_template.yaml](learning_path_template.yaml)
- [principle_template.yaml](principle_template.yaml)
- [choice_template.yaml](choice_template.yaml)
- [habit_template.yaml](habit_template.yaml)
- [task_template.yaml](task_template.yaml)
- [event_template.yaml](event_template.yaml)
- [goal_template.yaml](goal_template.yaml)

**Model Locations**:
- `/core/models/{domain}/{domain}.py` - Pure domain models
- `/core/models/{domain}/{domain}_request.py` - Pydantic validation
- `/core/models/{domain}/{domain}_dto.py` - Transfer objects

**Validation Service**:
- `/core/services/yaml_ingestion_service.py` - Where validation happens

**Architecture Docs**:
- `/home/mike/skuel/app/CLAUDE.md` - Three-tier architecture
- `/home/mike/skuel/app/SCHEMA_VALIDATION_ASSESSMENT.md` - Why templates, not schemas

---

**Remember**: These are TEMPLATES (documentation), not SCHEMAS (validation). Pydantic does the validation. Use these to understand what Pydantic expects.
