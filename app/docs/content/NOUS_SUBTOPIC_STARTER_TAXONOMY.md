# NOUS Sub-topic — Starter Taxonomy (DRAFT PROPOSAL)

> **Status: DRAFT for Mike to review and edit.** Nothing here is auto-applied.
> No `nous_subtopic:` value is written to any Ku until you deliberately author it
> into that Ku's frontmatter. This document is a *starting point* — a menu of
> suggestions to react to, not a final vocabulary.

## What this is

The 11 flat NOUS topics (`stories`, `environment`, `intelligence`, `investment`,
`words`, `relationships`, `social`, `body`, `exercises`, `self-management`,
`self-awareness`) now have a **2nd taxonomy level**: an authored `nous_subtopic:`
field on the Ku, mirroring `nous:` exactly.

- The **mechanism** ships now (field + search facet + Askesis scope), but there is
  **no data yet** — the sub-topic vocabulary is derived from the graph, so every
  faucet is **fail-soft empty** until you author `nous_subtopic:` into Kus.
- The sub-topic control is **flat** for now (a plain list). A *dependent* dropdown
  (pick `body` → only body's sub-topics appear) needs a `nous → subtopics` map,
  which cannot exist until the vault carries the data. That is a **follow-up**.

## How to author it

Add `nous_subtopic:` alongside `nous:` in a Ku's YAML frontmatter. Both are
multi-valued (a Ku can belong to several topics / sub-topics):

```yaml
---
uid: ku.body.vagus-nerve
type: ku
title: The Vagus Nerve
nous: [body]
nous_subtopic: [nervous-system]
---
```

Slugs are **kebab-case** (`nervous-system`, not `Nervous System`). Keep them short
and stable — they become the graph vocabulary and the faucet options.

## Proposed sub-topics (SUGGESTIONS — edit freely)

The seeds marked with **†** come from the existing compound vault section slugs in
`scripts/generate_nous_files.py` (`SECTION_ICONS`); the rest are reasonable
proposals for you to accept, rename, or drop.

### stories 📖
- `personal-narrative`
- `myth-and-archetype`
- `history`
- `storytelling-craft`

### environment 🌍
- `sustainability` †
- `weather` †
- `climate`
- `nature-and-ecology`
- `place-and-home`

### intelligence 🧠
- `education` †
- `learning`
- `memory`
- `reasoning`
- `attention`

### investment 📈
- `personal-finance`
- `markets`
- `risk`
- `time-investment`
- `compounding`

### words 💬
- `meaning` †
- `vocabulary`
- `writing`
- `rhetoric`
- `reading`

### relationships 🤝
- `communication` †
- `boundaries`
- `conflict`
- `trust`
- `intimacy`

### social 👥
- `awareness` †
- `belonging`
- `culture`
- `groups-and-teams`
- `empathy`

### body 🧬
- `nervous-system` †
- `sleep`
- `movement`
- `breath`
- `nutrition`

### exercises 🏃
- `sm-metrics` †
- `practice-design`
- `reflection-prompts`
- `drills`

### self-management ⚙️
- `habits`
- `planning`
- `focus`
- `energy`
- `discipline`

### self-awareness 🪞
- `who-are-u` †
- `values`
- `emotions`
- `identity`
- `blind-spots`

## Honest caveats

- These are **starting points**, not a settled ontology. Expect to rename, merge,
  and prune once real Kus are being tagged.
- A sub-topic only "exists" (and appears as a faucet option) once at least one Ku
  is authored with it. Deleting the last Ku carrying a sub-topic removes it from
  the vocabulary — the list is graph-derived, never hardcoded.
- The `nous → nous_subtopic` dependency is intentionally **not** modeled yet. When
  the data exists, a follow-up can build the map and make the sub-topic dropdown
  filter to the chosen topic.
