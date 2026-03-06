# YAML Template Reference Guide

This directory contains **template examples** (NOT validation schemas) showing all valid fields for each YAML entity type in SKUEL.

## Purpose

These templates are **documentation**, not validation. Validation happens via Pydantic Request models in the Python code.

## Quick Reference

| Entity Type | Template File | Primary Use Case |
|-------------|---------------|------------------|
| **Ku** | [ku_template.yaml](ku_template.yaml) | Atomic knowledge unit (concept, state, practice) |
| **Article** | [article_template.yaml](article_template.yaml) | Teaching composition (essay-like narrative) |
| **Edge** | [edge_template.yaml](edge_template.yaml) | Evidence relationship between entities |
| **LearningStep** | [learning_step_template.yaml](learning_step_template.yaml) | Steps within a learning path |
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
a:{namespace}:{slug}           # a:mindfulness:breath-awareness-basics
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

## Ku vs Article

| | Ku | Article |
|---|---|---|
| **Purpose** | Atomic reference node | Teaching composition |
| **Content body** | No | Yes (full markdown) |
| **Learning metadata** | No (no complexity, learning_level) | Yes |
| **Extends** | Entity | Curriculum |
| **UID prefix** | `ku:` | `a:` |
| **Example** | "Caffeine" (substance) | "Buzzing, Stimulants, and Calm" (essay) |

Articles compose Kus via `USES_KU` relationships. Learning Steps train Kus via `TRAINS_KU`.

## Edge Templates

Edge YAML documents evidence relationships between entities (e.g., "caffeine exacerbates buzzing"). Edge ingestion is **not yet wired** in the pipeline. See `docs/roadmap/edge-ingestion-support.md`.

## Knowledge UID References in Activity Domains

Activity domain templates (task, habit, goal, event, choice) can reference both Articles and Kus in their knowledge fields:

```yaml
# In a task template
applies_knowledge_uids:
  - a:mindfulness:breath-awareness-basics  # Article (teaching content)
  - ku:mindfulness:breath                  # Ku (atomic concept)
```

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
