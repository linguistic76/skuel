# Vault YAML Audit — Phase 1 Findings (2026-06-12)

Read-only audit of `/home/mike/0bsidian/0vault/` (240 files: 162 `.md` + 78 `.yaml`)
through SKUEL's real ingestion validators (`validate_file`, `validate_edge_data`) plus a
static frontmatter sweep and a live dry-run (`ingest_directory(dry_run=True,
validate_targets=True)` — no writes to Neo4j or the vault).

Machine-readable detail: `/tmp/vault_audit_report.json` (per-file issues).
Audit script (re-runnable): `/tmp/vault_audit.py`.

## Headline numbers

| Metric | Value |
|---|---|
| Files ingesting cleanly | 224 (190 entities + 34 single edges) |
| Files that FAIL ingestion (BLOCKING) | 16 |
| Dry-run vs live graph | 0 creates / 190 updates — graph has seen everything that validates |
| Duplicate UIDs (two files, same UID) | 69 pairs — all `Ku/*.md` vs `Ku/ku_older_vault/*.yaml` |
| Silently-dropped relationship data (DEGRADED) | 14 PathStep files (`connections.requires` unmapped) |
| Dangling refs in graph today | `lp.mindfulness-101`, `lp.self-reflection-101`, `principle.observation-before-action` (their source files are among the 16 blocked) |

**Non-findings (canonical as-is, no change proposed):** colon UIDs (`ku:yoga:asanas`) are
the documented canonical and normalize to dots at ingest; CamelCase `type:` values
(`Ku`, `PathStep`, `LearningPath`, `Edge`) match the ingestion guide's own examples.
All 240 files that declare a type use these consistently.

## A. BLOCKING (16 files fail ingestion)

| File | Reason | Fix class |
|---|---|---|
| `Lp/lp_mindfulness-101.md` | post-prepare validation: missing `name` — **code bug, see Contract Gap 1** | code (or vault workaround) |
| `Lp/lp_self-reflection-101.md` | same | same |
| `Prin/principle_observation-before-action.md` | same | same |
| `Prin/principle_precision-over-speed.md` | same | same |
| `Choice/choice_name-it-precisely.md` | `user_uid: system` non-canonical (must be `user_system`) | mechanical |
| `Choice/choice_observe-or-fix.yaml.md` | pure YAML saved as `.md` without `---` markers → parsed as bodyless markdown, no frontmatter; also carries `user_uid: system` | mechanical (rename to `.yaml` + uid fix) |
| `Ku/ku_presence.md` | frontmatter YAML syntax error — unquoted `description` contains `: ` (line 19) | mechanical (block scalar) |
| `Ku/ku_self.md` | same (line 19) | mechanical |
| `Ku/ku_older_vault/{1st,2nd,3rd}_ku.md` | scratch/template files ("This content becomes the content field…"), no `type`, `uid: 1st` | semantic (delete with directory) |
| `edges/edge_consciousness-web.md` | legacy **multi-edge bundle** (`edges:` list), no top-level `type` | semantic (see D) |
| `edges/edge_mindfulness-101-curriculum.md` | bundle with `type: Edge` but no `from/to/relationship` | semantic |
| `edges/edge_self-reflection-101-curriculum.md` | bundle, no `type` | semantic |
| `edges/edge_self-awareness-self-management-curriculum.md` | bundle, no `type` | semantic |
| `edges/edge_mindfulness-to-self-reflection.md` | bundle, no `type` | semantic |

## B. DEGRADED (ingests, loses data/meaning)

1. **`connections.requires` is inert on 14 PathStep files.** PS's mapped fields are
   `prerequisite_step_uids` / `prerequisite_knowledge_uids` / `connections.enables` /
   `connections.related` / `uses_kus` / …; `connections.requires` has no mapping, so the
   prerequisite edges are silently never created. Targets are all `ps:*` UIDs → 1:1
   mechanical rename to `prerequisite_step_uids`. (Files: all 14 non-step `Ps/*.md` that
   have a `connections:` block.)
2. **69 duplicate UIDs** — every `Ku/ku_older_vault/*.yaml` except 9 declares the same UID
   as a newer `Ku/*.md` file. Both ingest every sync; same node written twice per run,
   whichever parses last wins. The 9 WITHOUT twins are **live content referenced by
   `edges/` singles** (must be kept): `ku.yoga.niyamas`, `ku.yoga.tapas`, `ku.yoga.saucha`,
   `ku.yoga.vairagya`, `ku.discipline.investment`, `ku.mind.eq`, `ku.mind.mistakes`,
   `ku.sel.emotions`, `ku.values.six-choices`.
3. **Dangling graph refs** until the LP/Principle blockage clears: PS step files reference
   the two LPs; habits reference `principle.observation-before-action`. Dry-run
   `validate_targets` flags all three.

## C. COSMETIC (works, non-canonical / inert)

