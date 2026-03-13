# Obsidian Headless Sync Integration

**Created:** 2026-03-10
**Status:** Planned
**Principle:** Leverage Maintained Software (see below)

---

## Design Principle: Leverage Maintained Software

SKUEL is built by a non-technical founder through an analog-to-digital partnership — plain English
in, working code out. This means every custom-built subsystem is a maintenance liability. When
established, well-maintained software solves a problem, SKUEL adopts it rather than building a
bespoke alternative.

**Examples already in practice:**
- **Neo4j** (graph database) → future **AuraDB** (managed Neo4j)
- **Prometheus + Grafana** (observability) — industry-standard, community-maintained
- **MonsterUI (FrankenUI + Tailwind)** (UI) — maintained component library over hand-rolled CSS
- **FastHTML** (web framework) — maintained framework over custom server code

**This roadmap item:** Replace SKUEL's implicit "files are on the same machine" assumption with
**Obsidian Headless Sync** — Obsidian's official CLI tool for server-side vault synchronization.
Authors write in Obsidian (a tool they already know). Obsidian Sync delivers files to the server.
SKUEL's ingestion service consumes them. No custom sync code to maintain.

---

## What Obsidian Headless Is

An official, first-party Node.js CLI tool (`npm install -g obsidian-headless`) that provides
command-line access to Obsidian Sync. Open beta as of early 2026. Requires Node.js 22+.

**Key properties:**
- Same end-to-end encryption as desktop Obsidian Sync
- Runs on any server with Node.js — no Electron, no GUI
- Authenticated via Obsidian account (email/password + MFA)
- Syncs vault files to a local directory, identical to desktop behavior

**Storage limits (Obsidian Sync):**

| | Standard ($4/mo) | Plus ($8/mo) |
|---|---|---|
| Total storage | 1 GB | 10-100 GB |
| Max file size | 5 MB | 200 MB |
| Vaults | 1 | 10 |
| Version history | 1 month | 12 months |

For Markdown/YAML curriculum content, Standard (1 GB) is likely sufficient. Version history
provides a safety net for content recovery.

---

## What Gets Synced

Content authored in Obsidian that maps to SKUEL entity types:

| Content Type | EntityType | Typical Format |
|-------------|-----------|----------------|
| Knowledge Units | `KU` | Markdown with YAML frontmatter |
| Articles | `ARTICLE` | Markdown with YAML frontmatter |
| Learning Steps | `LEARNING_STEP` | YAML or Markdown |
| Learning Paths | `LEARNING_PATH` | YAML |
| Activity templates | `TASK`, `GOAL`, `HABIT`, `EVENT`, `CHOICE`, `PRINCIPLE` | YAML |
| Relationship edges | Edge YAML | YAML (`type: Edge`) |
| Exercises | `EXERCISE` | Markdown with YAML frontmatter |

The Obsidian vault at `/home/mike/0bsidian/skuel/docs/` is already the content source. This
roadmap item makes that relationship explicit and deployable.

---

## Architecture

```
┌──────────────────────┐
│  Authors (Obsidian)  │  ← Write Markdown/YAML in Obsidian desktop/mobile
│  Teacher devices     │
└─────────┬────────────┘
          │ Obsidian Sync (encrypted, automatic)
          ▼
┌──────────────────────┐
│  Obsidian Cloud      │  ← Obsidian's servers (encrypted at rest)
└─────────┬────────────┘
          │ Obsidian Headless Sync (pulls to server)
          ▼
┌──────────────────────┐
│  Server vault copy   │  ← /opt/skuel/vault/ (or configured path)
│  (local filesystem)  │
└─────────┬────────────┘
          │ File watcher (inotify/systemd path unit)
          ▼
┌──────────────────────┐
│  POST /api/ingest/   │  ← SKUEL's existing ingestion API
│  vault               │     (incremental mode, SHA-256 skip)
└─────────┬────────────┘
          │
          ▼
┌──────────────────────┐
│  Neo4j               │  ← Entities, relationships, embeddings
└──────────────────────┘
```

**What SKUEL builds:** Nothing new. The ingestion service already handles everything downstream.
The only new infrastructure is:
1. `obsidian-headless` installed on the server (npm package)
2. A systemd service to keep it running
3. A file watcher to trigger ingestion on changes

---

## Implementation Plan

### Phase 1: Local Proof of Concept (Current Stage)

**Trigger:** Can start now — local development machine already has the vault.

1. Install `obsidian-headless` globally: `npm install -g obsidian-headless`
2. Authenticate with Obsidian account
3. Configure sync to a **separate directory** (not the live vault) to verify behavior
4. Test: edit a file in Obsidian → confirm it appears in the synced directory
5. Run `POST /api/ingest/vault` against the synced directory in incremental mode
6. Verify entities created/updated correctly in Neo4j

