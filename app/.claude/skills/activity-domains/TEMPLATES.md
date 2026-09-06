# Activity Templates — Architecture Reference

> Template entities are PS-owned curriculum content. They are not user entities.
> When a student engages a PathStep, the spawn layer converts each template into a
> personalized, user-owned instance. Template and instance are distinct frozen
> dataclasses with incompatible state machines, incompatible ownership, and
> statically typed field pairs that cannot be merged.

This file is the architecture reference. **To author a template**, see
`/docs/guides/ACTIVITY_TEMPLATE_AUTHORING.md` — templates are vault files
(`<slug>_tmpl.md`, told apart by `type:`), attached from a PathStep's
`{domain}_template_uids:` frontmatter.

---

## 1. Two-Entity Split (why templates and instances are separate models)

Each of the 6 Activity Domains has a **twin pair**:

| Aspect | Template (e.g. `TaskTemplate`) | Instance (e.g. `Task`) |
|--------|-------------------------------|------------------------|
| Base class | `Entity` | `UserOwnedEntity` |
| `user_uid` | `None` — PS-owned curriculum | `str` — the student |
| `ContentOrigin` | `CURRICULUM` | `USER_CREATED` |
| Date fields | `RelativeOffset \| None` | `date \| datetime \| None` (absolute) |
| Cross-ref fields | `*_template_uid: str \| None` | `*_uid: str \| None` (instance UID) |
| Status lifecycle | `DRAFT → ACTIVE → ARCHIVED` | domain-specific (SCHEDULED/ACTIVE/COMPLETED/etc.) |
| `engagement_state` | not present | `EngagementState \| None` |
| Instance runtime state | not present | `current_streak`, `progress_percentage`, `completion_date`, etc. |

**Why not a single model with `is_template: bool`?** The two state machines are
incompatible (ADR-061 §Alternatives). Template `ACTIVE` means "this template is
live and may be engaged"; instance `ACTIVE` means "the student is working on
this". Collapsing them forces conditional logic on every operation that differs
between the two and destroys the static typing of `*_template_uid` vs `*_uid`.

**Why not a shared authoring-fields mixin?** ~74 of ~140 non-base fields are
identical across each pair, but the ~16 transform pairs genuinely differ in type
(`due_offset: RelativeOffset` vs `due_date: date`). Frozen-dataclass `kw_only`
inheritance ordering is brittle; explicit per-entity fields are the core
type-safety pattern (ADR-061 §Decision 4).

**Model locations:**

```
core/models/templates/task_template.py
core/models/templates/goal_template.py
core/models/templates/habit_template.py
core/models/templates/event_template.py
core/models/templates/choice_template.py
core/models/templates/principle_template.py
```

---

## 2. Template Lifecycle: DRAFT → ACTIVE → ARCHIVED

All six template types use `Entity.status: EntityStatus` with the same three
valid values, enforced by the status validator in `entity_enums.py`:

```
DRAFT    — authored but not yet available to students
ACTIVE   — live; students can engage this template via its PathStep
ARCHIVED — retired; no new engagements, existing spawned instances unaffected
```

The model default is `DRAFT`, and the JSON API / teaching UI leave it there —
those templates must be explicitly promoted to `ACTIVE` before a PathStep
engagement will include them in the spawn. **The vault door stamps `ACTIVE`
instead** (`ENTITY_CONFIGS` default): ingestion applies no model defaults, so an
unstamped node would carry no status, read `DRAFT`, and make every
vault-authored template silently inert. An authored `status:` still wins.

**Immutability at engagement:** Templates are immutable once `ACTIVE`. The
`(instance)-[:SPAWNED_FROM]->(template)` edge freezes the template at spawn
time. If the template fields were mutable post-engagement, the edge and the
denormalized `source_path_step_uid` on the instance could diverge. Do not
mutate a template's authoring fields while it is `ACTIVE`.

