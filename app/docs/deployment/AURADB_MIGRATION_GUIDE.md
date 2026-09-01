---
title: AuraDB Migration Guide
updated: 2026-08-29
category: deployment
tags: [deployment, auradb, neo4j, migration]
related_skills:
  - neo4j-cypher-patterns
---
# AuraDB Free Data Migration Guide

**Last Updated:** 2026-08-16
**Migration Type:** Data move — local Docker Neo4j → Neo4j AuraDB Free
**Status:** Executed 2026-08-15 (instance `skuel`, `d2d160c4`, US West) — kept as the re-run recipe. The app runs locally against Aura; public hosting (droplet) stays parked, and local Docker Neo4j is a stopped opt-in sandbox.
**Estimated Time:** 1–2 hours

---

## 1. Overview

This guide moves the **graph data** from the local Docker Neo4j (`infrastructure/docker-compose.yml`) into a **Neo4j AuraDB Free** instance. It is deliberately narrow: data out, data in, verify. Deploying the app that talks to that instance is [DO_MIGRATION_GUIDE.md](./DO_MIGRATION_GUIDE.md) (droplet + Caddy); the strategic reasoning is [ADR-080](../decisions/ADR-080-auradb-three-horizon-strategy.md).

Almost everything ports with zero work, because the pieces were built that way:

- **Embeddings are Python-side** — OpenAI `text-embedding-3-small` @ 1024 dims (ADR-068). No Neo4j server plugin, nothing to configure on Aura. (Older revisions of this guide said HuggingFace; ADR-068 superseded ADR-049 — OpenAI now, BGE staged for later.)
- **Schema auto-creates at bootstrap** — unique constraints + the 7 vector indexes (1024 dims, cosine) are created by `Neo4jSchemaManager` on app startup (`services_bootstrap/compose.py`), fail-fast. There is no constraint script to run and nothing to verify by hand: the first boot against Aura either creates the schema or refuses to start.
- **APOC surface fits** — SKUEL uses only `apoc.meta.*`, which works on Aura's APOC subset (confirmed against a scratch Free instance, 2026-07-24; `apoc.meta.stats()` answers).
- **Connection is an env change** — `NEO4J_URI`/`NEO4J_PASSWORD`; the code is environment-agnostic (ADR-044).
- **A paused Free instance is tolerated** — Free auto-pauses on inactivity; every startup path wraps the initial connect in bounded backoff (`connect_with_retry`, bounds in `/core/constants.py` `Neo4jConnectRetry`). Mid-request pause resilience is deliberately deferred (ADR-080 "When to Revisit").

What actually needs doing, in order: **prune → export counts → dump → upload → point config at Aura → boot once → compare counts.**

### Free-tier constraints that shape this guide

| Constraint | Number | Consequence |
|-----------|--------|-------------|
| Node cap | **200,000** | prune telemetry BEFORE dumping (step 3) |
| Relationship cap | **400,000** | same; alerts fire at 80% (`/monitoring/prometheus/alerts.yml`) |
| Auto-pause | after ~72 h without connections | while the app runs, its 5-min metrics poller keeps the instance active; bounded connect retry covers wake-up after real downtime |
| Backups | on-demand snapshots only, one at a time | see the runbook in [DO_MIGRATION_GUIDE.md](./DO_MIGRATION_GUIDE.md) |

Caps verified 2026-07-24 against the Neo4j Aura FAQ — the 50k-node/175k-relationship figures still shown on some Neo4j product pages are the stale 2021 launch limits.

---

## 2. Prerequisites

- [ ] Aura account + a **Free** instance created at https://console.neo4j.io/ (pick the region closest to where the app runs). **Download and keep the credentials file** — it is shown once, and on Free it is the only recovery path: AuraDB Free refuses ALL user-admin Cypher (`ALTER USER` / `CREATE USER` → `42NFF`), so the generic Aura lost-credentials recovery flow does not apply — lost credentials mean clone/recreate.
- [ ] Local Neo4j running with current data — started through the compose project that owns the container (see § 4).
- [ ] A quiet app — stop `main.py`/containers writing to the local graph before dumping.

---

## 3. Prune, then export the "before" counts

Prune first, export second — then the export describes **exactly** what the dump carries, and the post-migration comparison needs no exclusion logic.

```bash
cd /home/mike/skuel/app

# See what a prune would delete (deletes nothing)
./dev telemetry-retention --dry-run

# Prune system telemetry (AuthEvent / SearchEvent / Interaction / stale VIEWED,
# expired Session / PasswordResetToken). Saved discussions are never touched.
./dev telemetry-retention

# Snapshot the pruned counts — pure Cypher, JSON to stdout
uv run python scripts/export_entity_counts.py > before.json
```

