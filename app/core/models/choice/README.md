# Choice Domain Model

The Choice domain represents decision-making entities in SKUEL - structured ways to evaluate and make choices.

## Overview

Choices help structure decision-making by tracking:
- Multiple options with feasibility scores
- Decision criteria and constraints
- Stakeholder impact
- Outcome evaluation and lessons learned

**Critical Difference**: Choice is the ONLY domain model that **requires `user_uid`** field.

## YAML Structure

### Required Fields

| Field | Type | Pattern | Description |
|-------|------|---------|-------------|
| `version` | String | `1.0` | YAML schema version |
| `type` | String | `Choice` | Entity type identifier |
| `uid` | String | `choice:name` | Unique identifier (e.g., `choice:start-25min-now`) |
| `title` | String | 1-200 chars | Display title |
| `description` | String | 1-1000 chars | Detailed description |
| `user_uid` | String | UID or "system" | **REQUIRED** - User this choice belongs to ⚠️ |

### Optional Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `choice_type` | Enum | `binary` | Type of choice structure |
| `status` | Enum | `pending` | Current choice status |
| `priority` | Enum | `medium` | Urgency/importance level |
| `domain` | Enum | `personal` | Life domain |
| `decision_criteria` | List[str] | `[]` | Factors to consider (max 20) |
| `constraints` | List[str] | `[]` | Limitations/requirements |
| `stakeholders` | List[str] | `[]` | Who is affected |
| `decision_deadline` | DateTime | `null` | When decision must be made |
| `options` | List[ChoiceOption] | `[]` | Available options (max 50) |
| `tags` | List[str] | `[]` | Categorization tags (max 10) |

### Metadata Fields (Auto-Populated)

| Field | Type | Description |
|-------|------|-------------|
| `created_at` | DateTime | When choice was created |

⚠️ **IMPORTANT**: Choice has `created_at` but **NO `updated_at`** field (different from Task/Event/Goal/Habit)!

## Enum Values

### choice_type
- `binary` - Yes/No, do it or don't (most common)
- `multiple` - Pick one from several options
- `ranking` - Order preferences
- `allocation` - Distribute resources
- `strategic` - Long-term direction
- `operational` - Day-to-day decisions

### status
- `pending` - Choice not yet made (default)
- `decided` - Choice made
- `implemented` - Choice put into action
- `evaluated` - Outcome assessed
- `archived` - Historical record

### priority (from shared_enums)
- `low` - Can wait
- `medium` - Should decide soon (default)
- `high` - Needs decision soon
- `critical` - Urgent decision required

### domain (from shared_enums)
- `personal` - Personal life decisions (default)
- `professional` - Career/work decisions
- `technical` - Technical/tool choices
- `health` - Health and wellness
- `financial` - Money and resources
- `social` - Relationships and community

## ChoiceOption Structure

Each choice can have multiple options with evaluation metrics:

| Field | Type | Range | Description |
|-------|------|-------|-------------|
| `title` | String | 1-200 chars | Option title |
| `description` | String | 1-1000 chars | Option description |
| `feasibility_score` | Float | 0.0-1.0 | How doable is this? |
| `risk_level` | Float | 0.0-1.0 | How risky? (higher = riskier) |
| `potential_impact` | Float | 0.0-1.0 | How impactful? |
| `resource_requirement` | Float | 0.0-1.0 | How resource-intensive? |
| `estimated_duration` | Integer | Minutes | How long will it take? |
| `dependencies` | List[str] | UIDs | What must happen first? |
| `tags` | List[str] | Max 10 | Categorization |

## Example YAML

```yaml
version: 1.0
type: Choice
uid: choice:start-25min-now
title: Start a 25-minute block now
description: Pick one topic, set a timer, go.
user_uid: system                    # REQUIRED for Choice!

choice_type: binary                 # Yes/no decision
status: pending
priority: high
domain: personal

decision_criteria:
  - Do I have time available right now?
  - Is there a clear objective?
  - Can I minimize distractions quickly?

constraints:
  - Requires 25 minutes of uninterrupted time
  - Requires a clear study topic
  - Requires quiet environment

stakeholders:
  - self

outcomes:
  - Complete one focused study block
  - Build momentum for future sessions
  - Log tangible progress

tags:
  - focus
  - pomodoro
```

## Common Mistakes

### ❌ CRITICAL: Missing user_uid
```yaml
type: Choice
uid: choice:example
title: Example Choice
description: Some choice
# FAILS - Choice REQUIRES user_uid field!
```

### ✅ Correct: Include user_uid
```yaml
type: Choice
uid: choice:example
title: Example Choice
description: Some choice
user_uid: system                    # ✅ Required field present
```

---

### ❌ Wrong: Trying to set updated_at
```yaml
created_at: 2025-10-04T10:00:00
updated_at: 2025-10-04T11:00:00     # FAILS - Choice has no updated_at!
```

### ✅ Correct: Only use created_at
```yaml
created_at: 2025-10-04T10:00:00     # ✅ Auto-populated, can be omitted
# No updated_at field
```