**Status is enforced by `_PsValidator`:** both `publish_pathstep` (T1) and
`engage_pathstep` (T2 defensive re-validate) run `_PsValidator.validate()`
before proceeding. The `not_active` check runs first and short-circuits the
rest — a non-ACTIVE template produces a `Violation(violation="not_active")`
and blocks the operation immediately. Promote every template to `ACTIVE`
before publishing the PathStep.

---

## 3. TemplateBundle — PathStep's Template Aggregator

`TemplateBundle` is a frozen dataclass that holds all templates attached to a
PathStep, indexed by domain. It is the hand-off from the template-loading step
to both validation and the spawn orchestrator.

```python
# core/services/ps_engagement/_template_bundle.py
@dataclass(frozen=True)
class TemplateBundle:
    ps_uid: str
    tasks:      tuple[TaskTemplate, ...]
    goals:      tuple[GoalTemplate, ...]
    habits:     tuple[HabitTemplate, ...]
    events:     tuple[EventTemplate, ...]
    choices:    tuple[ChoiceTemplate, ...]
    principles: tuple[PrincipleTemplate, ...]
```

**How PathStep assembles it** — `_TemplateLoader.load(ps_uid)`:

1. Walks the six `HAS_*_TEMPLATE` edges from the PathStep node:
   `HAS_TASK_TEMPLATE`, `HAS_GOAL_TEMPLATE`, `HAS_HABIT_TEMPLATE`,
   `HAS_EVENT_TEMPLATE`, `HAS_CHOICE_TEMPLATE`, `HAS_PRINCIPLE_TEMPLATE`
2. Queries each domain backend for the UIDs linked by those edges.
3. Hydrates typed template instances from the returned properties.
4. Returns one frozen `TemplateBundle` consumed by both the validator and the
   spawn orchestrator — no double query.

**Helper methods on `TemplateBundle`:**

- `all_uids()` — flat list of every template UID across all six domains
- `type_by_uid(uid)` — returns the `EntityType` for a given template UID

A PathStep with no templates attached returns a bundle with all six tuples
empty — the spawn produces no instances.

---

## 4. DomainSpawnSpec Registry — the Orchestration Contract

`DomainSpawnSpec` is a generic frozen dataclass that centralises everything
the spawn orchestrator needs for one domain. The `SPAWN_REGISTRY` tuple holds
one entry per domain.

```python
# core/services/ps_engagement/_spawn_orchestrator.py
@dataclass(frozen=True)
class DomainSpawnSpec(Generic[InstanceT]):
    instance_cls:    type[InstanceT]                           # Task, Goal, Habit, …
    template_cls:    type[Entity]                              # TaskTemplate, GoalTemplate, …
    layer:           int                                       # 1–4 — spawn order
    collection_attr: str                                       # "tasks", "goals", … (TemplateBundle + ActivityBackends)
    uid_prefix:      str                                       # UIDGenerator prefix
    offset_rewrites: tuple[tuple[str, str, OffsetKind], ...] = ()
    field_rewrites:  dict[str, str]                           = field(default_factory=dict)
    cross_edges:     tuple[tuple[str, RelationshipName], ...] = ()
```

### 4a. 4-Layer Dependency Order

Templates within a single PathStep engagement can reference each other.
The `layer` field encodes which domains must be spawned first:

```
Layer 1: Choice, Habit, Principle   — no incoming cross-references within a spawn
Layer 2: Goal                        — may reference Choice (INSPIRED_BY_CHOICE)
Layer 3: Event                       — may reference Habit (REINFORCES_HABIT) and Goal (CELEBRATES_GOAL)
Layer 4: Task                        — may reference Habit (REINFORCES_HABIT), Goal (fulfills_goal_uid), Event (scheduled_event_uid)
```

The orchestrator sorts `SPAWN_REGISTRY` by `layer` before building instances.
UIDs for all layers are pre-allocated before any node is persisted, so a
Layer 4 spec can safely reference a Layer 1 instance UID in `field_rewrites`
or `cross_edges` without any I/O ordering dependency.

### 4b. Three Field Transform Categories

