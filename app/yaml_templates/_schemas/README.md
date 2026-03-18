# YAML Template Reference Guide

This directory contains **template examples** (NOT validation schemas) showing all valid fields for each YAML entity type in SKUEL.

## Purpose

These templates are **documentation**, not validation. Validation happens via Pydantic Request models in the Python code.

## Quick Reference

| Entity Type | Template File | Primary Use Case |
|-------------|---------------|------------------|
| **Ku** | [ku_template.yaml](ku_template.yaml) | Atomic knowledge unit (concept, state, practice) |
| **Lesson** | [lesson_template.yaml](lesson_template.yaml) | A unit for learning (composes Kus) |
| **Edge** | [edge_template.yaml](edge_template.yaml) | Evidence relationship between entities |
| **LearningStep** | [learning_step_template.yaml](learning_step_template.yaml) | A collection of lessons |
| **LearningPath** | [learning_path_template.yaml](learning_path_template.yaml) | Structured learning sequences |
| **Principle** | [principle_template.yaml](principle_template.yaml) | Guiding principles and values |
| **Choice** | [choice_template.yaml](choice_template.yaml) | Decision points for learners |
| **Habit** | [habit_template.yaml](habit_template.yaml) | Recurring behaviors to build/break |
| **Task** | [task_template.yaml](task_template.yaml) | Actionable work items |
| **Event** | [event_template.yaml](event_template.yaml) | Calendar events and milestones |
| **Goal** | [goal_template.yaml](goal_template.yaml) | Objectives and outcomes |

## UID Patterns

```yaml
# Curriculum
ku:{namespace}:{slug}          # ku:attention:buzzing
l:{namespace}:{slug}           # l:mindfulness:breath-awareness-basics
ls:{path}:{step}               # ls:mindfulness-101:step-1
lp:{path}                      # lp:mindfulness-101

# Activity Domains
task:{name}                    # task:log-first-5-sessions
habit:{name}                   # habit:daily-2min-breath
goal:{name}                    # goal:mindfulness-beginner
choice:{name}                  # choice:2-minutes-right-now
event:{name}                   # event:practice-block-2min
principle:{name}               # principle:small-steps
```

## Ku vs Lesson

| | Ku | Lesson |
|---|---|---|
| **Purpose** | Atomic reference node | Teaching composition |
| **Content body** | No | Yes (full markdown) |
| **Learning metadata** | No (no complexity, learning_level) | Yes |
| **Extends** | Entity | Curriculum |
| **UID prefix** | `ku:` | `l:` |
| **Example** | "Caffeine" (substance) | "Buzzing, Stimulants, and Calm" (essay) |

Lessons compose Kus via `USES_KU` relationships. Learning Steps train Kus via `TRAINS_KU`.

## Edge Templates

Edge YAML documents evidence relationships between entities (e.g., "caffeine exacerbates buzzing"). Edge ingestion is fully wired — both single-file and batch ingestion detect `type: Edge` and create relationships with evidence properties automatically.

## Cross-Domain Relationships via `connections:`

Activity domain templates (task, habit, goal, event, choice) declare cross-domain
relationships under the `connections:` key. Field names match the relationship
registry's `yaml_field_path` values — on ingestion, each becomes a graph edge.

```yaml
# In a task template
connections:
  applies_knowledge:
    - l:mindfulness:breath-awareness-basics  # Lesson (teaching content)
    - ku:mindfulness:breath                  # Ku (atomic concept)
  fulfills_goal:
    - goal:mindfulness-beginner
  reinforces_habit:
    - habit:daily-2min-breath
```

See `_schemas/{entity}_template.yaml` for the complete `connections:` fields per type.

## Validation Flow

```
YAML File
    |
Load as Python dict
    |
[Pydantic Request Model] -- Validation happens HERE
    |
 DTO (mutable transfer object)
    |
Pure Domain Model (frozen dataclass)
    |
Neo4j Database
```

**Validation is done by Pydantic**, not by these YAML templates.