- **Dead-weight fields** (stored as inert node properties, read by nothing — not entity
  config, not relationship-mapped, not embedded, not on the domain model):
  - `Ku`: `heading` ×96 (generation residue like `"#### Asanas"`)
  - `edge files`: `version` ×35 (entities strip `version`; edges just ignore it)
  - `Habit`: `category`, `difficulty` ×2 · `LearningPath`: `difficulty`, `goal`, `prerequisites` ×2
  - `Principle`: `category`, `source`, `why_important`, `decision_criteria`, `related_principle_uids` ×2
  - `PathStep` (the 4 `*_step-*` files only): `completed`, `difficulty`, `notes`, `priority` — personal
    state inside SHARED curriculum files
- **Recommended fields missing** on ~15 files (mostly `tags`; one missing `description`).
- **Naming strays** (UIDs are explicit so nothing breaks; zero wikilinks in vault, renames safe):
  `Ku/yaml - ku_writing-practice.md`, `Ku/yoga yaml.md`, six unprefixed Ku files
  (`active-listening.md`, `asanas.md`, `atomic-habits.md`, `attention.md`,
  `attention_buzzing.md`, `here-now.md`), root-level `caffeine_exacerbates_buzzing.md`
  (a VALID single edge, just outside `edges/` and missing the `edge_` prefix).

## D. The 5 legacy edge bundles (75 inner edges)

Format: `edges:` list with per-edge `type:` (contract wants one edge per file with
`from/to/relationship`). Three staleness axes:
- **UID dialect:** `l:mindfulness:breath-awareness-basics` — the retired lesson prefix;
  current PS UIDs are `ps:mindfulness:breath-awareness-basics` (mapping `l:` → `ps.` is 1:1).
- **Relationship names:** valid today — `ENABLES` 13, `RELATED_TO` 15, `USES_KU` 13,
  `TRAINS_KU` 5, `PREREQUISITE_FOR` 4, `BLOCKS` 3, `COMPLEMENTARY_TO` 2; **retired** —
  `HAS_LESSON` 8, `REQUIRES` 6, `CONTAINS_STEP` 4, `NEXT_STEP` 2.
- **Redundancy:** the `USES_KU` wiring is already declared in PS frontmatter (`uses_kus`
  in 14 PS files); LP→step wiring already in `connections.contains_steps` on the LPs.
  The Ku↔Ku web (consciousness-web, mindfulness↔self-reflection laterals) is NOT
  expressed anywhere else.

## E. Contract gaps (code-side — separate decisions, NOT part of the vault rewrite)

1. **LP/Principle ingestion is broken by design** (`required_fields` vs the `name`→`title`
   rename). `ENTITY_CONFIGS` requires `name` for `LEARNING_PATH`/`PRINCIPLE`; the preparer
   (`preparer.py:187`) pops `name` into `title`; post-prepare `validate_entity_data` then
   demands `name` → unsatisfiable unless a file redundantly carries BOTH `name` and `title`.
   No LP or Principle file has ever ingested (the dangling refs in B.3 prove it on the live
   graph). Fix: post-prepare required set should expect `title` (and `statement` for
   Principle), or skip the name/title pair the way pre-validation already does.
2. **Broken frontmatter is silently downgraded to empty** (`parser.py:122-132`): a YAML
   syntax error in `.md` frontmatter logs a warning and proceeds with `{}` — the user-facing
   error then becomes the misleading "has no 'type' field". Surfacing the syntax error
   would have pointed straight at `ku_presence.md:19`.
3. **`validator.validate_file` doesn't recognize edges** — the batch path checks
   `is_edge_type` before entity detection; the single-file validator (used by
   `/api/ingest` validation endpoints) does not, so a perfectly valid edge YAML
   dry-runs as "Cannot determine entity type".
4. **Markdown body kept only for PathStep/UserEntry** (`preparer.py:137`): any Ku/Activity/
   Exercise/LP `.md` body is silently dropped. Harmless for this corpus (Ku content lives in
   frontmatter `description`) but a trap worth a guard or a docs note.
5. **`related_principle_uids`** is carried by every Principle file and read by nothing —
   exactly the "field ingestion should perhaps read" case (Principle↔Principle lateral).
6. (Observation) Two UID dialects coexist by design: CRUD generates `ku_{slug}_{random}`,
   ingestion enforces `ku.{namespace}.{slug}`. Both live in the graph; not a vault problem.

## Phase 2 — Proposed fix plan (NOT executed; awaiting approval)

