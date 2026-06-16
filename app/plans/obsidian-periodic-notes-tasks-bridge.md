# Plan: Obsidian Periodic Notes → SKUEL Tasks Bridge (PoC)

## Context

Mike writes daily/weekly/monthly/yearly notes in Obsidian (Periodic Notes plugin)
using the standard **obsidian-tasks-plugin** checkbox syntax
(`- [ ] Title 📅 2026-06-16 ⏳ 2026-06-15 #tag ⏫`). He wants to keep authoring in
Obsidian — an established, excellent writing surface — and have those notes flow into
SKUEL through the existing one-way vault → Neo4j ingestion pipeline ("the hips").

Agreed mental model (confirmed with Mike):

> **A periodic note = one `UserEntry` (the journal). The `- [ ]` checkbox lines inside
> it = `Task` entities extracted from that entry** via the existing
> `EXTRACT_ACTIVITIES` pipeline (ADR-069), each linked with
> `(Task)-[:EXTRACTED_FROM {extracted_at, source_line_hash}]->(UserEntry)`.

This honors SKUEL's values (leverage maintained software, build bridges, one path
forward): no new editor, MarkWhen dropped as a sync format (personal viz only), and we
reuse the extraction path rather than duplicating it.

## Delivery — 3 PRs + one-time vault setup, with a context reset between PRs

Per Mike's preference (fresh context per unit; plan→implement→assess). Each PR is
independently mergeable and independently verifiable. **Reset context after each PR
merges**; implement the next in a fresh thread with a tight "EXECUTE, no plan file"
brief.

```
Setup S0  (Obsidian vault config + templates — NOT an app PR, done once)
   │
PR-1  UserEntry ingestion foundation (body capture + deterministic UID/upsert)  ──┐
PR-2  Obsidian-Tasks extractor adapter                                            ──┤ independent of each other
   │                                                                               │
PR-3  Auto-trigger extraction on ingest (integration — full PoC works) ◄──────────┘ depends on PR-1 + PR-2
```

PR-1 and PR-2 are independent (either order, or parallel). PR-3 depends on both. The
end-to-end "drop a note → tasks in graph" proof lands with PR-3.

**Deferred to later follow-on PRs (not in this PoC):** period filter UI; check-box →
COMPLETED round-trip. Foundations for both ship inside PR-2 (period stamped into
`Task.tags`; dedup hash normalized across check/uncheck). Details at the end.

**Past-date behavior (decided):** No validator change. `TaskCreateRequest` rejects past
`due`/`scheduled` dates via `validate_future_date` (`validation_rules.py:73`). Mike does
not need past-dated tasks, so past-dated lines are simply not created; undated and
today/future lines create normally.

**Why no folder registration:** ingestion is type-driven by frontmatter `type:`, and
the watcher recurses all subfolders (`scripts/vault_watch.py` `rglob`;
`core/services/ingestion/config.py:collect_files` `glob("**/*.md")`). A new
`0vault/Daily/` folder needs only correct frontmatter.

---

## Setup S0 — Obsidian vault config + templates (one-time, no app code/PR)

Under `INGESTION_PATH = /home/mike/0bsidian/0vault`. Do this once; needed for PR-3
verification. Can be done anytime before PR-3.

- **Fix Periodic Notes** (`/home/mike/0bsidian/.obsidian/plugins/periodic-notes/data.json`):
  `daily.folder = "0vault/Daily/"` (currently `"templates"` — the bug that keeps daily
  notes out of the synced vault); set weekly/monthly/yearly folders inside `0vault`
  likewise; point `.template` at the consolidated templates; remove MarkWhen blocks +
  `mw_*_to_tasks_and_export()` Templater calls.
- **`t_daily.md` frontmatter** (literal; Templater fills date):
  ```markdown
  ---
  type: user_entry
  pipeline: extract_activities
  audience: private
  uid: "ue:daily:{{date:YYYY-MM-DD}}"
  title: "Daily — {{date:YYYY-MM-DD}}"
  tags: [periodic, daily]
  metadata:
    entry_kind: daily
    period_date: "{{date:YYYY-MM-DD}}"
  ---

  ## Tasks
  - [ ] 

  ## Notes
  ```
- `t_weekly.md` / `t_monthly.md` / `t_yearly.md` — same shape, `entry_kind:
  weekly|monthly|yearly`, deterministic uid (`ue:weekly:{{date:GGGG-[W]ww}}`,
  `ue:monthly:{{date:YYYY-MM}}`, `ue:yearly:{{date:YYYY}}`).

