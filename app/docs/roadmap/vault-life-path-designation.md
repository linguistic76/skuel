---
title: "How a Vault-Authored LifePath Meets the Designation Model"
updated: 2026-10-02
status: "registered — deferred by ruling"
registered: 2026-10-02
ruled: 2026-10-01
trigger: "the first personal vault that syncs a `type: life_path` file, or the next change to `LifePathCoreService` designation"
check: "live: MATCH (lp:LifePath) WHERE lp.user_uid IS NOT NULL RETURN count(lp) — non-zero means a vault-authored LifePath exists beside the designation edge"
---

# How a Vault-Authored LifePath Meets the Designation Model

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/`
when nothing in it remains open. Registered with ADR-070 Decision 11 (a personal vault writes only
its owner's graph).*

**Ruled 2026-10-01:** a personal vault syncs `life_path` files — "The user must be able to sync
their life_path". How such a node meets the app's designation model is "a bigger question that
can be dealt with later". Decision 11 did only the part that could not wait: a `type: life_path` file is
owned by the vault's owner, whatever its `user_uid:` line says, and needs no `user_uid:` line at
all (`core/services/ingestion/config.py`, `EntityType.LIFE_PATH`). Before it, the file's own
`user_uid:` line was its owner — a file in Alice's vault created a LifePath owned by Bob — and a
file without the line was refused.

## The open question

The app designates a life path by pointing a user at a **LearningPath**:
`LifePathCoreService.designate_life_path(user_uid, lp_uid)` writes `ULTIMATE_PATH`
(`core/services/lifepath/lifepath_core_service.py`), and alignment
(`lifepath_alignment_service.py`) scores the user's activity against that path. A vault file
creates a separate `:LifePath` node with a title and a body. Nothing connects the two:

- Is a vault-authored LifePath the user's statement of their life path (the vision), with the
  designated LearningPath as the route to it — two nodes, one edge between them?
- Or is the vault file another way to designate — so it should name a LearningPath and write the
  same `ULTIMATE_PATH` the app does?
- What happens when the file and the app disagree (the file names one path, the app another)?

None of it is traced or decided. A synced LifePath today is an owned node no reader consults.

## What not to do meanwhile

Do not let ingestion write `ULTIMATE_PATH` or any designation edge from a vault file — that is the
question above, answered by accident.
