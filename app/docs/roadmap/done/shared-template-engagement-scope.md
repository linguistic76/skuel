---
title: "Engagement Instance Scope — the query that cannot tell two engagements apart"
status: done
registered: 2026-09-06
ruled: "2026-09-23 (Mike): option 2, stamped on the edges — a minted `uid` on ENGAGED_WITH, carried as `engagement_uid` on every SPAWNED_FROM the engagement writes"
updated: 2026-09-23
---

# Engagement Instance Scope — the query that cannot tell two engagements apart

*Fixed 2026-09-23 in the goal-link arc's PR 3. Registered as a
[deferred-work.md](../deferred-work.md) entry; the defect as found is kept below, followed by
[what shipped](#what-shipped).*

*Found 2026-09-06 while verifying a claim for
[ACTIVITY_TEMPLATE_AUTHORING.md](../../guides/ACTIVITY_TEMPLATE_AUTHORING.md)'s reuse
section — the guide advertises template reuse across PathSteps, and the claim did not
survive being checked against the code.*

## The defect

`PsEngagementBackend.fetch_engaged_instances` defines *"the instances belonging to this
engagement"* as **every instance the student owns that was spawned from a template
attached to this PathStep**:

```cypher
MATCH (ps {uid: $ps_uid})-[:HAS_TASK_TEMPLATE|…]->(t)
MATCH (n {user_uid: $student_uid})-[:SPAWNED_FROM]->(t)
WHERE n.engagement_state IN ['engaged', 'owned']
```

Nothing in it names an engagement. The service method's docstring states the assumption
it rests on — *"Safe because the at-most-one-active invariant ensures the only engaged
instances belong to the current engagement"* — and that invariant is **per (student,
PathStep)**, not per student. `find_active` and `open_engagement` refuse only a second
*concurrent* engagement of the *same* step.

It is the read behind both `complete_engagement` and `abandon_pathstep`, so a wrong row
is deleted or re-stated, not merely displayed.

## Two ways the ordinary flow reaches it

**1. Re-engaging one step — needs no reuse at all.** `open_engagement` creates a *new*
edge and its refusal message says "complete or abandon it first", so re-engagement is the
intended flow:

1. Engage PS-A → `habit_1` spawns, `engaged`.
2. Complete, keep it → `habit_1` becomes `owned`. It now outlives the step, which is the
   documented meaning of *keep*.
3. Engage PS-A again → `habit_2` spawns, `engaged`.
4. Abandon → the query returns **both** (`owned` is in its state list) → **`habit_1` is
   deleted**, months after the learner earned it.

**2. One template on two steps — the reuse the guide advertises.** `ht.X` attached to
PS-A and PS-B; the learner engages both. `fetch_engaged_instances(student, ps_A)` matches
PS-B's instance too, because it also points at `ht.X`. Completing A marks B's instance
`owned`; abandoning A deletes it.

## Why it is latent, not live

Zero activity templates existed before 2026-09-05. The six authored in the vault-door
arc's PR-2 all sit on one PathStep (`ps.mindfulness-101.step-1`), and no learner has
engaged it twice. The first shared template, or the first re-engagement, makes it live.

## The shape of a fix

`SPAWNED_FROM` already carries `spawned_at`, and the engagement edge carries `since` —
the scoping predicate exists in the data. Candidates, cheapest first:

1. **Filter by anchor.** Add `AND n.spawned_at >= $since` using the current engagement's
   `since`. Fixes case 1 completely and case 2 only when the two engagements differ in
   time, so it is a narrowing, not a fix.
2. **Stamp the engagement on the instance.** Carry an engagement identifier onto the
   spawned instance (or onto `SPAWNED_FROM`) and scope by it. This is the honest fix —
   "which engagement spawned this" becomes a stored fact rather than an inference.
3. **Edge from the engagement.** `(engagement)-[:SPAWNED]->(instance)`. Most graph-native,
   most work; the `ENGAGED_WITH` relationship would have to become a node.

⚠ Whatever is chosen, `complete_engagement` and `abandon_pathstep` must be pinned by a
test that engages **twice** and by one that shares a template across **two** steps — the
two shapes no existing test covers, which is why the assumption in the docstring went
unchallenged.

## What shipped

Option 2, with the stamp on the edges rather than the instance node, so the six domain models
and their DTOs stay untouched:

```
(User)-[:ENGAGED_WITH {uid, since, state, completed_at?, abandoned_at?}]->(PathStep)
(instance)-[:SPAWNED_FROM {spawned_at, engagement_uid}]->(template)
```

- `_EngagementGateway.open_engagement` mints the uid (`engagement_…`); `Engagement.uid`
  carries it, and `engage_pathstep` hands it to the spawn orchestrator, which passes it to
  `create_with_spawned_from` for every instance.
- `fetch_engaged_instances` and `list_review_items` share one match: the pair's active
  `ENGAGED_WITH` edge, then the student's `:OWNS` instances whose `SPAWNED_FROM` carries its
  uid. The `HAS_*_TEMPLATE` hop is gone. As a result, taking a template off a PathStep no
  longer strands the instances a live engagement already spawned from it.
- `fetch_auto_complete_siblings` had the same defect in a third form. It found the PathStep
  through the template, so a shared template gave it several steps and `LIMIT 1` picked one
  of them. It now takes the step from the engagement named on the instance's own
  `SPAWNED_FROM` edge.
- `'owned'` stays in the state list. It covers only a completion that failed part-way, and an
  earlier engagement's owned instances carry that engagement's uid.

A read-only count on AuraDB before the change found no `ENGAGED_WITH` or `SPAWNED_FROM`
edges, so there was nothing to backfill.

`TestEngagementInstanceScope` in `tests/integration/test_ps_engagement_lifecycle.py` pins the
two shapes the docstring's assumption hid: engaging the same step twice (then abandon, and then
complete with every template discarded), and one template shared by two steps (`list_engaged`,
the review, the sibling read, abandon and complete). All three tests failed on `main`. Removing
either scoping predicate fails at least one of them.
