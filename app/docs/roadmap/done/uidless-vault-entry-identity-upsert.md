# Path-keyed identity for uid-less vault UserEntries

**Shipped** 2026-07-12 (#616). This is the contract the ingestion code cites.

A personal knowledge note with no `uid:` frontmatter has no identity of its own, so
ingestion has to supply one. **The file's path is that identity.**

## The ruling

**Path = identity for uid-less vault files.** This was already the deletion-propagation
contract — the tracker keys deletions on path. Updates honor the same contract: at the
vault ingest door, look up the tracker's prior uid for the file path and pass it as
`request.uid`, routing the note through the existing MERGE-on-uid living-entry channel. No
vault mutation, no new identity machinery.

Before this, a uid-less note minted a fresh random `ue_` uid on **every** re-ingest while
the tracker's path→uid row was simply overwritten, orphaning the old node along with its
chunks, grounding edges and `created_at`. Measured damage at ruling time: 276 stale orphans
out of 357 knowledge-pipeline UserEntry nodes, holding 380 of 502 `APPLIES_KNOWLEDGE`
grounding edges — so the ZPD fourth signal counted the same note three or four times. The
orphans were removed by `scripts/cleanup_untracked_vault_entries.py` in the same arc.

### Rejected alternatives (do not revisit)

- **uid-injection write-back** into the author's notes — invasive, and needs dual-transport
  write-back.
- **Reconciler retirement sweep** — symptom-only; retraction stays broken between sweeps.

## The gates

`build_user_entry_request` reuses the prior uid **only when all three hold**:

| Gate | Why |
|---|---|
| `uid_override` is None | An authored or periodic uid always wins |
| `fulfills_exercise_uid` is None | **Critical** — see the turn-in trap below |
| `file_path.is_absolute()` | Vault-tracked files only; uploads pass temp paths |

The first sync of a new file has no tracker row, so it mints a random uid as before.

## Private-flip retraction

Flipping a note `private: true` deletes its existing chunks. `APPLIES_KNOWLEDGE` grounding
edges are **not** retracted, and neither is the entity-level embedding.

`private:` is a *companion-retrieval opt-out*, not an evidence opt-out — ZPD grounding is
owner-scoped signal about the owner's own learning, and entity search is owner-scoped too.
The retraction surface is chunks, because chunks are the canon/vault retrieval substrate.

## Traps

1. **The turn-in channel.** `create_entry` derives `turn_in_exercise_uid` as
   `None if request.uid else request.fulfills_exercise_uid`, so injecting a uid into a
   request that carries `fulfills_exercise_uid` silently kills the turn-in channel — frozen
   copy, Interaction, teacher routing all lost. Hence gate 2 above.
2. **Body preservation.** `store_content_with_chunks` has `clear_inline_body` semantics, so
   the UserEntry ingest door must keep `preserve_entity_body=True`. A knowledge note's body
   must survive every sync byte-identical.
3. **Periodic uids stay colon-form.** Derived `ue:daily:{user}:{date}` uids are deliberately
   NOT normalized — the colon form is the calendar-routes join contract.
4. **Tracker rows also encode edge identities** (`EDGE_UID_PREFIX`). A prior-uid lookup for
   a `.md` entity file will never hit one, but do not assume every `entity_uid` in that
   table names a node.

## Accepted trade-off, and how it was closed

A moved or renamed file is a new path, so identity is lost — delete plus recreate,
identical to the deletion semantics of the time. That gap was closed the same day by
content-hash move detection: see
[hash-assisted-move-detection.md](hash-assisted-move-detection.md).

**Related:** `docs/patterns/UNIFIED_INGESTION_GUIDE.md` § path-keyed identity.