---

## 4. Dump the local database

⚠️ **Run stop/dump/start through the compose project that OWNS the running container** — `docker compose` manages only its own project's containers. Both `infrastructure/` and `app/` can own `skuel-neo4j` (the app compose `extends` the infrastructure definition); on the dev machine it is typically the **`app`** project. Aimed at the wrong project, `stop neo4j` is a silent no-op and the one-off dump container then fails against the still-running instance (2026-08-15 cutover finding). Check first:

```bash
docker inspect skuel-neo4j \
  --format '{{ index .Config.Labels "com.docker.compose.project" }}'
```

```bash
# The dump runs as container uid 7474, but the host dir behind the /backups
# volume is owned by your user — open it for the dump, revert afterwards
chmod o+w /home/mike/skuel/infrastructure/neo4j/backups

cd /home/mike/skuel/app   # or infrastructure/ — whichever project the check named

docker compose stop neo4j
# --to-path is a DIRECTORY — the tool writes <database>.dump (here: neo4j.dump)
# into it; --overwrite-destination replaces a leftover from an earlier attempt
docker compose run --rm neo4j \
  neo4j-admin database dump neo4j --to-path=/backups --overwrite-destination=true
docker compose start neo4j

chmod o-w /home/mike/skuel/infrastructure/neo4j/backups

# /backups is volume-mapped to infrastructure/neo4j/backups on the host;
# stamp it with a date
cd /home/mike/skuel/infrastructure
mv neo4j/backups/neo4j.dump "neo4j/backups/aura_migration_$(date +%Y%m%d).dump"
ls -lh neo4j/backups/
```

Verify the dump file exists with non-zero size before proceeding.

---

## 5. Upload the dump to Aura

