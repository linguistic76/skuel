Love it. Here’s a clean, graph-ready **Principle: Serenity Prayer** you can drop in today, plus optional edges to wire it into WorkEthic and your JE.

```yaml
# nodes/principles/serenity_prayer.v1.yaml
type: Principle
uid: principle.serenity_prayer.v1
title: Serenity Prayer
statement: >
  Grant me the serenity to accept the things I cannot change,
  courage to change the things I can,
  and wisdom to know the difference.
rationale: >
  Re-centers action on controllables and reduces energy lost to overthinking.
  Aligns WorkEthic with integrity—start, finish, and release.
domains: [philosophy, ops, pedagogy]
status: active
review_cycle_days: 365
tags: [acceptance, courage, wisdom, work_ethic, integrity]

# Teach it (content hooks)
teaching:
  key_distinctions:
    - "Thinking vs Doing"
    - "Control vs Influence vs Observe"
  examples:
    - "Place the block on the calendar (Doing), not just plan (Thinking)."
    - "Tidy the workspace you control; release weather or other people’s moods."
  four_ps_mapping:
    preparation: "Choose one controllable for today’s block."
    presentation: "Read the statement aloud; visualize today’s controllable."
    practice: "Do a 60–90 min focused block on that one controllable."
    performance: "Log completion + 2-line reflection: accept/change/learned."

# Operationalization (so it lives at the edges too)
policy_links:
  - policy.privacy_defaults.v1       # example: clarity over control at data edges
  - policy.purpose_limitation.v1
adapters_guidance:
  calendar_default_block_minutes: 90
  recommend_reset_task_when_score_below: 0.45   # ties into WorkEthic scoring

# Evidence you want to see (so the engine can score it)
evidence_signals:
  accepted_uncontrollable: true
  named_single_controllable: true
  completed_focused_block: true
  reflected_two_lines: true

connections:
  supports:
    - we.focus_execution               # WorkEthic node you created
  related:
    - principle.never_destroy_to_create.v1
notes: >
  Keep it practical: one controllable per block. Serenity is not passivity; it’s
  conserved energy directed into the next right action.
```

Optional edges (wire it into today’s note and WorkEthic):

```yaml
# edges/principles-links.yaml
- type: SUPPORTS
  from: principle.serenity_prayer.v1
  to: we.focus_execution

# If your 09-15-4 journal has a UID, connect it:
- type: MENTIONED_IN
  from: principle.serenity_prayer.v1
  to: je.2025-09-15-4
```

Tiny **habit + task** pair that puts the prayer into motion:

```yaml
# nodes/habits/serenity_one_controllable.yaml
type: Habit
uid: habit.serenity.one_controllable
title: Name One Controllable (Daily)
cadence: daily
estimated_minutes: 3
tags: [serenity_principle, prep]
links: [principle.serenity_prayer.v1, we.focus_execution]

# nodes/tasks/serenity_block_today.yaml
type: Task
uid: task.serenity.block.today
title: Do the Block on the One Controllable
scheduled_for: {{TODAY}}
estimated_minutes: 90
tags: [work_ethic, focus, serenity_principle]
links: [habit.serenity.one_controllable, we.focus_execution]
```

If you want, I can also draft a **2-rule extractor** that turns lines in your JE into `evidence_signals` (e.g., detect “overthinking” → `accepted_uncontrollable: true`; detect an explicit block or schedule → `completed_focused_block: true`) so the WorkEthic score nudges you back to action automatically.