### Mechanical (safe batch rewrite, frontmatter-only, bodies byte-for-byte)
1. `user_uid: system` → `user_uid: user_system` (2 Choice files).
2. Rename `Choice/choice_observe-or-fix.yaml.md` → `choice_observe-or-fix.yaml`.
3. `ku_presence.md` + `ku_self.md`: convert `description:` to a block scalar (`|`).
4. 14 PS files: `connections.requires` → top-level `prerequisite_step_uids` (drop empty lists).
5. Move root `caffeine_exacerbates_buzzing.md` → `edges/edge_caffeine-exacerbates-buzzing.md`.
6. Naming normalization (optional): `ku_`-prefix the six unprefixed Ku files; fix
   `yaml - ku_writing-practice.md` → `ku_writing-practice.md`, `yoga yaml.md` → `ku_yoga.md`.

### Semantic (Mike's judgment required)
7. **`ku_older_vault/`**: promote the 9 unique YAMLs into `Ku/` proper, delete the 69
   duplicates + 3 scratch `.md` files, remove the directory.
8. **LP/Principle blockage**: fix the code (Contract Gap 1) — recommended — or add a
   redundant `title:` next to `name:` in the 4 files as a vault-side workaround.
9. **Edge bundles**: explode the non-redundant ~40 inner edges into per-edge files
   (`l:`→`ps.`, retired rel names mapped: `REQUIRES`→`PREREQUISITE_FOR` reversed or
   `prerequisite_step_uids` on the PS, `HAS_LESSON`/`CONTAINS_STEP`/`NEXT_STEP` →
   decide per case), drop the `USES_KU`/LP-wiring duplicates, delete the 5 bundle files.
10. **Dead-weight fields**: strip clear residue (`heading`, edge `version`); keep authored
    semantics (`why_important`, `tradition`, `personal_interpretation`, …) as
    Obsidian-only fields; decide on the 4 step files' `completed/notes/priority`.
11. Optional enrichment: add missing `tags`/`description` (~15 files).

### Verification (after approved fixes)
Re-run `/tmp/vault_audit.py`: expect 0 BLOCKING, 0 duplicate UIDs, dry-run shows the LPs,
Principles, blocked Choices and new edge files as creates, and the three dangling-ref
warnings gone. Still no real ingestion — first live sync stays with Mike
(`./dev vault-watch --once`).

---

# Phase 2 — EXECUTED 2026-06-12 (all 5 decisions approved by Mike)

Vault backup before any edit: `/tmp/0vault-backup-20260612-140111.tar.gz`.

| Step | Result |
|---|---|
| Mechanical batch (items 1–6) | 28 operations: 2 `user_uid` fixes, `.yaml.md`→`.yaml` rename, 2 description quotings, 14 PS `requires`→`prerequisite_step_uids` (8 with targets, 6 empty dropped), caffeine edge moved into `edges/`, 8 Ku filename normalizations |
| `ku_older_vault/` | 9 unique YAMLs promoted into `Ku/` (verified: zero remaining files lacked an outer UID twin), 69 duplicates + 3 scratch deleted, directory removed |
| App-code fix | PR #300 — `required_fields` name→title for LP/Principle + regression test + docs sync (UNIFIED_INGESTION_GUIDE + yaml-to-graph tables, `config.py` comment block) |
| Edge bundles | 24 new single-edge files (consciousness web ×11, Ku laterals ×7, cross-domain ×4, PS→Exercise ×2), 3 PS frontmatter additions (`connections.related`/`enables`), 5 bundles deleted. All curriculum-structure edges verified redundant with modern frontmatter (`uses_kus`/`knowledge_uids`/`trains_ku_uids`/`prerequisite_step_uids`/`contains_steps`/`sequence`). **Skipped (dangling targets):** 2 edges to unauthored `principle:attention-over-intensity` / `principle:small-steps` — re-add if those principles get written |
| Residue strip | `heading` ×52 (Ku), `version` ×34 (edge files), `completed`/`priority` ×4 each (step files; values were pure defaults), empty `prerequisites: []` ×1 (LP). **Kept as authored:** `notes`, `difficulty`, Habit `category`/`difficulty`, LP `goal` + non-empty `prerequisites`, all Principle narrative fields incl. `related_principle_uids` |

## After-state (re-audit, live dry-run)

- **0 BLOCKING / 0 DEGRADED** (was 19 / 14); 176 COSMETIC, all accepted-as-canonical
  (colon UIDs, authored fields, ~15 missing `tags`)
- 187 files (was 240): −72 `ku_older_vault`, −5 bundles, +24 single edges
- 0 duplicate UIDs (was 69)
- Dry-run: **7 creates** — exactly the previously-blocked entities (`lp.mindfulness-101`,
  `lp.self-reflection-101`, `principle.observation-before-action`,
  `principle.precision-over-speed`, `choice.observe-or-fix`, `ku.consciousness.self`,
  `ku.consciousness.presence`) — + 122 updates + 58 skips (all edge files; the dry-run
  preview doesn't list edges, they ingest in a real run), 0 validation errors
- The 3 dangling-ref warnings persist in dry-run **by design** — they check the live
  graph, and the LPs/Principles enter it on the first real sync. Expected to clear then.
