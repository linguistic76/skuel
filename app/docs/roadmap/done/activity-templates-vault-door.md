---
title: "Activity Templates Get a Vault Door"
updated: 2026-09-06
status: done
registered: 2026-09-05
ruled: 2026-09-05
---

# Activity Templates Get a Vault Door

*Shipped 2026-09-06 in three PRs (#1283, #1284, PR-3). Graduated out of
[parked-features.md](../parked-features.md) 2026-09-05 when the shape was ruled; left the live
folder when PR-3 closed the last open half.*

The 2026-07-06 ruling said the 6 Activity Templates belong *somewhere of their own* and explicitly
declined to force a shape. On 2026-09-05 the shape was ruled: **the vault**. This file records the
evidence that decided it, the shape, and the arc that implements it.

## What decided it

Measured 2026-09-05 against the live AuraDB (`d2d160c4`) and the tree at `b72252059`:

- **Zero activity templates exist.** Not one, in any of the six types. The six `HAS_*_TEMPLATE`
  relationship types are not in the database at all — Neo4j answers an
  `UnknownRelationshipTypeWarning` for every one of them. There are 25 PathSteps, all authored.
- **The stack is complete.** ~6,800 lines: 6 models + 6 DTOs + 6 request schemas + 6 services +
  6 backends + 6 route files + `templates_ui.py` + panel/forms, plus the `ps_engagement` spawn
  orchestrator and its tests. Engagement has never had anything to spawn.
- **The only door contradicts the authoring model.** A template can be created exactly one way: a
  TEACHER-gated web form nested inside a PathStep
  (`/teaching/ps/{ps_uid}/templates/{domain}/new`, `adapters/inbound/templates_ui.py`), which
  creates then attaches. Templates have **no ingestion config** — `ENTITY_CONFIGS` registers Ku,
  PathStep, LearningPath, Exercise, Resource and all **6 Activity instances**, and its own comment
  names the six templates as deliberately not file-ingestible. `HAS_*_TEMPLATE` exists in
  `relationship_names.py` but has no `relationship_registry.py` entry, so the `_edge.md` door
  cannot author the attachment either.

That is the whole explanation for the zero. The 6 Activity **instances** went ingestion-first on
2026-03-28 — their CRUD UI was deleted, Obsidian became the authoring layer. The templates, built
later, were given precisely the surface that had just been removed. Everything Mike actually
authors is a vault file: 113 `_Ku.md`, 25 `_Ps.md`, 76 `_edge.md`, 14 `_exer.md`. Templates are the
one curriculum type with no file kind.

## The shape

**Templates are vault-authored, like every other curriculum type.** Their own file kind is the
"somewhere of their own"; SKUEL surfaces them read-only. The teacher CRUD forms go, per One Path
Forward — the same trade the Activity Domains made in March, which kept the service facades and
dropped the UI.

Two standing defects dissolve rather than needing separate fixes:

1. **Detach orphans a node permanently.** `template_detach` removes only the edge; the node
   survives with no listing, no search and no reachable page. The create-path error banner already
   concedes it — *"delete the orphan template via the JSON API."* Under a vault door the file is
   the home, so there is nothing to orphan.
2. **Reuse is modelled but unreachable.** `attach` is a `MERGE`, so one template could serve N
   PathSteps, but the UI only ever creates-and-attaches. Under a vault door, reuse is a second
   `_edge.md` line.

### Already solved, do not rebuild

`RelativeOffset` round-trips through `core/models/templates/offset_helpers.py`:
`jsonable_to_offset` already accepts a dict **or** a JSON string, and `to_dict` stores
`json.dumps(offset_to_jsonable(...))`. So YAML frontmatter `due_offset: {days: 7}` parses to
exactly the dict that helper takes. The authoring form needs no new vocabulary.

### The technical risk — measured false, and what was actually owed

The risk recorded here was that ingestion persists **raw property dicts** through
`_bulk_backend.upsert_with_relationships`, bypassing the DTO layer where offset serialization
lives, so a nested-map property would reach Neo4j as a map and be rejected.

**Reproduced on 2026-09-05 and it does not happen.** `prepare_batch_items` → `to_neo4j_node` →
`Neo4jGenericMapper._dict_to_node` already `json.dumps`es any mapping value, and
`jsonable_to_offset` accepts a JSON string — so `due_offset: {days: 7}` round-trips today with no
coercion at all:

```python
to_neo4j_node({"due_offset": {"days": 7}})   # {'due_offset': '{"days": 7}'}
jsonable_to_offset('{"days": 7}')            # RelativeOffset(days=7, hours=0, minutes=0)
```

What the ingest path *did* owe is the opposite of a coercion — a **gate**. Because the mapper
serializes any mapping, a mistyped `due_offset: {day: 7}` persists happily and the reader rebuilds
it as a **zero** offset: the template spawns an instance due today, and the write reports success.
An int, a list or an unparseable string lands as a silent `None`; `{"days": "seven"}` makes
`jsonable_to_offset` raise inside the reader.

PR-1 therefore ships, following the `created_at` precedent in the same validator: the preparer
canonicalizes every *authorable* offset to the three-key dict the DTO write path stores (so both
doors persist one shape) and leaves anything else **verbatim**, and `validate_entity_data` rejects
it with one actionable per-file message. There is still exactly one `json.dumps`, in the mapper.
`TEMPLATE_OFFSET_FIELDS` in `offset_helpers.py` is now the one list of offset field names — the
six DTOs read their own row from it rather than each keeping a private tuple.

## The arc

Three PRs, fresh context each, per the standard multi-PR arc workflow.

**PR-1 — the door. ✅ SHIPPED 2026-09-05.** Six `EntityIngestionConfig` entries
(`uid_prefix` `tt`/`gt`/`ht`/`et`/`ct`/`pt`, matching the generated prefixes the route files
already use), the six `type:` values registered in the detector, the offset gate described above,
and six `relationship_registry.py` entries for `HAS_*_TEMPLATE` with `yaml_field_path`, so PS
attachment is authorable — these edges already exist, so registering them is not a new coupling.
The `ENTITY_CONFIGS` comment that stated the opposite premise is corrected.

Two things PR-1 had to settle that the scope above did not name:

- **`status: active` by default.** `PsEngagementService` refuses to spawn from a non-ACTIVE
  template (`ps_engagement/_validator._check_template_statuses`), and ingestion applies no model
  defaults — a vault file omitting `status:` would persist no status at all, the DTO would read
  DRAFT, and every vault-authored template would silently never spawn. Stamped at the ingest door
  exactly as PathStep stamps ACTIVE, and an authored `status:` still wins.
- **The `event_template_uids` collision — Mike's HELD rename executed.** The name was already
  taken by `SCHEDULES_EVENT` → `:Event`, an *instance* channel; `generate_ingestion_relationship_config`
  keys on `yaml_field_path`, so registering `HAS_EVENT_TEMPLATE` under it would have silently
  dropped one of the two. Mike ruled the `event_template_uids` → `event_uids` rename on 2026-08-21
  and then **held** it pending "the template-vs-activity question" — the question this arc's
  2026-09-05 ruling settled, and settled in the direction that makes the rename *required* rather
  than merely tidy. Executed here at the scope that case file measured: the registry, one test,
  three authoring docs, a regenerated `GRAPH_CONTRACT.yaml`, and the one vault file using it
  (`0vault/Ps/Ps_dev/noticing-patterns_Ps.md`). See
  [context-retriever-write-only-fields.md](../context-retriever-write-only-fields.md).

**PR-2 — the authoring surface. ✅ SHIPPED 2026-09-06.** The `_tmpl.md` suffix, with the six
kinds separated by `type:` as planned. [ACTIVITY_TEMPLATE_AUTHORING.md](../../guides/ACTIVITY_TEMPLATE_AUTHORING.md)
is the new authoring reference — the six kinds, complete field references, the offset vocabulary,
structured lists, and what engagement does; `YAML_AUTHORING_GUIDE`'s API-centric TaskTemplate
section becomes a short vault-first section pointing at it. Six worked examples live in
`0vault/Tmpl/`, attached to `ps.mindfulness-101.step-1`.

Verified by driving the real doors against the live graph, not by reading: both directory doors
(`./dev vault-sync --vault content` and the admin `POST /api/vault/sync/content` are the same
`VaultReconciler.sync` call), the single-file door (`ingest_file`), `--preview`, edge retraction
(dropping a uid from the PS took the edge and left the node), and deletion propagation (deleting
a template file deleted its node, `entities_deleted: 1`). All six read back through the service
with their offsets, enums, milestones, options and expressions intact.

Five things PR-2 found that the scope did not name:

- **`type: TaskTemplate` was rejected.** The content vault spells every other kind in PascalCase
  (`type: PathStep`, `type: Ku`, `type: Habit`) and that resolves because lowercasing is enough —
  but `EntityType.from_string` inserts no underscore, so the six canonical values, the only
  ingestible ones with an internal underscore, were the one family it missed. `type: Task Template`
  worked; `type: TaskTemplate` did not. The six spellings join `pathstep`/`learningpath` in the
  detector's `TYPE_MAPPING`.
- **The TaskTemplate field table documented a `priority` field that has never existed** anywhere in
  the stack, and two worked examples POSTed it. `tests/unit/docs/test_activity_template_docs.py`
  now derives every documented table from the live dataclasses — names both ways, plus the
  `type:`/prefix/attachment rows against three separate authorities and any spelled-out enum
  vocabulary against `ENUM_FIELD_TYPES`. That last check caught the doc calling `event_type`
  free-text when the ingest door enum-validates it.
- **The JSON API the guide pointed at as the second door named routes that do not exist** —
  `POST /api/task-templates/` and `POST /api/ps/{ps_uid}/task-templates/{uid}/attach`. The
  factory builds `/api/{domain_name}` and every template config names itself
  `pathstep-{domain}-templates`. Same class as `priority`, so it gets the same treatment: the
  docs test pins the documented pattern against the six configs, derived from the six
  EntityTypes. The `POST /api/ps/{ps_uid}/publish` route in the same section is real.
- **A structured-list item without its nested `uid:` corrupts silently** — registered as its own
  case file, [structured-list-items-need-a-nested-uid.md](../structured-list-items-need-a-nested-uid.md).
  Not template-specific (Goal and Choice have carried it since they became ingestible), so the fix
  belongs at the shared gate, not on six template configs.
- **A frontmatter edge whose target does not exist yet is written nowhere and reported nowhere** —
  registered as [frontmatter-edge-target-missing-is-silent.md](../frontmatter-edge-target-missing-is-silent.md).
  Hit in the ordinary course: one template failed validation, so the PathStep in the same batch
  silently got five of six edges and the sync reported success.

**PR-3 — One Path Forward. ✅ SHIPPED 2026-09-06.** The create/edit/detach handlers and the form
builders are gone: `templates_ui.py` 508 → 111 lines (the panel fragment route and nothing else),
`ui/teaching/templates_forms.py` (586), `ui/teaching/_template_widgets.py` (123) and
`adapters/inbound/_template_form_parsing.py` (88 — the dotted-offset form parser, whose only
caller was the create/edit submit) deleted, and `parse_template_form_body` dropped from
`audit_route_security.py`'s `FORM_HELPERS`. The services, backends and JSON CRUD stay, matching
the March precedent.

Two things PR-3 had to settle that the scope above did not name:

- **The panel was never surfaced.** "Keep the panel as a read-only view on the PS detail page" was
  a *build*, not a keep: `render_templates_panel_placeholder` had **zero callers**, so the
  TEACHER-gated fragment route existed with nothing loading it, and
  `render_ps_detail_content`'s `user_role` parameter — documented as "gates teacher-only
  controls" — gated nothing at all. Both halves are now live: TEACHER+ viewers of
  `/explore/ps/{uid}` get the panel, everyone else gets no node. The panel itself lost its
  "+ Add" / "Edit" / "Detach" controls and gained the line that names the real door — an
  `_tmpl.md` file plus the step's `{domain}_template_uids:` frontmatter.
- **`ActivityTemplateOperations` was the deleted handlers' port.** It declared six members
  (`create`/`get`/`update`/`attach_to_pathstep`/`detach_from_pathstep`/`list_for_pathstep`) and
  had exactly one consumer, `templates_ui.py`, which now calls one of them. Narrowed to
  `list_for_pathstep` and no longer generic — the type parameter existed only for `create`'s
  contravariant argument position, and every remaining member returns property dicts. The JSON
  CRUD reaches the concrete services, so it is unaffected.

## Constraints (from the 2026-07-06 ruling, still binding)

- **A separate arc.** Not folded into search/nous work. Templates stay out of
  `SearchRouter._SEARCHABLE_DOMAINS` and out of the `/search` Types facet in this arc.
- **Entities stay orthogonal.** No coupling edges invented to make templates "belong".
- **The adjacent question stays unruled:** whether the Types facet — or templates — should ever
  serve content-discovery-by-domain is a distinct, open design question. Do not conflate it.
