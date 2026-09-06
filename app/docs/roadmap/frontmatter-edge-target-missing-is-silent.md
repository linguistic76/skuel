---
title: "A Frontmatter Edge Whose Target Does Not Exist Yet Is Silent"
updated: 2026-09-06
status: "registered"
registered: 2026-09-06
trigger: "the next ingestion-mechanism touch, or the first authoring session that loses an edge to it"
check: "`git grep -n 'unresolved' core/services/ingestion/batch.py` — empty until the relationship pass reports misses"
---

# A Frontmatter Edge Whose Target Does Not Exist Yet Is Silent

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/`
when nothing in it remains open. Found while driving the vault door in the
[activity-templates-vault-door](activity-templates-vault-door.md) arc, PR-2.*

Every registered `*_uids:` frontmatter channel (`uses_kus`, `exercise_uids`, `task_uids`, the six
`*_template_uids`, …) writes its edge with a `MATCH` on the target. When the target node does not
exist at the moment that file is ingested, the match returns nothing, no edge is written, **and
nothing reports it**. The sync's stats show no error, no warning, and no unresolved count; the
file is recorded as successfully ingested.

Reproduced 2026-09-06 in the ordinary course of authoring, not in a contrived case. Six templates
and their PathStep were added in one sync. One template file failed validation on an unrelated
field, so its node did not exist when the PathStep in the same batch was ingested. The PathStep
got five of its six `HAS_*_TEMPLATE` edges. The sync reported `files_failed: 0` for the PathStep
and listed the template's own failure — with no hint that the two were connected, and no hint
that fixing the template would not be enough. Re-syncing the PathStep afterwards wrote the sixth
edge; nothing prompted that.

The asymmetry is what makes it worth naming: MOC **body links** already have this covered — a
dangling wiki-link is silent in a personal vault and *warned* in the content vault. The
frontmatter uid channels, which carry every structural edge in the curriculum, have no equivalent.

**The fix**, when it is scheduled: the relationship pass counts and returns unresolved targets
per file, and the sync report lists them the way it lists ignored files —
`Ps/…_Ps.md: task_template_uids → tt.… (no such node)`. Ordering is not the fix and never was:
the bulk writer already runs nodes in phase 1 and edges in phase 2, so every node in the batch
exists before any edge is attempted — the miss happens because the target was **never created**,
which no ordering reaches. The unit subquery that swallows it is deliberate and should stay
(`"so later fields are unaffected when a target is missing"`); what is owed is a count, not a
failure.

**Named cost:** a curriculum edge can be missing with no signal anywhere, and the resulting
PathStep is not obviously broken — it just has fewer templates, fewer Kus, or fewer exercises
than the file says.