**`offset_rewrites`** — convert a `RelativeOffset` template field to an absolute
date/datetime on the instance, resolved against the engagement anchor:

```python
# (source_field, dest_field, kind)
("due_offset", "due_date", "date")          # RelativeOffset → date
("event_offset", "event_date", "date")      # RelativeOffset → date
("decision_deadline_offset", "decision_deadline", "datetime")  # RelativeOffset → datetime
```

Principle has no offsets and carries an empty tuple. `_resolve_offsets()` is a
no-op when the tuple is empty.

**`field_rewrites`** — translate a `*_template_uid` property to the
corresponding `*_uid` property on the instance, remapping through the
pre-allocated `template_to_instance` UID map:

```python
# {template_field: instance_field}
{"fulfills_goal_template_uid": "fulfills_goal_uid"}
{"parent_template_uid": "parent_uid"}
{"scheduled_event_template_uid": "scheduled_event_uid"}
```

The template UID is looked up in `template_to_instance`; the result (the
spawned instance UID) is written to the instance property.

**`cross_edges`** — write a graph edge between spawned instances; the template
field holding the cross-reference is NOT written as an instance property:

```python
# (template_field_with_template_uid, RelationshipName)
("inspired_by_choice_template_uid", RelationshipName.INSPIRED_BY_CHOICE)
("reinforces_habit_template_uid",   RelationshipName.REINFORCES_HABIT)
("milestone_celebration_for_goal_template_uid", RelationshipName.CELEBRATES_GOAL)
```

The relationship is the canonical representation; there is no scalar property
counterpart on the instance for these.

### 4c. SPAWN_REGISTRY entries at a glance

| Spec | Layer | offset_rewrites | field_rewrites | cross_edges |
|------|-------|----------------|----------------|-------------|
| `CHOICE_SPEC` | 1 | `decision_deadline_offset → decision_deadline (datetime)` | — | — |
| `HABIT_SPEC` | 1 | `recurrence_end_offset → recurrence_end_date (date)` | — | — |
| `PRINCIPLE_SPEC` | 1 | — | — | — |
| `GOAL_SPEC` | 2 | `start_offset → start_date`, `target_offset → target_date` | `fulfills_goal_template_uid`, `selected_choice_option_template_uid` | `inspired_by_choice_template_uid → INSPIRED_BY_CHOICE` |
| `EVENT_SPEC` | 3 | `event_offset → event_date`, `recurrence_end_offset → recurrence_end_date` | — | `milestone_celebration_for_goal_template_uid → CELEBRATES_GOAL`, `reinforces_habit_template_uid → REINFORCES_HABIT` |
| `TASK_SPEC` | 4 | `due_offset → due_date`, `scheduled_offset → scheduled_date`, `recurrence_end_offset → recurrence_end_date` | `fulfills_goal_template_uid`, `scheduled_event_template_uid`, `parent_template_uid` | `reinforces_habit_template_uid → REINFORCES_HABIT` |

### 4d. Registry Validation at Import

`_validate_spawn_registry(SPAWN_REGISTRY)` runs at module import and raises
`ValueError` if any of the following fail:

- `offset_rewrites` source/dest field names don't exist on the template/instance class
- `field_rewrites` key/value field names don't exist on the template/instance class
- `cross_edges` source field doesn't exist, or edge type isn't a `RelationshipName`
- `collection_attr` isn't a field on both `TemplateBundle` and `ActivityBackends`
- `template_cls` / `instance_cls` pair doesn't match `EntityType.instance_type()` — catches mis-wired entries where the wrong instance class is paired with a template

A typo or mis-wiring is a startup crash, not a silent runtime failure (ADR-056
fail-fast pattern).

---

## 5. Spawn Orchestration — Three Phases

The full spawn path (`_SpawnOrchestrator.spawn(student_uid, ps_uid, bundle,
engagement_anchor)`):

**Phase 1 — Pre-allocate UIDs** (all domains, before any DB write):

