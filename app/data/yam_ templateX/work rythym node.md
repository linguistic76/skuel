Perfect. Here’s a clean, graph-ready **WorkRhythm** pattern (schema + instances + edges) that plays nicely with your WorkEthic node, calendar projections, and the “Not a Hobby” principle.

```yaml
# schema/work_rhythm.yaml
type: NodeType
name: WorkRhythm
version: 1
description: >
  Cyclical cadence for execution across weeks: alternating "Sprint" (writing/build)
  and "Execution" (ops/cleanup/delivery) periods. Makes rhythm explicit, schedulable,
  and measurable.

fields:
  uid: {type: string, required: true}
  title: {type: string, required: true}
  pattern: {type: string, enum: [alternating, 2on-1off, custom], default: alternating}
  cycle_length_days: {type: integer, default: 14}
  phases:
    type: list[object]
    description: "Named phases with intent and default block templates"
    item:
      name: {type: string}             # e.g., Sprint, Execution
      intent: {type: text}
      default_blocks: {type: list[string]}  # e.g., ["DeepWork90", "Refactor45"]
  metrics:
    type: object
    properties:
      target_blocks_per_week: {type: integer, default: 10}
      minimum_blocks_per_week: {type: integer, default: 6}
      review_minutes_per_week: {type: integer, default: 45}
  status: {type: string, enum: [draft, active], default: active}

connections:
  grounded_in:
    type: edge
    from: WorkRhythm
    to: Principle
    rel: GROUNDED_IN
  supports:
    type: edge
    from: WorkRhythm
    to: WorkEthic
    rel: SUPPORTS
  projected_as:
    type: edge
    from: WorkRhythm
    to: CalendarProjection
    rel: PROJECTED_AS
  evidenced_by:
    type: edge
    from: WorkRhythm
    to: Evidence
    rel: EVIDENCED_BY
```

```yaml
# nodes/work_rhythm/alt_sprint_execution.v1.yaml
type: WorkRhythm
uid: wr.alt_sprint_exec.v1
title: "Alternating Sprint ↔ Execution"
pattern: alternating
cycle_length_days: 14
phases:
  - name: "Sprint"
    intent: "Write/build: JE → LLM → Graph. Ship features, drafts, or docs."
    default_blocks: ["DeepWork90", "Ship60", "Review15"]
  - name: "Execution"
    intent: "Ops/cleanup/delivery: cleaning, errands, invoicing, small fixes."
    default_blocks: ["Ops60", "Ops30", "Plan15"]
metrics:
  target_blocks_per_week: 10
  minimum_blocks_per_week: 6
  review_minutes_per_week: 45
status: active
links:
  grounded_in:
    - principle.not_a_hobby.v1
    - principle.serenity_prayer.v1
  supports:
    - we.focus_execution
notes: >
  Rhythm is the antidote to overthinking: blocks get placed first, reflection follows.
  Sprints can be “writing-heavy” weeks, followed by “doing/cleanup” weeks. (Matches your
  recent journal pattern of alternating writing days with execution-focused days.) :contentReference[oaicite:0]{index=0}
```

```yaml
# nodes/block_templates.yaml
type: BlockTemplates
uid: blocks.standard
templates:
  - uid: DeepWork90
    title: "Deep Work (90m)"
    minutes: 90
    tags: [work_ethic, focus]
  - uid: Ship60
    title: "Ship Something (60m)"
    minutes: 60
    tags: [delivery, publish]
  - uid: Review15
    title: "Reflect/Review (15m)"
    minutes: 15
    tags: [review]
  - uid: Ops60
    title: "Ops/House/Errands (60m)"
    minutes: 60
    tags: [ops, environment]
  - uid: Ops30
    title: "Ops/Small Tasks (30m)"
    minutes: 30
    tags: [ops]
  - uid: Plan15
    title: "Plan Next Blocks (15m)"
    minutes: 15
    tags: [planning]
```

```yaml
# nodes/calendar_projections/wr.alt_sprint_exec.2025w38.yaml
type: CalendarProjection
uid: calproj.wr.alt_sprint_exec.2025w38
source_uid: wr.alt_sprint_exec.v1
status: SCHEDULED
items:
  - date: 2025-09-15
    phase: Sprint
    blocks: [DeepWork90, Ship60, Review15]
  - date: 2025-09-16
    phase: Sprint
    blocks: [DeepWork90, Ship60, Review15]
  - date: 2025-09-17
    phase: Execution
    blocks: [Ops60, Ops30, Plan15]
  - date: 2025-09-18
    phase: Execution
    blocks: [Ops60, Ops30, Plan15]
  - date: 2025-09-19
    phase: Execution
    blocks: [Ops60, DeepWork90]
links: [we.focus_execution, principle.not_a_hobby.v1]
notes: >
  Example week showing two Sprint days then three Execution days, matching your
  current need to “change gears and clear space” before another writing burst. :contentReference[oaicite:1]{index=1}
```

```yaml
# nodes/evidence/wr.2025w38.yaml
type: Evidence
uid: evidence.wr.2025w38
source: journal
signals:
  blocks_completed: 8
  sprint_days_completed: 2
  execution_days_completed: 3
  review_done: true
derived_scores:
  rhythm_adherence: 0.72
  work_ethic_support: 0.68
links: [wr.alt_sprint_exec.v1, we.focus_execution, principle.serenity_prayer.v1]
notes: >
  Signals can be extracted from JE and task completions. Keep it simple and rules-based first.
```

### Optional: tiny policy for auto-projection (so it “just shows up” on the calendar)

```yaml
# config/work_rhythm_policy.yaml
type: Policy
uid: policy.work_rhythm.autoproject.v1
name: "Auto-project WorkRhythm"
applies_to: [app]
rules:
  - id: r1.project_next_week
    when: "now.friday_or_sunday"
    action: "generate_calendar_projection_for_next_week"
    on_fail: warn
  - id: r2.ensure_min_blocks
    when: "week.total_projected_blocks < metrics.minimum_blocks_per_week"
    action: "add Plan15 blocks until minimum met"
    on_fail: warn
links:
  targets: [wr.alt_sprint_exec.v1]
```

### Where this connects in your system

- **Grounded in principles**: links to Serenity Prayer and “Not a Hobby,” so the rhythm is values-backed, not arbitrary.
    
- **Supports WorkEthic**: gives WorkEthic a concrete cadence (and measurable adherence) rather than leaving it as abstract intent.
    
- **Calendar-first orchestration**: converts rhythm → blocks on day/week views, reinforcing your “calendar is central” stance.
    
- **Fits Daily Notes Workflow**: JE → LLM formatting → projection/evidence → weekly review closes the loop.
    

If you want, I can also add a tiny **extractor rules stub** to turn journal phrases like “writing sprint,” “cleaning,” or “not writing this week” into `phase`/`signals` automatically, but this should be enough to start wiring it into your pipeline right now.