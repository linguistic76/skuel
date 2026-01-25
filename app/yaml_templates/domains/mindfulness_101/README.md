# Mindfulness 101 Domain Bundle
## Light & Conversational Introduction to Mindfulness

A complete, beginner-friendly curriculum bundle for starting a mindfulness practice.

## Bundle Contents

### Core Curriculum (6 entities)

**Knowledge Units** (ku)
- `ku:breath-awareness-basics` - Foundation of breath awareness practice
- `ku:posture-basics` - Simple posture guidelines
- `ku:mind-wandering-happens` - Understanding and working with wandering mind

**Learning Steps** (ls)
- `ls:mindfulness-101:step-1` - Two Minutes Today
- `ls:mindfulness-101:step-2` - Name The Wanders

**Learning Path** (lp)
- `lp:mindfulness-101` - Complete beginner sequence

### Supporting Entities (13 entities)

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
- `event:practice-block-2min` - Breath Practice — 2 min (calendar template)

**Goals** (1)
- `goal:mindfulness-beginner` - Build a gentle daily starter practice

**Conversations** (1)
- `conversation:2025-10-04:breath-starter` - (To be created)

**Total**: 19 entities (18 created + 1 pending)

## Learning Journey

### Step 1: Two Minutes Today
**Objective**: Try one two-minute breath session, note what you notice

**What You'll Learn**:
- Basic breath awareness technique
- Simple posture setup
- Foundation for daily practice

**Practice**:
- Choose: Do 2 minutes right now OR 2 minutes before bed
- Build habit: Daily 2-minute breath
- Complete task: Log first 5 sessions

**Guided by**: Principle of Small Steps

### Step 2: Name The Wanders
**Objective**: Label mind-wanders without judgment once per session

**What You'll Learn**:
- Mind wandering is normal and expected
- Meta-awareness through gentle labeling
- Non-judgmental observation

**Practice**:
- Choose: Label one wander per session
- Build habit: Label wander daily
- Complete task: Reflect on first week

**Guided by**: Principle of Attention Over Intensity

## Philosophy

### Small Steps Beat Big Bursts
Sustainable change comes from small, repeated actions. Two minutes daily beats one hour weekly.

### Attention Over Intensity
Quality of attention matters more than intensity of effort. Mindfulness is about noticing, not forcing.

## Success Criteria (Goal: mindfulness-beginner)

✅ Complete 5+ breath awareness sessions per week
✅ Maintain practice for 4 consecutive weeks
✅ Log reflections on progress
✅ Develop ability to notice mind wandering

### Milestones
1. **First Session Complete** - Complete first 2-minute breath session
2. **First Week Complete** - 5 sessions completed in first 7 days
3. **Labeling Practice Added** - Begin labeling mind-wanders
4. **Four Weeks Complete** - Maintain 5+ sessions/week for 4 weeks

## Relationship Graph

```
Knowledge Units (ku)
  └─> Learning Steps (ls)
        └─> Learning Path (lp)

Principles
  └─> Guide Learning Steps
  └─> Inspire Habits

Choices
  └─> Offered at Learning Steps
  └─> Create Tasks
  └─> Nudge Habits

Habits
  └─> Reinforce Knowledge
  └─> Support Goals
  └─> Project as Events

Tasks
  └─> Practice Knowledge
  └─> Support Goals
  └─> Project as Events

Goal
  └─> Aligns with Habits, Tasks, Principles, Knowledge
```

## Ingestion

### Using YamlIngestionService

```python
from core.services.yaml_ingestion_service import YamlIngestionService
from pathlib import Path
from neo4j import AsyncGraphDatabase

# Connect to Neo4j
driver = AsyncGraphDatabase.driver(
    "bolt://localhost:7687",
    auth=("neo4j", "password")
)

# Create service
service = YamlIngestionService(driver)

# Ingest entire bundle (uses manifest for dependency order)
result = await service.ingest_domain_bundle(
    Path("yaml_templates/domains/mindfulness_101")
)

if result.is_ok:
    stats = result.value
    print(f"✅ Created {stats['total_successful']} entities")
    print(f"Entities: {stats['entities_created']}")
```

### Import Order (from manifest)

1. **Knowledge Units** - Foundation content
2. **Supporting Entities** - Principles, choices, habits, tasks, events, goals
3. **Learning Steps** - Steps that reference knowledge and supporting entities
4. **Learning Path** - Path that references steps
5. **Conversations** - Delivery layer that ties it all together

## Querying the Graph

### Find the learning path
```cypher
MATCH (lp:Lp {uid: 'lp:mindfulness-101'})
RETURN lp
```

### Find all steps in path
```cypher
MATCH (lp:Lp {uid: 'lp:mindfulness-101'})-[:HAS_STEP]->(ls:Ls)
RETURN ls ORDER BY ls.sequence
```

### Find knowledge for a step
```cypher
MATCH (ls:Ls {uid: 'ls:mindfulness-101:step-1'})
MATCH (ls)-[:PRIMARY_KNOWLEDGE]->(ku:Ku)
RETURN ku
```

### Find practice opportunities
```cypher
MATCH (ls:Ls {uid: 'ls:mindfulness-101:step-1'})
OPTIONAL MATCH (ls)-[:SUGGESTS_HABIT]->(h:Habit)
OPTIONAL MATCH (ls)-[:ASSIGNS_TASK]->(t:Task)
RETURN ls, collect(h) as habits, collect(t) as tasks
```

### Find guiding principles
```cypher
MATCH (lp:Lp {uid: 'lp:mindfulness-101'})
MATCH (lp)-[:HAS_STEP]->(ls)
MATCH (ls)-[:HAS_PRINCIPLE]->(p:Principle)
RETURN DISTINCT p
```

## Files

```
mindfulness_101/
├── README.md (this file)
├── manifest.yaml
│
├── ku_breath-awareness-basics.yaml
├── ku_posture-basics.yaml
├── ku_mind-wandering-happens.yaml
│
├── ls_mindfulness-101_step-1.yaml
├── ls_mindfulness-101_step-2.yaml
│
├── lp_mindfulness-101.yaml
│
├── principle_small-steps.yaml
├── principle_attention-over-intensity.yaml
│
├── choice_2-minutes-right-now.yaml
├── choice_2-minutes-before-bed.yaml
├── choice_label-one-wander.yaml
│
├── habit_daily-2min-breath.yaml
├── habit_label-wander-daily.yaml
│
├── task_log-first-5-sessions.yaml
├── task_reflect-on-first-week.yaml
│
├── event_practice-block-2min.yaml
│
└── goal_mindfulness-beginner.yaml
```

## Design Principles

1. **Tiny & Sustainable** - 2-minute sessions, not 20-minute marathons
2. **Conversational** - Friendly language, no spiritual baggage
3. **Practice-Oriented** - Every concept links to concrete action
4. **Non-Judgmental** - Mind wandering is expected and welcomed
5. **Beginner-Friendly** - No prerequisites, clear progression

## Next Steps

After completing Mindfulness 101, learners can:
- Extend session duration gradually
- Explore walking meditation
- Add body scan practice
- Develop loving-kindness meditation
- Join community practice groups

## Credits

Inspired by:
- Jon Kabat-Zinn - Mindfulness-Based Stress Reduction (MBSR)
- BJ Fogg - Tiny Habits methodology
- James Clear - Atomic Habits principles
- Buddhist meditation traditions (secularized presentation)
