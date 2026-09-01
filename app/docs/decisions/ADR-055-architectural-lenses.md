---
title: "ADR-055: Architectural Lenses — Subsystems + 3-Layer Lens"
updated: 2026-05-11
status: current
category: decisions
tags: [adr, decisions, architecture, mental-model, vocabulary]
related:
  - ADR-047-entity-types-replace-domain-categories
  - ADR-054-user-entry-unified-submissions
---

# ADR-055: Architectural Lenses — Subsystems (Model A) + 3-Layer Lens (Model B)

**Status:** Accepted
**Date:** 2026-04-19
**Related:**
[ADR-047 Entity Types Replace Domain Categories](ADR-047-entity-types-replace-domain-categories.md),
[ADR-054 UserEntry Unified Submissions](ADR-054-user-entry-unified-submissions.md)

> **Note (2026-05-11):** This ADR refers to "20 EntityTypes" — the count at decision time. The `EntityType` enum has since grown to 25 (added the 6 Activity Templates, retired others). See [`architecture/ENTITY_TYPE_ARCHITECTURE.md`](../architecture/ENTITY_TYPE_ARCHITECTURE.md) for the current count. The reasoning in this ADR (two lenses, coarse rollup vs. fine grain) is unchanged by the count drift.

## Context

ADR-047 retired the "domains in categories" framing and replaced it with "20 EntityTypes with behavioral traits." That is the right fine-grained ontology for code — services, backends, and protocols key off EntityType and its traits, not category membership.

But documentation, architecture discussion, and product reasoning keep wanting two things the EntityType list does not provide:

1. **A coarse rollup.** It is cumbersome to list all 20 types every time the conversation is about "the Curriculum side" or "the Learning Loop." Readers want seven groupings, not twenty items.
2. **A flow-of-information view.** The Learning Loop (Exercise → UserEntry → ExerciseReport → RevisedExercise) is a pipeline. `ContentOrigin` is close to this view but is 4-valued for code reasons (`CURATED` and `CURRICULUM` have different ownership and access) — it does not read cleanly as a cycle.

Meanwhile, the word **"domain"** is already overloaded in SKUEL:

- *Activity Domains* — a specific group of 6 EntityTypes (Task, Goal, Habit, Event, Choice, Principle)
- *Domain services* — the service layer (`core/services/`)
- *Domain models* — frozen dataclasses (the inner tier of the three-tier type system)
- *`NonKuDomain`* — a 4-valued enum for non-Entity domains (Finance, Group, Calendar, Learning)

Using "domain" for a seventh sense (the coarse ontological rollup) would make docs actively confusing. Without a shared vocabulary and a shared framing, ADRs and architecture docs drift — two authors describe the same architecture in different terms.

## Decision

We formalize **two complementary lenses** for reading SKUEL's architecture, each with its own question, its own canonical doc, and its own place in ADR frontmatter.

### Model A — Ontological ("What exists / where does this belong?")

Two levels:

| Level | Granularity | Canonical doc |
|-------|-------------|---------------|
| Fine | 20 EntityTypes (per ADR-047) | `architecture/ENTITY_TYPE_ARCHITECTURE.md` |
| Coarse | **7 Subsystems** grouped into 3 sections (Object / Context / Meta) | `architecture/SEVEN_SUBSYSTEMS.md` |

The 7 subsystems are: **Ku, Curriculum Domains, Activity Domains, Learning Loop, User, Groups, Askesis.** Object (produces entities): Ku, Curriculum Domains, Activity Domains, Learning Loop. Context (wraps entities): User, Groups. Meta (interprets entities): Askesis.

### Model B — Operational ("How information flows / what role is this playing?")

Three layers: **Curriculum → Action → Feedback.** Canonical doc: `architecture/THREE_LAYER_LENS.md`.

The 3-layer lens is a *reading of* the existing `ContentOrigin` enum, not a replacement:

| Layer | `ContentOrigin` values |
|-------|------------------------|
| Curriculum | `CURATED` + `CURRICULUM` |
| Action | `USER_CREATED` |
| Feedback | `REPORT` |

`ContentOrigin` stays 4-valued in code. No `ContentLayer` enum is added.

### Vocabulary

For the Model A coarse level, we adopt **"Subsystems"** as the canonical term. "Domain" continues to be used only in the senses the code already owns (Activity Domains, domain services, domain models, `NonKuDomain`). New docs and ADRs should say *subsystem* when they mean the seven-way rollup.

### ADR / doc framing

New architecture docs and ADRs should name the lens they operate in — e.g. "this is an Object/Learning-Loop change" or "this lives in the Feedback layer." This is a lightweight convention, not a schema field.

## Alternatives Considered

1. **One lens only.** Pick either ontological or operational and drop the other. Rejected — they answer different questions, and collapsing them produces worse docs (either the Learning Loop looks like a flat group of EntityTypes, losing the cycle; or all 20 types get crammed into three buckets, losing ownership and access distinctions).
2. **Add a `ContentLayer` enum to code.** A 3-valued enum mirroring the lens. Rejected — it adds a redundant surface next to `ContentOrigin` without new capability, and every new entity type would need both values kept in sync. The lens is documentation-only by design.
3. **Keep using "Domains" at the coarse level.** Rejected because of the vocabulary overload above. "Subsystems" is one more word to learn, but it pays for itself every time someone reads a doc and does not have to disambiguate which sense of "domain" is meant.
4. **Two ADRs (one for vocabulary, one for the two-lens model).** Rejected because the sub-choices are not separable in practice — picking "Subsystems" presupposes the two-lens split that motivates needing a coarse term at all. One ADR keeps the decision coherent.

## Consequences

**Positive**

- Two canonical architecture docs (`SEVEN_SUBSYSTEMS.md`, `THREE_LAYER_LENS.md`) with a clear division of labor.
- Future ADRs and docs have a shared vocabulary. Reviewers can check that an architectural claim names its lens.
- The MVP scope call (teacher-led + both tracks, Askesis deferred) lives in the `SEVEN_SUBSYSTEMS.md` matrix, not in this ADR — product decisions can evolve without ADR churn.

**Negative**

- One more term ("Subsystems") for new contributors to learn.
- Two docs to keep in sync as the architecture evolves. Mitigation: both docs cross-link and both reference this ADR.

**No code changes.** This ADR introduces no new enums, no new types, no new services. It is a documentation and vocabulary decision.

## Out of Scope

- **MVP scope.** The 7×3 matrix in `SEVEN_SUBSYSTEMS.md` captures the current MVP shape (teacher-led + both tracks, Askesis deferred). That is a product decision, not an architecture one, and it can move without revisiting this ADR.
- **Renaming existing code.** `ContentOrigin` stays 4-valued. `NonKuDomain`, Activity Domains, domain services, and domain models keep their names. This ADR only reserves "subsystem" as the canonical term for the coarse Model A level.
