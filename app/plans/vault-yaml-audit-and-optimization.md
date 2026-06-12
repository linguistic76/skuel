# Investigation Prompt: Vault YAML Audit & Optimization

> **How to use:** paste the prompt below into a FRESH Claude Code session.
> **Sequencing:** this runs BEFORE the first live vault sync (`./dev vault-watch --once`)
> and BEFORE the journal/reports investigation (`plans/journal-pipeline-and-report-convergence-investigation.md`).
> Rationale: the first incremental sync ingests whatever is in the vault — a clean corpus
> first avoids ingest-then-fix churn.

---

## Prompt

Audit and optimize the YAML frontmatter across my Obsidian content vault at
`/home/mike/0bsidian/0vault/` (~162 `.md` + ~78 `.yaml` files, organized in per-type
subdirectories: Ku, Ps, Lp, Task, Goal, Habit, Event, Choice, Prin, Exer, edges — plus
possible strays at the root). I believe the YAML in these files is NOT aligned with what
SKUEL's ingestion contract considers optimal. Find every misalignment and fix the corpus,
in two phases: report first, then fix with my approval.

### The contract to audit against (verify in code, don't trust this summary)

- `core/services/ingestion/config.py` — `ENTITY_CONFIGS`: the 14 ingestible entity types,
  their required fields, UID prefixes, and relationship field mappings. This is the source
  of truth for "optimal YAML" per type.
- `core/services/ingestion/validator.py` — `validate_entity_data`, `validate_edge_data`,
  UID-prefix validation. `core/services/ingestion/detector.py` — `type:` field rules and
  aliases (explicit `type` is REQUIRED, no silent defaults; legacy ADR-054 type names like
  `je_input`/`exercise_submission` are rejected).
- Edge files: `type: Edge` + `from`/`to`/`relationship` (must be a valid `RelationshipName`)
  + optional evidence fields (confidence, polarity, temporality, source). Edge YAMLs in
  `.md` form — check whether markdown edges even parse (there is at least one stray:
  `caffeine_exacerbates_buzzing.md` at the vault root).
- `core/utils/embedding_text_builder.py` — `EMBEDDING_FIELD_MAPS`: which fields feed
  embeddings per type. Fields present in frontmatter but read by NOTHING (not in entity
  config, not embedded) are dead weight — list them.
- Reference templates: `yaml_templates/` in the repo (`_schemas/edge_template.yaml` etc.)
  and the activity vault template served by `/upload/template`.

### Phase 1 — Audit (read-only, no vault writes)

1. **Dry-run the whole vault** through the real validator: compose the ingestion service
   (see `scripts/ingest_nous.py` for the direct-composition pattern, or use
   `UnifiedIngestionService.ingest_directory(..., dry_run=True)`) against
   `/home/mike/0bsidian/0vault/`. Dry-run validates and previews without writing to Neo4j.
   Collect every error with file, field, and reason.
2. **Static frontmatter sweep** beyond hard errors: per file, classify
   - missing/legacy/aliased `type` values (aliases work but canonical is cleaner),
   - UID issues (missing, wrong prefix, colon-vs-dot form),
   - required fields missing; recommended fields (description, tags) missing,
   - fields nothing reads (dead weight),
   - per-directory consistency (does everything in `Task/` actually declare `type: task`?),
   - strays (root-level files, edges outside `edges/`, .md where .yaml is required —
     note Activities are YAML-only per the ingestion guide; check which types accept md).
3. **Deliver a findings report**: counts by category, a per-file table for hard failures,
   and a proposed canonical frontmatter template per entity type. Distinguish
   (a) BLOCKING (file will fail ingestion), (b) DEGRADED (ingests but loses data/meaning),
   (c) COSMETIC (works, non-canonical).

### Phase 2 — Optimize (vault writes, gated)

- Propose the fix plan grouped by mechanical vs. semantic:
  - **Mechanical** (safe batch rewrite): canonical type names, uid normalization,
    field renames where the mapping is 1:1, moving strays into the right directory.
  - **Semantic** (needs my judgment): missing required content, ambiguous types,
    dead-weight fields that might be MY notes worth keeping (Obsidian-only fields are
    legitimate — flag, don't auto-delete).
- WAIT for my approval on the plan before writing to the vault. The vault is my authored
  content and is Obsidian-synced — edits propagate to my devices. Preserve markdown bodies
  byte-for-byte; only touch frontmatter unless I approve otherwise.
- After fixes: re-run the dry-run to prove zero BLOCKING findings remain, and report the
  before/after counts.

### Constraints

- Do NOT run a real (non-dry-run) ingestion — the first live sync happens after this audit,
  via `./dev vault-watch --once` (needs the `vault_watcher` account I provision myself).
- Do NOT edit `node_modules/yaml` (JS package, unrelated). SKUEL's YAML layer is PyYAML in
  `core/services/ingestion/parser.py` + `core/utils/frontmatter.py`.
- If the audit reveals the CONTRACT is suboptimal (not the files) — e.g. a field every file
  carries that ingestion ignores but should read — report that as a separate
  "contract gaps" section; changing app code is a separate decision, not part of the
  vault rewrite.