In the [Aura console](https://console.neo4j.io/): select the instance → **Import/Restore** → upload the `.dump` file → wait for completion.

**Compatibility note:** the local server runs the calendar release pinned in `infrastructure/docker-compose.yml` (ADR-067 § 3a — `2026.06.0` at the 2026-08-15 cutover; read the pin, don't trust this sentence). Confirm the console accepts a dump from that line at migration time (Aura's import path and its accepted formats have changed before — e.g. the 2024 dump→`.backup` export format change). If the upload is rejected, the fallback is a Cypher-level export/import; at SKUEL's data volume that is tedious but tractable.

---

## 6. Update Application Configuration

### 6.1 Point the environment at Aura

Wherever the app runs (locally: `.env`; droplet, if/when unparked: `/opt/skuel/app/.env.production` + `/opt/skuel/secrets.env`):

```bash
NEO4J_URI=neo4j+s://<dbid>.databases.neo4j.io
NEO4J_USERNAME=<dbid>
# NEO4J_PASSWORD → keychain (local) / secrets.env (droplet)
```

⚠️ **Aura database usernames are the INSTANCE ID, not `neo4j`** (burned an hour at the 2026-08-15 cutover). The credentials file downloaded at instance creation is authoritative — copy its `NEO4J_USERNAME=<dbid>` verbatim. Authenticating as `neo4j` returns `Unauthorized` even with the correct password, indistinguishable from a bad password.

`neo4j+s://` is required in production — `SKUEL_ENVIRONMENT=production` boot-refuses plaintext schemes (`/core/config/validation.py`). TLS comes solely from the URI scheme; there is no separate encryption knob (the dead `NEO4J_ENCRYPTED` flag was deleted).

There is no database-name knob either. Every query opens on the driver's **home database** — no call site passes `database=` / `database_=` — which is `neo4j` on both self-hosted Community (single user database) and AuraDB. The inert `NEO4J_DATABASE` flag was deleted for the same reason as `NEO4J_ENCRYPTED`: it was documented but never reached a query.

### 6.2 Remove Docker-Specific Configuration (self-host-only knobs)

These knobs exist **only because SKUEL self-hosts Neo4j** — AuraDB provides each by default, so they disappear on migration and are not worth further investment. They are marked in the compose files with a grep-able `# AURA-TEMPORARY:` comment; run `grep -rn "AURA-TEMPORARY" infrastructure/ app/` to find every one.

**Remove or comment out (env / `.env`):**

```bash
# ❌ REMOVE - self-host-only (AuraDB manages memory by instance tier)
# NEO4J_HEAP_INIT=512m
# NEO4J_HEAP_MAX=2G
# NEO4J_PAGECACHE=1G
```

**Drop from the compose Neo4j service (each managed by AuraDB):**

| Knob | Why it disappears on Aura |
|------|---------------------------|
| `NEO4J_server_memory_heap_*`, `NEO4J_server_memory_pagecache_size` | AuraDB sizes memory by the chosen instance tier |
| `NEO4J_server_jvm_additional: --add-modules jdk.incubator.vector` | AuraDB enables the Vector API (SIMD) by default — vector search is optimal without the flag |
| `image: neo4j:<calendar-monthly>` version pin | AuraDB auto-upgrades — the ~monthly bump obligation goes away |

**Keep — these port cleanly (driver/app-side, not server knobs):** the per-query timeout (`TimedDriver`), schema-change monitoring (`NEO4J_SCHEMA_MONITORING`), and APOC allowlist scoping all apply above the server and work unchanged against AuraDB.

Note these knobs only *matter* while the local self-hosted instance is the production store. Once production is on Aura, the local compose files keep their knobs for local development — the markers stay as documentation of the split.

---

## 7. First boot against Aura

Boot the app once against the new URI. This **is** the schema migration:

```bash
# Locally against Aura (quick check):
cd /home/mike/skuel/app && uv run python main.py

# Or on the droplet: deploy normally — the health gate covers the boot
./dev deploy
```

On startup, `Neo4jSchemaManager` creates any missing unique constraints and the 7 vector indexes (Entity, ContentChunk, ReferenceChunk, Goal, Task, Ku, PathStep — 1024 dims, cosine), fail-fast: a schema problem stops boot with a clear error rather than degrading. `connect_with_retry` absorbs the instance waking from pause. `/health/ready` returning 200 means Neo4j answered.

---

## 8. Verify

```bash
cd /home/mike/skuel/app

# Point NEO4J_* at Aura for this shell if not already, then:
uv run python scripts/export_entity_counts.py --compare before.json
```

Exit 0 with a `Match — N nodes / M relationships identical` line on stderr means every per-label and per-relationship-type count survived the move; exit 1 lists each mismatch. (A multi-label node counts once under each label on both sides — deterministic, which is all a diff needs.)

Then smoke by hand: log in, run a search, open an entity detail page, create + complete a task. Take an Aura **snapshot** once verified — that is your post-migration restore point.

---

## 9. Rollback

The local database is untouched by this entire procedure — the dump is a copy. What "backing out" means depends on which app was pointed at Aura. In both cases the app reads its env **at startup**: editing an env file does nothing until the app is restarted.

**Local app (step 7's quick check went wrong):** edit local `.env` back to the local instance and restart:

```bash
# in app/.env:  NEO4J_URI=bolt://localhost:7687   (or neo4j://localhost:7687)
cd /home/mike/skuel/infrastructure && docker compose up -d   # ensure local Neo4j is running
cd /home/mike/skuel/app && uv run python main.py             # restart — env is read at boot
```

**Droplet:** there is no local-Neo4j fallback for production — by design. The droplet app reads `/opt/skuel/app/.env.production` + `/opt/skuel/secrets.env`, and the production boot guard refuses plaintext URI schemes, so it can only ever talk to an encrypted (Aura) endpoint. If Aura data is bad *after* cutover:

- restore the post-migration **snapshot** from the console (Snapshots tab) — no config change, but restart the stack afterwards so connections re-establish cleanly (`docker compose -f docker-compose.production.yml restart skuel-app`), or
- re-run this guide from the latest local dump, or
- if the instance is unusable entirely, stop the stack (`docker compose -f docker-compose.production.yml down`) until it's resolved — a droplet pointed at nothing is honest downtime, not a silent wrong-database.

---

## Related Documentation

- [Droplet Deployment Guide](./DO_MIGRATION_GUIDE.md) — the stack that talks to this instance, and the operations runbook (retention cron, snapshot cadence, alerts)
- [Neo4j Setup Migration Summary](./NEO4J_SETUP_MIGRATION_SUMMARY.md) — how the deployment path evolved
- [ADR-080: AuraDB Three-Horizon Strategy](../decisions/ADR-080-auradb-three-horizon-strategy.md) — why Free, why now, what is deliberately deferred
- [ADR-068: OpenAI embeddings now, BGE later](../decisions/ADR-068-openai-embeddings-now-bge-later.md) — why embeddings need no server plugin
- [Neo4j Aura backup/export docs](https://neo4j.com/docs/aura/managing-instances/backup-restore-export/)

---

**Last Updated:** 2026-08-16
**Maintained By:** SKUEL Core Team