---

### ❌ Wrong: Invalid choice_type
```yaml
choice_type: yes_no                 # FAILS - not a valid enum value
```

### ✅ Correct: Use valid choice_type
```yaml
choice_type: binary                 # ✅ Valid enum value
```

---

### ❌ Wrong: Too many decision criteria
```yaml
decision_criteria:
  - Criterion 1
  - Criterion 2
  # ... 25 total criteria
  # FAILS - max 20 decision criteria allowed
```

### ✅ Correct: Keep criteria concise
```yaml
decision_criteria:
  - Is it feasible?
  - Does it align with goals?
  - Can we afford it?
  - What are the risks?
  # ✅ Under 20 criteria
```

---

### ❌ Wrong: Decision deadline in the past
```yaml
decision_deadline: 2024-01-01T00:00:00  # FAILS - must be future
```

### ✅ Correct: Future deadline
```yaml
decision_deadline: 2025-12-31T23:59:59  # ✅ Future date
```

## Field Differences from Other Models

⚠️ **Choice is UNIQUE** - Pay attention to these differences:

| Feature | Choice | Task/Event/Goal/Habit | Notes |
|---------|--------|----------------------|-------|
| **User Ownership** | YES `user_uid` | NO `user_uid` | Choice is ONLY model requiring `user_uid` ⚠️ |
| **Display Name Field** | `title` | `title` (except Habit uses `name`) | Same as most models |
| **Timestamps** | `created_at` ONLY | `created_at`, `updated_at` | Choice has NO `updated_at` ⚠️ |
| **Options** | Has `options` list | No options concept | Only Choice has embedded options |
| **Decision Tracking** | Full decision workflow | Single status field | Choice tracks entire decision process |

## Business Logic Methods

The Choice domain model (Tier 3) includes these business logic methods:

### Status Checks
- `is_pending()` - Check if choice is still pending
- `is_decided()` - Check if choice has been made
- `is_overdue()` - Check if past deadline without decision

### Option Analysis
- `get_selected_option()` - Get the chosen option
- `get_available_options()` - Get all options
- `get_feasible_options(threshold)` - Get only feasible options
- `rank_options(preferences)` - Rank options by user preferences

### Complexity & Quality
- `calculate_decision_complexity()` - Complexity score (0-1)
- `get_decision_quality_score()` - Quality based on satisfaction
- `has_high_stakes()` - Determine if high-stakes decision
- `time_until_deadline()` - Minutes until deadline

### Insights & Learning
- `generate_insights()` - Generate decision insights
- `needs_follow_up()` - Check if needs evaluation

### Graph Intelligence (Phase 1-4 Integration)
- `build_decision_context_query(depth)` - APOC query for decision context
- `build_impact_analysis_query()` - APOC query for impact analysis
- `build_knowledge_requirements_query(depth)` - APOC query for required knowledge
- `get_suggested_query_intent()` - Recommended QueryIntent for this choice

## Model File Locations

```
/core/models/choice/
├── choice.py                    # Tier 3: Frozen domain model (Choice, ChoiceOption)
├── choice_dto.py                # Tier 2: Mutable DTO for data transfer
├── choice_request.py            # Tier 1: Pydantic validation models
└── choice_converters.py         # Conversion between tiers
```

## Template Reference

Full YAML template with all fields and documentation:
`/home/mike/skuel0/yaml_templates/_schemas/choice_template.yaml`

## Validation Rules

**From Pydantic Request Models** (`choice_request.py`):

- `title`: 1-200 characters
- `description`: 1-1000 characters
- `decision_criteria`: Max 20 items
- `options`: Max 50 options per choice
- `decision_deadline`: Must be in the future (if provided)
- `tags`: Max 10 tags per choice
- Option `tags`: Max 10 tags per option
- Option scores: All in 0.0-1.0 range

## Best Practices

1. **Always include `user_uid`** - This is the only domain that requires it
2. **Use `binary` for simple yes/no decisions** - Most common choice type
3. **Add decision_criteria** - Help users evaluate the choice systematically
4. **Clarify constraints** - Make viable conditions explicit
5. **Track outcomes** - Use satisfaction_score and lessons_learned for growth
6. **System vs User choices** - Use `user_uid: system` for curriculum choices shared across users
7. **Keep options manageable** - 2-5 options is ideal; max 50 allowed
8. **Set realistic deadlines** - When the decision truly needs to be made
9. **Identify stakeholders** - Can be `["self"]` for personal choices
10. **Evaluate after implementation** - Track satisfaction and lessons learned

## Notes

- Choice domain is designed for structured decision-making
- ChoiceOption allows detailed evaluation of each possibility
- Decision criteria and constraints guide systematic evaluation
- Outcome tracking enables learning from past decisions
- Graph intelligence methods (Phase 1-4) provide decision context
- Strategic choices use HIERARCHICAL intent for long-term impact analysis
- Binary choices use SPECIFIC intent for focused analysis
- Multiple/ranking choices use RELATIONSHIP intent to compare options
