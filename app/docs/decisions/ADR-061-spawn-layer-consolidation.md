---
title: "ADR-061: Spawn-Layer Consolidation — DomainSpawnSpec Registry"
updated: 2026-06-20
status: current
category: decisions
tags: [adr, decisions, ps-engagement, spawn, activity-templates, dry, type-safety]
related:
  - ADR-046-activity-domains-not-ku-subtypes
  - ADR-056-service-layer-label-split
  - ADR-059-askesis-engagement-alignment
---

# ADR-061: Spawn-Layer Consolidation — `DomainSpawnSpec` Registry

**Status:** Accepted
**Date:** 2026-05-20
**Related:**
[ADR-046 Activity Domains Are Not Ku Subtypes](ADR-046-activity-domains-not-ku-subtypes.md),
[ADR-056 Service-Layer Label Split](ADR-056-service-layer-label-split.md),
[ADR-059 Askesis ↔ Engagement Alignment](ADR-059-askesis-engagement-alignment.md)

## Context

The PathStep engagement system gives each of the 6 Activity Domains a dual
existence: a teacher/PS-owned **template** (`TaskTemplate`, `GoalTemplate`, …,
extending `Entity`, `user_uid = None`, ContentOrigin CURRICULUM) and a
user-owned **instance** (`Task`, `Goal`, …, extending `UserOwnedEntity`,
`user_uid = student`, ContentOrigin USER_CREATED). When a student engages a
PathStep, `_SpawnOrchestrator`
(`core/services/ps_engagement/_spawn_orchestrator.py`) reads the PS's
`TemplateBundle` and produces a personalized instance per template, resolving
`RelativeOffset` fields to absolute dates and `*_template_uid` refs to
`*_uid`/graph edges, in a 4-layer dependency order.

A redundancy audit of this subsystem was requested. It found the
**two-entity split is correct** — templates and instances have incompatible
state machines (`DRAFT→ACTIVE→ARCHIVED` vs `ENGAGED→OWNED`/deleted),
incompatible ownership and retention, and the `*_template_uid` vs `*_uid`
distinction is statically type-checked. Collapsing them into one model with an
`is_template` flag would force conditional logic and conditional field naming
across every operation that differs between the two. That is not in question.

The audit did surface redundancy in three places:

1. **Twin model field declarations.** Across the 6 pairs, ~74 fields are
   identical in name and type, ~16 are transform pairs (`due_offset:
   RelativeOffset` → `due_date: date`; `*_template_uid` → `*_uid`), ~49 are
   instance-only runtime state (`current_streak`, `progress_percentage`, …),
   and ~1 is template-only. Roughly 90 of ~140 non-base declarations are
   mechanically related across the pair, hand-written twice.

2. **Six-fold fan-out in the spawn layer.** Adding or changing an activity
   domain touches ~8 locations: the six near-identical `_build_*` functions
   (`_spawn_orchestrator.py:429-613`), the per-domain pre-allocate loop
   (`:198-212`), the four explicit spawn blocks (`:214-291`), the
   `*_OFFSET_REWRITES` / `*_FIELD_REWRITES` / `*_CROSS_EDGES` tables
   (`:77-152`), `TemplateBundle`'s six tuple fields, `ActivityBackends`'s six
   fields, and `_TemplateLoader`'s six ctor params + `rel_to_backend_and_class`
   table. The six `_build_*` functions differ only by instance class, the
   three rewrite tables, and whether an engagement anchor is used (Principle
   alone has no offsets).

3. **Denormalized PS back-reference.** Commit `ea548c34` populated
   `source_path_step_uid` uniformly on all six spawned instances. This
   duplicates what the `(instance)-[:SPAWNED_FROM]->(template)<-[:HAS_*_TEMPLATE]-(PS)`
   2-hop path already encodes. The duplication is justified — activities
   created by non-template scheduling paths set the field but have **no**
   `SPAWNED_FROM` edge, so the field is the universal back-reference — but the
   two carry subtly different semantics (the field freezes the *spawn-time* PS;
   the edge path reflects *current* template ownership) and no doc states which
   is authoritative.

## Decision

**1. Affirm the template/instance split.** It is the minimal correct design for
the divergent state machines, ownership, and type-safe cross-references. No
change.

**2. Consolidate the six-fold spawn fan-out behind a single `DomainSpawnSpec`
registry.** Define one frozen spec per domain that carries everything the
orchestrator currently spreads across ~8 locations:

```python
@dataclass(frozen=True)
class DomainSpawnSpec:
    instance_cls: type[UserOwnedEntity]
    template_cls: type[Entity]
    layer: int                                            # 1..4 — drives ordering
    collection_attr: str                                  # on TemplateBundle AND ActivityBackends
    uid_prefix: str                                       # UIDGenerator prefix
    offset_rewrites: tuple[tuple[str, str, OffsetKind], ...] = ()
    field_rewrites: dict[str, str] = field(default_factory=dict)
    cross_edges: tuple[tuple[str, str], ...] = ()

SPAWN_REGISTRY: tuple[DomainSpawnSpec, ...] = (...)   # one entry per domain
```

`spawn()` then becomes: pre-allocate UIDs by iterating the registry, sort specs
by `layer`, and call a single generic `_build(spec, template, student_uid,
ps_uid, anchor, uid_map)` that performs exactly what the six builders do today
(the shared kwargs assembly plus `_resolve_offsets`/`_resolve_refs` — already
generic). Adding a 7th domain becomes **one registry entry** instead of edits
in eight places.

The standard objection — "a generic builder loses the concrete `-> Task`
return type" — is resolved by parameterising the spec: `DomainSpawnSpec` is
generic in the instance type, so `TASK_SPEC` is a `DomainSpawnSpec[Task]` and
`_build(TASK_SPEC, …)` is statically a `Task`. There is **no** type-safety cost
— the per-domain unit tests assert concrete attributes (`task.due_date`,
`goal.start_date`, …) and type-check.