**Validates:** End-to-end flow works, incremental ingestion handles Sync's file delivery.

### Phase 2: Automated Trigger

**Trigger:** Phase 1 validated.

1. Set up a file watcher (inotify on Linux, fswatch on macOS) on the synced vault directory
2. On file change → call `POST /api/ingest/vault` with incremental mode
3. Debounce: wait 5 seconds after last change before triggering (Sync may deliver multiple
   files in a batch)
4. Log ingestion results

**Alternative:** Cron job running `POST /api/ingest/vault` every N minutes. Simpler, slightly
less responsive. Incremental mode makes this cheap even if nothing changed.

### Phase 3: Server Deployment (Stage 2 — Droplet)

**Trigger:** DigitalOcean Droplet deployment is ready (see `DO_MIGRATION_GUIDE.md`).

1. Add `obsidian-headless` to server provisioning (Node.js 22+ required alongside Python)
2. Create systemd service: `obsidian-headless-sync.service`
   - Runs as dedicated user (not root)
   - Vault synced to `/opt/skuel/vault/`
   - Auto-restart on failure
3. Create systemd path unit: `skuel-ingest.path`
   - Watches `/opt/skuel/vault/` for modifications
   - Triggers `skuel-ingest.service` which calls the ingestion API
4. Environment variable: `SKUEL_VAULT_PATH=/opt/skuel/vault/` consumed by ingestion endpoints
5. Credentials: Obsidian account credentials stored securely (systemd credential store or
   environment file with restricted permissions)

### Phase 4: Multi-Author Workflow

**Trigger:** Multiple teachers/curriculum authors exist.

1. Enable Obsidian Sync shared vault — all authors sync to the same vault
2. Headless Sync on server receives all authors' changes
3. Ingestion service processes everything identically (content is admin-created, shared scope)
4. Obsidian Sync handles conflict resolution at the file level before SKUEL ever sees it

---

## What This Replaces

| Current State | With Headless Sync |
|---|---|
| Vault lives on dev machine only | Vault synced to any server automatically |
| Ingestion triggered manually via API/dashboard | Ingestion triggered automatically on file change |
| Single author (local filesystem) | Multi-author via Obsidian Sync shared vaults |
| Deployment requires copying vault to server | Vault arrives via Sync — no manual file transfer |
| `JupyterNeo4jSync` bidirectional sync (complex) | One-way: Obsidian → server → Neo4j (simple) |

---

## What This Does NOT Replace

- **UnifiedIngestionService** — still does all parsing, type detection, validation, relationship
  creation, bulk ingestion, and Neo4j persistence. Headless Sync is file delivery only.
- **The ingestion dashboard** — still useful for manual triggers, dry-run previews, and monitoring.
- **Edge YAML ingestion** — relationship files still authored in Obsidian, still ingested normally.
- **Incremental tracking** — SKUEL's SHA-256 content hashing still prevents re-processing
  unchanged files, even if Sync touches their mtime.

---

## Cost

| Item | Cost | Notes |
|---|---|---|
| Obsidian Sync Standard | $4/month | 1 GB, 1 vault — likely sufficient |
| Obsidian Sync Plus | $8/month | 10 GB, 10 vaults — if attachments grow |
| Node.js on server | Free | Already common in server environments |
| `obsidian-headless` | Free | Official npm package |

Compare to alternatives:
- Git-based sync: Free, but requires authors to use git (friction for non-technical users)
- rsync/scp: Free, but manual or requires custom scripting (maintenance liability)
- Custom sync service: Free, but SKUEL would own the code (violates Leverage Maintained Software)

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Headless is in open beta | Low-stakes integration — files on disk. If it breaks, vault is still in Obsidian. Manual ingestion as fallback. |
| Obsidian Sync is a paid service | $4/mo is trivial vs. building/maintaining custom sync. Cancel anytime. |
| Node.js dependency on server | Minimal — single global npm package. No build step, no node_modules in SKUEL. |
| Obsidian account credentials on server | Systemd credential store or env file with 600 permissions. Dedicated Obsidian account for server (not personal). |
| Sync conflicts | Obsidian Sync resolves conflicts before files reach the server. SKUEL never sees conflicts. |

---

## Related Documents

- `/docs/architecture/CORE_SYSTEMS_ARCHITECTURE.md` — ingestion as foundational system
- `/docs/patterns/UNIFIED_INGESTION_GUIDE.md` — ingestion service details
- `/docs/deployment/DO_MIGRATION_GUIDE.md` — Stage 2 server deployment
- `/docs/architecture/ANALOG_DIGITAL_ARCHITECTURE.md` — Analog layer runs at $0
- `/docs/decisions/ADR-043-intelligence-tier-toggle.md` — cost-conscious design