Contract is already valid app-side: `type: user_entry` (`detector.py:61`),
`pipeline: extract_activities` (accepted by `_parse_pipeline`), `audience: private`
(no shares, PRIVATE).

---

## PR-1 — UserEntry ingestion foundation (body capture + deterministic UID/upsert)

**Why first:** independently testable, and PR-3 needs a UserEntry that captures the
note body and re-syncs onto a stable uid.

**1a. Body → `UserEntry.content`.** The user_entry branch
(`unified_ingestion_service.py:432-448`) returns before `prepare_entity_data_async`, so
the body→content merge at `preparer.py:137` never runs and the note body (where `- [ ]`
lines live) is discarded. Pass `body` into `ingest_user_entry`; in
`build_user_entry_request` (`user_entry_ingestion.py:200-212`) set
`content = data.get("content") or body` (explicit `content:` wins; else body — periodic
notes have no `content:`, so body wins).

**1b. Deterministic UID + upsert.** Today `create_entry` always mints `ue_<random>`
(`user_entry_service.py:166`) and `backend.create` is pure `CREATE`
(`_crud_mixin.py:130`), so re-sync duplicates / violates the uid constraint.
- Add optional `uid: str | None` to `UserEntryCreateRequest`
  (`core/models/user_entry/user_entry_request.py`).
- `build_user_entry_request` reads `data.get("uid")` onto the request.
- `create_entry`: `uid = request.uid or UIDGenerator.generate_random_uid("ue")`.
- When `request.uid` is set, branch to an **upsert** (MERGE-on-uid) — add `upsert(entry)`
  on `UserEntryBackend` mirroring the bulk path's `MERGE (n {uid}) ON CREATE … ON MATCH …`
  (`bulk_upsert_backend.py:79`); replicate the OWNS-edge MERGE. Random-uid callers
  (`/submit`) keep `create`.

**Files:** `unified_ingestion_service.py`, `user_entry_ingestion.py`,
`user_entry_service.py`, `core/models/user_entry/user_entry_request.py`,
`UserEntryBackend` (adapters/persistence/neo4j).

**Verify (independent — no extraction needed):** ingest a `type: user_entry`,
`pipeline: none`, `uid: ue:test:1` markdown file with a real body; re-ingest an edited
version.
```cypher
MATCH (e:Entity {uid:'ue:test:1'})
RETURN e.uid, e.content IS NOT NULL AS has_content, count(e) AS n  // n=1 after re-sync, body present
```
**After merge: reset context.**

---

## PR-2 — Obsidian-Tasks extractor adapter

**Why independent:** testable at the extractor/service level (call `process()` on a
UserEntry whose `content` holds checkbox lines) without the ingest auto-trigger.

**New file `core/services/dsl/obsidian_tasks_adapter.py`** — stateless
`obsidian_task_line_to_parsed(line, *, entry_kind=None, ...) -> ParsedActivityLine | None`,
manufacturing `contexts=[EntityType.TASK]`:
- **Checkbox gate** — reuse `ActivityDSLParser.CHECKBOX_UNCHECKED/CHECKED`
  (`activity_dsl_parser.py:516-517`); `None` if neither. `is_checked` from CHECKED.
- `📅 date` → `when` (converter → `due_date`); `⏳ date` → new `scheduled_date` field.
- Priority `🔺/⏫`→1, `🔼`→2, none→3, `🔽`→4, `⏬`→5.
- `#tag` → new `extra_tags`; plus `period:{entry_kind}` when set (foundation for the
  deferred filter; lands in `Task.tags`).
- Description = line stripped of checkbox/emoji/dates/`#tags`, whitespace-collapsed
  (mirror `_extract_description`, `activity_dsl_parser.py:732`).
- **Store `raw_line` with checkbox normalized to `- [ ]`** (replace `[x]`/`[X]`) so the
  dedup hash is stable across check/uncheck (prevents future duplicate creation; the
  active flip-to-COMPLETED is deferred).

**`ParsedActivityLine`** (`activity_dsl_parser.py:76-162`) — add `scheduled_date: date |
None = None` and `extra_tags: list[str] = field(default_factory=list)`. Existing
`@context` lines default them empty → no behavior change.

**`activity_to_task_request`** (`activity_domain_converters.py:91-104`) — pass
`scheduled_date=activity.scheduled_date` and
`tags=dedup(activity.energy_states + activity.extra_tags)`.

