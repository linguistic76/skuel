Here’s a clean YAML stub for the **Principle: Not a Hobby** node, so it can sit alongside your other principle files (Serenity Prayer, Never Destroy to Create).

```yaml
# nodes/principles/not_a_hobby.v1.yaml
type: Principle
uid: principle.not_a_hobby.v1
title: "Not a Hobby"
statement: >
  SKUEL is a real enterprise, not a pastime.
  It deserves disciplined practice, clean architecture, and sustainable growth.
rationale: >
  Reframes the project from casual tinkering into a long-term business and
  teaching platform. Anchors daily choices in seriousness, stewardship,
  and the pursuit of intelligence as a higher calling.
domains: [philosophy, ops, pedagogy]
status: active
review_cycle_days: 365
tags: [business, discipline, seriousness, intelligence, work_ethic]

teaching:
  key_distinctions:
    - "Play vs Stewardship"
    - "Casual Experiment vs Sustainable Enterprise"
    - "Hobby Energy vs Business Rhythm"
  examples:
    - "Investing in Redis or AuraDB rather than hacking custom libraries."
    - "Blocking work sprints on calendar instead of drifting."
    - "Treating journal → LLM → graph as production pipeline."
  four_ps_mapping:
    preparation: "Frame SKUEL as a real business, not just an idea."
    presentation: "Show seriousness in architecture and pedagogy."
    practice: "Execute tasks as blocks with integrity."
    performance: "Publish, ship, and review outputs with users."

policy_links:
  - policy.privacy_defaults.v1
  - policy.purpose_limitation.v1

evidence_signals:
  completed_block: true
  external_service_used: true     # e.g., Redis, AuraDB
  pipeline_output_ingested: true
  published_artifact: true

connections:
  supports:
    - we.focus_execution
    - agg.skuel.core
  related:
    - principle.serenity_prayer.v1
    - principle.never_destroy_to_create.v1
notes: >
  This principle keeps the project grounded in seriousness and discipline,
  while preserving awe and playfulness in metaphor. Acts as guardrail against
  drifting back into "just tinkering."
```

---

Do you want me to also sketch a **WorkRhythm node** (sprints vs execution weeks) that links directly to this principle—so the rhythm itself gets formalized into the ontology, alongside WorkEthic?