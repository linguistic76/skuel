# Mindfulness 101 Domain Bundle
## Light & Conversational Introduction to Mindfulness

A complete, beginner-friendly curriculum bundle for starting a mindfulness practice.

## Bundle Contents

### Atomic Kus (2)
- `ku:mindfulness:breath` - The breath as a mindfulness anchor
- `ku:mindfulness:attention` - The cognitive capacity to focus awareness

### Lessons (3)
- `l:mindfulness:breath-awareness-basics` - Foundation of breath awareness practice
- `l:mindfulness:posture-basics` - Simple posture guidelines
- `l:mindfulness:mind-wandering-happens` - Understanding and working with wandering mind

### Learning Steps (2)
- `ls:mindfulness-101:step-1` - Two Minutes Today
- `ls:mindfulness-101:step-2` - Name The Wanders

### Learning Path (1)
- `lp:mindfulness-101` - Complete beginner sequence

### Supporting Entities (11)

**Principles** (2)
- `principle:small-steps` - Small Steps Beat Big Bursts
- `principle:attention-over-intensity` - Attention Over Intensity

**Choices** (3)
- `choice:2-minutes-right-now` - Do Two Minutes Right Now
- `choice:2-minutes-before-bed` - Two Minutes Before Bed
- `choice:label-one-wander` - Label One Wander

**Habits** (2)
- `habit:daily-2min-breath` - Daily Two-Minute Breath
- `habit:label-wander-daily` - Label a Wander Daily

**Tasks** (2)
- `task:log-first-5-sessions` - Log your first five sessions
- `task:reflect-on-first-week` - Reflect on your first week

**Events** (1)
- `event:practice-block-2min` - Breath Practice -- 2 min (calendar template)

**Goals** (1)
- `goal:mindfulness-beginner` - Build a gentle daily starter practice

**Total**: 21 entities

## Curriculum Model

This bundle demonstrates SKUEL's four-entity curriculum model:

```
Ku (atom)          Lesson (teaching)        Ls (step)          Lp (path)
ku:breath    <--   l:breath-awareness  -->   ls:step-1    -->   lp:mindfulness-101
ku:attention <--   l:mind-wandering    -->   ls:step-2    -->
                   USES_KU                   TRAINS_KU
```

- **Kus** are atomic reference nodes (breath, attention)
- **Lessons** compose Kus into learning content via `USES_KU`
- **Learning Steps** train specific Kus via `TRAINS_KU` and reference Lessons for content
- **Learning Path** sequences the steps

## Ingestion

### Using UnifiedIngestionService

```python
from core.services.ingestion import UnifiedIngestionService
from pathlib import Path

# Ingest entire bundle (uses manifest for dependency order)
result = await ingestion_service.ingest_directory(
    Path("yaml_templates/domains/mindfulness_101")
)
```

### Import Order (from manifest)

1. **Kus** - Atomic knowledge units (referenced by Lessons)
2. **Lessons** - Teaching content (references Kus)
3. **Supporting Entities** - Principles, choices, habits, tasks, events, goals
4. **Learning Steps** - Steps that reference Lessons and train Kus
5. **Learning Path** - Path that sequences steps

## Files

```
mindfulness_101/
  README.md (this file)
  manifest.yaml
  # Atomic Kus
  ku_breath.yaml
  ku_attention.yaml
  # Lessons (units for learning)
  lesson_breath-awareness-basics.yaml
  lesson_posture-basics.yaml
  lesson_mind-wandering-happens.yaml
  # Learning
  ls_mindfulness-101_step-1.yaml
  ls_mindfulness-101_step-2.yaml
  lp_mindfulness-101.yaml
  # Supporting
  principle_small-steps.yaml
  principle_attention-over-intensity.yaml
  choice_2-minutes-right-now.yaml
  choice_2-minutes-before-bed.yaml
  choice_label-one-wander.yaml
  habit_daily-2min-breath.yaml
  habit_label-wander-daily.yaml
  task_log-first-5-sessions.yaml
  task_reflect-on-first-week.yaml
  event_practice-block-2min.yaml
  goal_mindfulness-beginner.yaml
```

## Design Principles

1. **Tiny & Sustainable** - 2-minute sessions, not 20-minute marathons
2. **Conversational** - Friendly language, no spiritual baggage
3. **Practice-Oriented** - Every concept links to concrete action
4. **Non-Judgmental** - Mind wandering is expected and welcomed
5. **Beginner-Friendly** - No prerequisites, clear progression