**Hook in `parse_journal`** (`activity_dsl_parser.py:686-699`) — non-`@context` lines get
a second pass through the adapter; add `entry_kind: str | None = None` param.
`ActivityExtractorService.extract_and_create` (`activity_extractor.py:451`) reads
`(entry.metadata or {}).get("entry_kind")` and passes it down. Downstream
(`_create_task` → converter → `tasks_service.create_task`, `created_links`/
`EXTRACTED_FROM`/line-hash dedup) untouched.

**Files:** `core/services/dsl/obsidian_tasks_adapter.py` (new),
`activity_dsl_parser.py`, `activity_extractor.py`, `activity_domain_converters.py`.

**Verify (independent):** create a UserEntry directly with `content` = a few checkbox
lines + `metadata.entry_kind=daily`, call `processing_service.process(entry, force=True)`.
```cypher
MATCH (t:Task)-[r:EXTRACTED_FROM]->(e:UserEntry {uid:'<entry>'})
RETURN t.title, t.due_date, t.scheduled_date, t.priority, t.status, t.tags  // period:daily in tags
```
Plus unit tests on the adapter (line → ParsedActivityLine for each emoji). **After
merge: reset context.**

---

## PR-3 — Auto-trigger extraction on ingest (integration; full PoC works)

**Depends on PR-1 + PR-2.** Wires the entry-from-ingest to the extractor.
- Add `user_entry_processor: UserEntryProcessingService | None = None` to
  `UnifiedIngestionService.__init__`.
- In `services_bootstrap/compose.py` (~line 1166, after the processor is built) set
  `unified_ingestion.user_entry_processor = user_entry_processor` (order already works;
  no circular import).
- In `ingest_user_entry`, after a successful `create_entry`, if a processor is present
  and `entry.pipeline == Pipeline.EXTRACT_ACTIVITIES`, call
  `await processor.process(entry, force=True)`. `force=True` is required so edits
  re-extract (the completed-run guard, `user_entry_processing_service.py:122`, would
  else no-op); line-hash dedup remains the real idempotency guard.
- **Failure isolation:** an extraction error must not fail persistence of the journal
  node — log + surface in the result dict; return node-create success. Re-sync retries.

**Files:** `unified_ingestion_service.py`, `user_entry_ingestion.py`,
`services_bootstrap/compose.py`.

**Verify (full PoC end-to-end; local Docker Neo4j; neo4j-cypher MCP; CI runs no pytest):**
1. With S0 done, drop `0vault/Daily/2026-06-16.md` from the template with a couple of
   `- [ ] … 📅 <today> ⏫ #work` lines (today/future dates).
2. `uv run python scripts/vault_watch.py` (one-shot) over `INGESTION_PATH`.
3. ```cypher
   MATCH (e:Entity {uid:'ue:daily:2026-06-16'})
   OPTIONAL MATCH (t:Task)-[r:EXTRACTED_FROM]->(e)
   RETURN e.entity_type, e.content IS NOT NULL AS has_content,
          count(DISTINCT t) AS tasks, count(r) AS edges  // 1 entry, N tasks, N edges
   ```
4. **Re-sync no-dup:** add `- [ ] new task`, re-ingest → original N unchanged, +1 new,
   same uid.
5. Cleanup: `MATCH (e:Entity {uid:'ue:daily:2026-06-16'})<-[:EXTRACTED_FROM]-(t) DETACH DELETE e,t`

---

## Deferred follow-on PRs (recorded so they aren't lost)

- **Period filter UI.** Filter by the `period:{kind}` tag stamped in PR-2 — NOT by
  `entry.metadata.entry_kind`, because metadata is JSON-stringified into one Neo4j string
  property (`neo4j_mapper.py:192`), so `WHERE e.metadata.entry_kind = …` is invalid
  Cypher. Add a `period` param to `filter_tasks` (`core/utils/entity_filters.py:83`), a
  `("period","all")` entry to `filter_params` (`adapters/inbound/tasks_ui.py:63`, in
  signature order), and a `FilterSelect` to `FILTER_CONFIGS["tasks"]`
  (`ui/activities/filter_bar.py:185`). Zero backend change.
- **Completion round-trip.** PR-2's checkbox-normalized `raw_line` already prevents
  duplicate creation on check. To flip the existing task to COMPLETED on re-sync, extend
  `_run_extract_activities` (`user_entry_processing_service.py:425-434`) to keep
  `hash → source_task_uid` from existing `EXTRACTED_FROM` edges and mark COMPLETED any
  pre-existing-hash line now `is_checked`.
- **Past-date relaxation.** Not needed per Mike; if ever wanted, an extraction-only
  `TaskCreateRequest` path without `validate_future_date`.
