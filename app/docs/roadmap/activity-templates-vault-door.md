---
title: "Activity Templates Get a Vault Door"
updated: 2026-09-06
status: "shape ruled, arc unscheduled"
registered: 2026-09-05
ruled: 2026-09-05
trigger: "Mike schedules the arc — the shape is settled, the build is not"
check: "`git grep -n 'TASK_TEMPLATE' -- core/services/ingestion/config.py` → empty (no vault door yet)"
---

# Activity Templates Get a Vault Door

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/`
when nothing in it remains open. Graduated out of [parked-features.md](parked-features.md)
2026-09-05 when the shape was ruled.*

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

### The one real technical risk

Ingestion persists **raw property dicts** through `_bulk_backend.upsert_with_relationships` — it
does not go through the DTO layer, which is where offset serialization lives. A nested-map property
reaches Neo4j as a map and is rejected. The ingest path therefore needs a per-type coercion step
that runs the existing helpers over the `*_OFFSET_FIELDS` before upsert. Reuse
`offset_helpers`; do not introduce a second serialization.

## The arc

Three PRs, fresh context each, per the standard multi-PR arc workflow.

**PR-1 — the door.** Six `EntityIngestionConfig` entries (`uid_prefix` `tt`/`gt`/`ht`/`et`/`ct`/`pt`,
matching the generated prefixes the route files already use). The offset coercion described above.
Six `relationship_registry.py` entries for `HAS_*_TEMPLATE` with `yaml_field_path`, so PS
attachment is authorable — these edges already exist, so registering them is not a new coupling.
Correct the `ENTITY_CONFIGS` comment that states the opposite premise.

**PR-2 — the authoring surface.** A `_tmpl.md` filename suffix following the `_Ku`/`_Ps`/`_exer`/
`_edge` convention, with the six kinds separated by an explicit `type:` (the detector already keys
off `type:`; six suffixes would buy nothing). Authoring documentation and one worked example per
domain in the content vault. Verify both ingest doors, `--preview`, and deletion reconciliation.

**PR-3 — One Path Forward.** Delete the create/edit/detach handlers in `templates_ui.py` and the
form builders (`ui/teaching/templates_forms.py`, `ui/teaching/_template_widgets.py`). Keep
`ui/teaching/templates_panel.py` as a **read-only** view on the PS detail page — that is the
"surfaced" half of the ruling. Keep the services, backends and JSON API, matching the March
precedent.

## Constraints (from the 2026-07-06 ruling, still binding)

- **A separate arc.** Not folded into search/nous work. Templates stay out of
  `SearchRouter._SEARCHABLE_DOMAINS` and out of the `/search` Types facet in this arc.
- **Entities stay orthogonal.** No coupling edges invented to make templates "belong".
- **The adjacent question stays unruled:** whether the Types facet — or templates — should ever
  serve content-discovery-by-domain is a distinct, open design question. Do not conflate it.
