# Principle Domain Models

**Purpose**: Guiding principles and values that shape behavior, learning, and goal pursuit.

---

## YAML Structure

### Required Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `version` | Float | YAML version | `1.0` |
| `type` | String | Entity type (must be exact) | `Principle` |
| `uid` | String | Unique identifier | `principle:small-wins` |
| `name` | String | Principle name (1-100 chars) | `"Small Wins Compound"` |
| `statement` | String | Core statement (1-500 chars) | `"Consistent small actions compound..."` |
| `category` | Enum | Principle category | `personal` |
| `source` | Enum | Origin of principle | `scientific` |
| `strength` | Enum | How foundational | `core` |
| `alignment_level` | Enum | Importance of alignment | `high` |

### Optional Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `description` | String | `null` | Detailed explanation (multi-line) |
| `supported_knowledge_domains` | List[Enum] | `[]` | Which domains this applies to |
| `example_applications` | List[String] | `[]` | Concrete examples of use |
| `measurement_criteria` | String | `null` | How to know you're applying it |
| `tags` | List[String] | `[]` | Tags for organization |

### Auto-Populated Fields (DO NOT SET)

- `created_at`: Timestamp when created
- `updated_at`: Timestamp when last modified

---

## Enum Values

### Category
- `personal` - Self-development and personal growth
- `social` - Interpersonal relationships and community
- `professional` - Work and career
- `ethical` - Moral and ethical guidelines
- `philosophical` - Fundamental life philosophies

### Source
⚠️ **IMPORTANT**: Use valid source values only!

- `philosophical` - From philosophy traditions
- `religious` - From religious teachings
- `cultural` - From cultural heritage
- `personal` - From personal experience
- `scientific` - Evidence-based, research-backed
- `mentor` - Learned from teachers/mentors
- `literature` - From books and texts

**Common Mistakes**:
- ❌ `productivity` - NOT valid (use `scientific` or `personal`)
- ❌ `habit_formation` - NOT valid (use `scientific`)

### Strength
- `core` - Fundamental, always applicable
- `supporting` - Helpful in many situations
- `contextual` - Valuable in specific contexts

### Alignment Level
- `critical` - Must align for success
- `high` - Strong alignment recommended
- `medium` - Moderate alignment beneficial
- `low` - Nice to have, not essential

---

## Example YAML

```yaml
version: 1.0
type: Principle
uid: principle:small-wins
name: Small Wins Compound
statement: Consistent small actions compound into significant results over time
category: personal
source: scientific
strength: core
alignment_level: high
description: |
  One 25-minute study block doesn't feel significant.
  But 5 blocks per week for 4 weeks is 500 minutes of focused learning.

  Small wins build:
  - Momentum (easier to continue)
  - Confidence (proof you can do it)
  - Skill (practice accumulates)

supported_knowledge_domains:
  - personal
  - professional
example_applications:
  - Study 25 minutes daily instead of 3-hour cramming sessions
  - Write 200 words daily instead of waiting for motivation
  - Exercise 10 minutes daily instead of sporadic gym sessions
measurement_criteria: |
  You're applying this when you choose to do something small today
  rather than waiting for ideal conditions.
tags:
  - habits
  - momentum
  - consistency
```

---

## Common Mistakes

### ❌ Wrong: Invalid source value
```yaml
source: productivity  # FAILS - not a valid PrincipleSource
```

### ✅ Correct: Use valid source
```yaml
source: scientific  # Valid - evidence-based principle
```

### ❌ Wrong: Invalid source value
```yaml
source: habit_formation  # FAILS - not valid
```

### ✅ Correct: Use valid source
```yaml
source: scientific  # Valid for research-backed principles
```

---

## Model Files

- **Pure Domain Model**: `principle.py` - Tier 3 (frozen dataclass)
- **DTO**: `principle_dto.py` - Tier 2 (mutable transfer)
- **Request Models**: `principle_request.py` - Tier 1 (Pydantic validation)

---

## Template Reference

Full template with all fields documented:
- [/yaml_templates/_schemas/principle_template.yaml](../../../yaml_templates/_schemas/principle_template.yaml)

---

## Usage in Learning Ecosystem

Principles guide:
- **Habits**: What principles does this habit embody?
- **Goals**: What principles guide pursuit of this goal?
- **Learning Paths**: What principles shape the learning approach?
- **Choices**: What principles inform this decision?

---

## Best Practices

### 1. Clear, Actionable Statements
```yaml
# ✅ Good - actionable and specific
statement: Brief planning before action saves time and reduces overwhelm

# ❌ Weak - vague and abstract
statement: Planning is good
```

### 2. Concrete Example Applications
```yaml
example_applications:
  - Plan study session before starting timer  # ✅ Specific
  - List 3 priorities before work day  # ✅ Actionable
  - Be more organized  # ❌ Too vague
```

### 3. Measurable Criteria
```yaml
measurement_criteria: |
  You know you're applying this principle when you can answer
  "What am I doing and why?" before starting work.
  # ✅ Observable indicator
```

---

## Notes

1. **Choose source carefully**: Determines credibility and context
2. **Category affects discoverability**: Principles can be filtered by category
3. **Strength indicates hierarchy**: Core > Supporting > Contextual
4. **Alignment level guides prioritization**: Critical principles need active work
5. **Description supports statement**: Expand on the core idea with examples and context