```python
for spec in SPAWN_REGISTRY:
    for tmpl in getattr(bundle, spec.collection_attr):
        template_to_instance[tmpl.uid] = UIDGenerator.generate_uid(spec.uid_prefix, tmpl.title)
```

All instance UIDs exist in the map before Phase 2 begins. This allows Layer 4
specs to embed Layer 1 UIDs in `field_rewrites` and `cross_edges` without
waiting for those nodes to be persisted.

**Phase 2 — Build + persist in layer order:**

For each spec (sorted by `layer`), for each template in the bundle:

1. `_build(spec, template, student_uid, ps_uid, anchor, template_to_instance)`
   — pure function, no I/O. Copies authoring fields, applies all three
   transform categories, injects managed fields:
   ```
   uid                    = template_to_instance[template.uid]
   user_uid               = student_uid
   engagement_state       = EngagementState.ENGAGED
   source_path_step_uid   = ps_uid
   entity_type            = spec.instance_cls.entity_type  (class-level constant)
   ```
2. `_compute_cross_edges(template, spec.cross_edges, template_to_instance)`
   — resolves edge targets using the pre-allocated UID map.
3. `backend.create_with_spawned_from(instance, template_uid)` — atomic write:
   creates the node and the `(instance)-[:SPAWNED_FROM]->(template)` edge in
   one transaction.
4. Writes cross-edges via `backend.create_relationship(from_uid, to_uid, edge)`.

**Phase 3 — Rollback on partial failure:**

If any create fails, the orchestrator deletes already-persisted nodes in reverse
order (`cascade=True`). Rollback failures are logged but do not mask the
original error.

---

## 6. Instance Engagement State

After spawn, instances carry `engagement_state: EngagementState | None` on every Activity model:

```
None                      — standalone instance; not from template spawn
EngagementState.ENGAGED   — freshly spawned; student is working through the curriculum content
EngagementState.OWNED     — student has personalised the instance; template relationship is broken
```

The `engaged → owned` transition is the learning loop closure signal (ADR-059).
`source_path_step_uid` is always the spawn-time PS UID regardless of engagement
state. The `SPAWNED_FROM` edge is the graph-native back-reference (use it to
traverse to the template; don't use it as an existence check — the field is
faster and works for non-template scheduling paths too).

---

## 7. Adding a 7th Activity Domain

The registry is the single change point. Steps:

1. Define `XTemplate` and `X` model pair in `core/models/templates/` and
   `core/models/x/`.
2. Add `EntityType.X_TEMPLATE` and `EntityType.X` to `entity_enums.py` with
   valid status sets.
3. Add `X_SPEC = DomainSpawnSpec(...)` and append it to `SPAWN_REGISTRY`.
   Set `layer` based on what the new domain references:
   - References nothing → Layer 1.
   - References Layer-N entities → Layer N+1.
4. Add `x: tuple[XTemplate, ...]` to `TemplateBundle` and `ActivityBackends`.
5. Wire `HAS_X_TEMPLATE` edge in `_TemplateLoader.rel_to_backend_and_class`.
6. Add a backend, service facade, and routes following the Activity Domain
   patterns in `FACADE_PATTERN.md` and `PATTERNS.md`.

`_validate_spawn_registry()` will catch field-name typos at server startup.

---

**See:**
- `core/services/ps_engagement/_spawn_orchestrator.py` — `DomainSpawnSpec`, `SPAWN_REGISTRY`, `_SpawnOrchestrator`
- `core/services/ps_engagement/_template_bundle.py` — `TemplateBundle`, `TemplateTypeName`
- `core/services/ps_engagement/_template_loader.py` — `_TemplateLoader`
- `docs/decisions/ADR-061-spawn-layer-consolidation.md` — rationale for the two-entity split and registry design
- `docs/decisions/ADR-059-askesis-engagement-alignment.md` — how Askesis consumes engagement events
- [PATTERNS.md § Curriculum-Spawned Activity](PATTERNS.md) — `engagement_state` and `source_path_step_uid` from the instance side