**As built (2026-05-20).** Implemented as above with three refinements: (a)
`DomainSpawnSpec` is `Generic[InstanceT]` (`instance_cls: type[InstanceT]`,
`_build(...) -> InstanceT`), so the concrete return type is preserved rather
than erased; the registry itself is typed `tuple[DomainSpawnSpec[Any], ...]`
since it mixes domains. (b) One `collection_attr` serves both `TemplateBundle`
and `ActivityBackends` (their field names already coincide), so no separate
`backend_attr` is needed. (c) The sketched `uses_anchor` flag proved
unnecessary — `_resolve_offsets` ignores the anchor when `offset_rewrites` is
empty, so Principle (no offsets) simply carries an empty tuple. `_build`
assembles a `dict[str, Any]` of kwargs and calls `spec.instance_cls(**kwargs)`;
`engagement_state` and `source_path_step_uid` go through the kwargs dict (they
live on the concrete instances, not on the `UserOwnedEntity` base).
`_validate_spawn_registry()` runs at module import and raises `ValueError` on
any rewrite/edge/`collection_attr` that does not resolve. mypy clean (incl. the
pre-commit `--follow-imports=silent` pass over the tests), ruff + SKUEL lint
clean, 75 unit + 21 integration tests pass.

**3. Document the back-reference authority.** Add one line to the spawn
docstring / lifecycle contract stating that `source_path_step_uid` is the
spawn-time PS, the `SPAWNED_FROM` edge is the universal (template-only)
back-reference, and — if templates are immutable-at-engagement (ACTIVE) —
that the two cannot diverge, making the field a pure read-optimization.

**4. Do NOT extract a shared authoring-fields mixin from the twin models.**
Despite ~74 duplicate fields, the ~16 transform fields genuinely differ in type
and cannot be shared; frozen-dataclass `kw_only` inheritance ordering is
brittle; and per-entity explicit fields are the core type-safety pattern
(Three-Tier Type System). A mixin would remove ~74 of ~140 declarations at the
cost of inheritance complexity that fights the grain — net negative unless these
authoring fields begin to churn.

## Consequences

**Positive**

- The spawn orchestrator's six `_build_*` functions, four spawn blocks, and
  pre-allocate loop collapse into one registry-driven path. New activity
  domains are a single `DomainSpawnSpec` entry.
- The 4-layer ordering, cross-edge specs, and offset/field rewrites live in one
  data structure rather than scattered module-level tables — the spawn invariant
  is readable in one place.
- Mirrors the precedent in [ADR-056](ADR-056-service-layer-label-split.md):
  per-domain hand-written variation collapsed into config the factory drives.
- Back-reference semantics become documented rather than folklore.

**Negative / follow-up**

- `TemplateBundle`, `ActivityBackends`, and `_TemplateLoader` keep their six
  explicit typed fields/params for DI clarity and type narrowing; the registry
  consolidates the *orchestration*, not the dependency surface. Some six-fold
  shape remains by design.
- `DomainSpawnSpec.instance_cls(**kwargs)` constructs via `**kwargs`, so a
  field-name typo in a rewrite table moves from a builder-local error to a
  registry-data error. Mitigation: a startup assertion that every spec's
  rewrite targets are valid fields of `instance_cls` (analogous to ADR-056's
  fail-fast factory validation).
- The twin model-field duplication is consciously **not** addressed; this ADR
  records the rejection so the question is closed rather than reopened.

## Alternatives Considered

1. **Single model with an `is_template` discriminator.** Rejected — incompatible
   state machines, ownership, and retention; destroys static typing of
   `*_template_uid` vs `*_uid`; forces conditional logic on every shared
   operation. This is the design the split deliberately avoids
   ([ADR-046](ADR-046-activity-domains-not-ku-subtypes.md) reasoning extends
   here).

2. **Shared authoring-fields mixin across template + instance.** Rejected — see
   Decision §4. Partial DRY win, real inheritance cost, fights the explicit-field
   type-safety pattern.

3. **Keep the spawn layer as-is.** Tenable — the code is clean, fully tested,
   carries no TODO debt, and the per-domain stubs are cheap. Rejected as the
   long-term shape only because the orchestrator fan-out (unlike the
   service/backend/route stubs) is genuine duplicated *logic*, and the registry
   removes it at near-zero type cost. Until implemented, the status quo is
   acceptable.

4. **Drop the denormalized `source_path_step_uid`, rely on the 2-hop edge.**
   Rejected — non-template scheduling paths create activities with no
   `SPAWNED_FROM` edge; the field is the only uniform back-reference. Keep it;
   document it (Decision §3).

## Related

- Builds on [ADR-046](ADR-046-activity-domains-not-ku-subtypes.md) — Activity
  Domains as first-class entity types is what makes a per-domain spawn spec
  coherent rather than a Ku-subtype hack.
- Follows the consolidation pattern of
  [ADR-056](ADR-056-service-layer-label-split.md) — collapse per-domain
  hand-written variation into config/registry the orchestration drives, with
  fail-fast validation.
- Operates on the machinery [ADR-059](ADR-059-askesis-engagement-alignment.md)
  consumes (`PsEngagementService`, `Engagement.spawned_instance_uids`); does not
  change the engagement contract Askesis reads.
- Implementation surface: `core/services/ps_engagement/_spawn_orchestrator.py`,
  `_validator.py` (`TemplateBundle`), `_template_loader.py`. Tests:
  `tests/unit/services/ps_engagement/test_spawn_builders.py`,
  `tests/integration/test_ps_engagement_lifecycle.py`.
