---
title: "Roadmap: backend-typing follow-on"
updated: 2026-08-26
status: complete
category: roadmap
tags: [roadmap, typing, protocols, ports, domain-config, done]
---

# Roadmap: Backend-Typing Follow-on

**Status:** ✅ **COMPLETE — 2026-08-21. Queue empty, all three closed.**

These three outlived the backend-typing arc (#1090–#1102, closed 2026-08-20) because none
of them was a retype — each was a decision or a chain. The standing ruling (Mike,
2026-08-20) was that a fresh context takes **ONE** of them, not the set, and that is how
they closed: **A** (#1106) and **B** (#1107) on 2026-08-20, **C** on 2026-08-21 riding the
substance-write-grain arc (#1113) — see `substance-write-grain.md`.

A fourth sibling — the LP recommendation backend methods — was ruled *build, not now* and
stays live in `../deferred-work.md` § LP Recommendation Backend Methods.

**This record exists for the residue notes and never-resurrect rulings each item carries**,
not as a status report. Nothing below remains open.

### A. ✅ CLOSED — The `DomainConfig` string chain (2026-08-20)

Re-running the census (as this register demanded) **falsified the item's
premise**: the chain was not merely string-typed — it was **severed**. Commit
`76d64a0d1` (2026-01-31) deleted the per-class values (e.g. KU's
`_prerequisite_relationships = [RelationshipName.REQUIRES_KNOWLEDGE.value]`)
pointing at DomainConfig as successor, but `BaseService.__init__` synced only
`dto_class`/`model_class` — the relationship tuples were computed at every
factory call, validated in `__post_init__`, and read by nobody. Every service
saw the empty default; the mixin's `get_prerequisites`/`get_enables` silently
returned `[]`, `add_prerequisite` always refused, and PR #1102's conversion
chokepoint was unreachable. No live path was affected (PsService's caller
overrides with its graph service; the lateral routes hardcode their enums).
The enables half was deader still: `_enables_relationships` had zero readers,
and the ruled `get_enables` design (KEEP, 2026-07-25) walks prerequisite edges
inward — nothing staged consumed it.

**Mike's rulings (2026-08-20):** reconnect + type the prerequisite chain;
delete the service-side enables plumbing. Executed: `DomainConfig
.prerequisite_relationships` is `tuple[RelationshipName, ...]`,
`BaseService.__init__` syncs it onto the instance (like `_dto_class`), both
mixins and the `prerequisite_traversal` / `prerequisite_chain_with_distance`
port+adapter carry enums (`.value` happens once, in the adapter, where enums
become Cypher edge patterns), the #1102 chokepoint is retired, and
`generate_enables_relationships` + `DomainConfig.enables_relationships` +
`_enables_relationships` are deleted (registry-side
`enables_relationship_names` stays — the graph contract reads it).
A regression test now pins the `__init__` sync.
Known residue (Codex on the PR, measured): the mixin's typed
`get_prerequisites` matches the domain label, so a curriculum domain's
Ku-typed prerequisites are silently excluded from that read — heterogeneous
chains belong to `prerequisite_chain_with_distance` (base-label match,
projected rows), which is what PsService's live path uses. Whoever wires the
PLANNED mixin consumers must pick the read accordingly.

### B. ✅ CLOSED — The `PsOperations` layering contradiction (2026-08-20)

Mike's hypothesis ("PsOperations is the backend protocol") was **confirmed by
census**, and the dual-layer doctrine it contradicted turned out to be drifted
fiction with a single, datable origin.

**Measured.** `PsOperations` declares 142 public callables. `PsBackend`
satisfies it; `PsService` implements **8**, diverges on 15, and is **missing
119** — including `execute_query`, `find_by`, `create_step_node`,
`faceted_search_raw`. Consumer census found **7** annotation sites, not the 5
this register claimed: six are backend handles (the factory's five plus
`PsAIService`, built outside it), all satisfied. The seventh —
`EntityExtractor.knowledge_service`, the "facade holder" the whole doctrine
rested on — called exactly **one** method (`get`) and arrived via
`AskesisDeps.knowledge_service: Any`, so its 142-member claim had never been
type-checked. Its four sibling params (`TasksOperations`, `GoalsOperations`,
`HabitsOperations`, `EventsOperations`) failed the identical probe: the
constructor was a uniform five-site instance of the trap, not a PS quirk.

**Provenance.** `git log -S "service-facing"` returns one commit: `862dafea4`
(PR #826, 2026-07-26). Commit 2 of that PR made `PsOperations` inherit the
backend slice; commit 3 reverted it on a Codex P1 whose rationale was the
dual-layer story — while that same commit message's own verification line
records "`EntityExtractor` never calls the ORGANIZES methods at all". The
revert accepted a remedy its own measurement falsifies. Every downstream
statement (the seam comment, the module docstring, `PsProgressBackendOperations`'
docstring, `BACKEND_OPERATIONS_ISP.md`'s "live example") descends from it.

**The un-composability constraint was real but irrelevant.** Re-verified: the
multiple-inheritance probe is still rejected — by the extra optional `limit`
param, *not* the `entity_uid`/`parent_uid` rename (mypy does not enforce
protocol parameter names at all under this config, so that divergence guarded
nothing). Composition was never the tool: **inheritance has no conflict,
because there is only one definition.**

**Executed.** All five `EntityExtractor` params type against `EntityLookup`,
promoted from `context_retriever.py` into `core/services/askesis/types.py`
alongside `KuLookup` (deleting the duplicate private `_EntityLookup`).
`PsOperations` inherits `PsOrganizesBackendOperations` **and**
`PsProgressBackendOperations` (Mike's ruling: take the progress slice too), so
both sets of signatures have one source; its 8 duplicate declarations are
deleted. `create_ps_sub_services(backend=)` **and** `PsService.__init__(backend=)`
are typed `PsOperations`; the `# boundary: ps-two-layer-divergence` comment is
gone. Naming: Mike ruled **state the layer, don't rename** — `KuOperations` /
`PsOperations` / `LpOperations` are all backend protocols wearing the
route-facing suffix, and renaming only PS would invent a new asymmetry. The
trio-wide rename stays an open naming question, deliberately untaken.

⚠️ **Typing the laundered handle found a real hole:** the moment the param
stopped being `Any`, mypy surfaced `PsService.attach_step_to_path` calling
`self.repo.get_next_step_sequence(...)` — a method `PsBackend` has always
implemented and the port had never declared. Now declared (cf. #1094).

### C. ✅ CLOSED — The lying `ku_backend` fixture (2026-08-21, with its vehicle)

`tests/integration/test_event_ku_practice_flow.py:61` — a fixture **named**
`ku_backend` that constructed a `PsBackend`. Ruled a rider, not a PR; closed
riding the substance-write-grain arc, exactly as scheduled — and riding it
mattered for the reason predicted: the arc's ruling (grain-agnostic, rename to
`knowledge_uid`) decided what the fixture should say. Executed: the fixture is
`ps_backend` (named for what it constructs), the seeded PathSteps carry honest
`ps.`-form uids instead of `ku.`-spelled ones, and a real `KuBackend`-backed
fixture now exists in the same file for the new grain-contract tests — so
`ku_backend` there means a Ku backend again.

