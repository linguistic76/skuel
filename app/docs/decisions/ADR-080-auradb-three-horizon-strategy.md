---
title: "ADR-080: AuraDB Three-Horizon Strategy & GDS Deferral"
updated: 2026-07-22
status: accepted
category: decisions
tags: [adr, decisions, neo4j, auradb, graph-data-science, infrastructure]
related: [ADR-043, ADR-044, ADR-067, ADR-068]
related_skills: [neo4j-cypher-patterns]
---

# ADR-080: AuraDB Three-Horizon Strategy & GDS Deferral

**Status:** Accepted — the *direction* is committed (move to AuraDB Free soon; Neo4j Graph Data
Science deliberately deferred). **Horizon 2 (GDS/AuraDS) is staged, not scheduled** — a choices-doc
written ahead of need per the "write the choices-doc before big builds" working agreement, so the
pathway is clear the day content density makes it pay off.

**Date:** 2026-07-22

**Deciders:** Mike

**Related:** ADR-044 (Neo4j as a committed architectural choice — the graph is not swappable),
ADR-043 (intelligence-tier toggle — GDS is a **Digital-layer** enhancer, next to embeddings/LLM),
ADR-068 (OpenAI-now-BGE-later — the same "commit long-term, adopt the enhancement when justified"
shape), ADR-067 (dependency/version policy — home of the `AURA-TEMPORARY` self-host knobs).
Cross-refs: `docs/architecture/ANALOG_DIGITAL_ARCHITECTURE.md`,
`docs/architecture/GRACEFUL_DEGRADATION_ARCHITECTURE.md`,
`docs/deployment/AURADB_MIGRATION_GUIDE.md`, `docs/deployment/DO_MIGRATION_GUIDE.md`,
`docs/patterns/NEO4J_SERVER_TUNING.md`.

---

## Context

SKUEL is committed to **AuraDB** long-term. This follows the **Leverage Maintained Software**
principle (ADR-052 Firefly, Prometheus/Grafana): we do not run infrastructure that a managed service
runs better. We want to move to **AuraDB Free soon** while content is still being refined — accepting
that some capabilities are *willingly absent* from the current installment, provided the pathway to
them is explicit.

The genuine Neo4j capability worth eventually leaning into is **Graph Data Science (GDS)** — the
graph-*algorithm* engine (pathfinding, centrality, community detection, structural similarity/
embeddings). It is almost tailor-made for SKUEL: shortest-path over the prerequisite DAG *is* the ZPD
"what should this learner do next?" question; centrality finds keystone Kus; community detection
surfaces emergent topics complementing hand-authored MOCs. The trap this ADR guards against is
**hand-rolling those algorithms** in bespoke Cypher/Python — which rebuilds GDS badly and violates
the Leverage principle.

Three facts shape the decision:

1. **AuraDB Free ≠ GDS.** GDS is a **separate paid product line, AuraDS** (verified 2026-07-22 against
   neo4j.com/pricing + the AuraDS support docs). Moving to Free does *not* hand us GDS, and GDS is *not*
   an argument for migrating to Free soon. The two are **different clocks.**
2. **GDS is a Digital-layer, volume-gated play.** In SKUEL's own terms (ADR-043) it sits on the
   **Digital layer** (`INTELLIGENCE_TIER=full`) — machine understanding layered on the Analog graph,
   not part of the $0 core. Every capability it would provide already has an **Analog fallback** that
   works today.
3. **Content is too sparse for GDS to say anything — and the gap is edges, not nodes.** Live-graph
   measurement (dev, 2026-07-22): knowledge subgraph = 121 Ku · 14 PathStep · 2 LP · 15 Exercise.
   Structural edges are sparse — `PREREQUISITE_FOR`=9, `DEPENDS_ON`≤1, `ORGANIZES`≤1 (MOC hierarchy
   essentially empty), `USES_KU`=53, lateral ~33. Ku **avg degree 2.17, 17 orphans (14%)**. GDS
   PageRank here would echo "which Kus a PathStep happens to use"; shortest-path over a 9-edge DAG is
   meaningless; communities around 17 orphans are degenerate.

The key insight that resolves the tension: **the edge-authoring that makes GDS meaningful later is the
same curriculum authoring that makes SKUEL a good learning app today.** A rich prerequisite DAG is a
better ZPD *now* (even heuristically) *and* the substrate GDS monetizes *later*. There is no premature
investment and no detour — GDS-readiness is a byproduct of building the product well.

## Decision

Model development as **three horizons on one graph.** ("The plant grows on the lattice"; GDS is what
reads the lattice once the plant has grown on it.)

**1. Horizon 0 — AuraDB Free readiness (near-term, finite).** Make the graph cap-safe and
managed-ready. Concretely: telemetry retention/TTL (AuthEvent/Session/SearchEvent/ConversationTurn/
Interaction/VIEWED are unbounded-growth and dwarf the curriculum — `HAD_AUTH_EVENT`=1089,
`HAS_SESSION`=431 today; Free is node-capped), and tolerance of a **paused/waking** instance
(Free auto-pauses on inactivity). Everything else already ports: embeddings are Python-side (ADR-068,
no server plugin), connection is a `.env` change, and the `AURA-TEMPORARY` knobs fall away.

**2. Horizon 1 — nurture the graph edge-first (ongoing, the real work).** Author the knowledge
subgraph for **density, typed relationships, and connectivity** — prerequisites, ORGANIZES/MOC links,
lateral relations, Ku composition. Instrument it with a **structural-health gauge** (degree
distribution, orphan Kus, DAG depth/coverage, ORGANIZES coverage, a composite readiness score). The
gauge is an *authoring guide today* (it flags the 17 orphan Kus and the near-empty DAG as content
gaps) and the *GDS-readiness signal* for Horizon 2 — measurable in plain Cypher, no GDS required.

**3. Horizon 2 — graduate to AuraDS and slot GDS behind a port (deferred; density-triggered).** When
the gauge shows the graph is dense enough **and** a concrete GDS-powered feature is worth the AuraDS
cost, GDS enters — each capability *enhancing* an existing Analog fallback, never replacing the
meaning layer. **GDS replaces the algorithm compute, not the meaning:** it gives PageRank; SKUEL still
owns what PageRank-over-Kus *means* for a learner (ZPD pedagogy, domain semantics, knowledge-substance
weighting). It does not touch CRUD/traversal Cypher (the store) or text-vector similarity (a
*complementary* lens — structural vs. semantic relatedness).

**4. The discipline (how the pathway stays clear).**
- **Don't hand-roll graph algorithms.** When tempted to write bespoke centrality/pathfinding/
  clustering Cypher, stop — mark it `# GDS-FUTURE:` and register it in `PLANNED_METHODS`
  (`scripts/detect_bloat.py`) as a visible, deferred-with-a-pathway item, then do the cheapest
  heuristic or defer the feature. This is the same "staged ≠ dead code" mechanism One-Path-Forward
  already uses.
- **Keep compute separated from meaning** — which SKUEL already does structurally (intelligence
  returns plans not view-shapes; analytics aggregate, don't create; ports/adapters, ADR-044). The seam
  mostly already exists; the discipline is to *not violate it* by inlining algorithm-compute into ZPD/
  meaning code.
- **Do NOT build a `GraphAlgorithmPort` abstraction now.** A port with zero current implementations and
  one hypothetical future one is speculative generality — exactly what One-Path-Forward rejects. The
  port is born at Horizon 2 alongside its first real adapter (bespoke or GDS), when its interface is
  actually knowable. Today the seam is *discipline + a marker*, not a construct.

**5. Two scaffolding conventions carry the "temporary/deferred" intent in the codebase.**
- `# AURA-TEMPORARY:` marks self-host-only knobs (heap/page-cache sizing, the JVM Vector-API/SIMD flag,
  the monthly version pin) that AuraDB provides by default and that disappear on migration. Checklist:
  `AURADB_MIGRATION_GUIDE.md § 6.2`; find them with `grep -rn AURA-TEMPORARY infrastructure/ app/`.
- `PLANNED_METHODS` / `PLANNED_EVENTS` register deferred GDS-shaped work as a visible backlog rather
  than dead code.

### Willingly-absent capabilities (deferred to Horizon 2, each with a present Analog fallback)

| GDS capability | What it would give SKUEL | Present Analog fallback (holds the floor) |
|---|---|---|
| Centrality / PageRank | keystone-knowledge ranking (structurally important Kus) | none today (accepted gap) |
| Shortest-path over the prerequisite DAG | optimal learning routes | heuristic ZPD "what next?" (UserContext + bespoke traversal) |
| Community detection (Louvain) | emergent topic clusters | hand-authored MOCs / `nous` taxonomy |
| Node similarity / FastRP·GraphSAGE | structural "related concepts" | text-vector (embedding) similarity — a complementary lens |

None of these is broken by GDS's absence; each is an *enhancement* of something that already works at
the Analog tier. That is why the absence is safe to **choose**.

## Alternatives Considered

### Alternative 1: Self-host GDS on a large droplet
**Description:** Run the GDS plugin ourselves on a memory-sized DigitalOcean droplet.
**Pros:** GDS available without AuraDS; no Free-tier limits.
**Cons:** GDS projections are memory-hungry; a modest droplet OOMs on non-trivial projections. Reintroduces exactly the operator burden (memory ops, tuning, upgrades) we are moving to managed hosting to escape.
**Why rejected:** Opposite of the Leverage-Maintained-Software direction; and pointless while content is too sparse for GDS to say anything.

### Alternative 2: Build bespoke graph-algorithms in-app
**Description:** Hand-write centrality/pathfinding/clustering in Cypher/Python inside SKUEL.
**Pros:** No dependency on AuraDS; works on any tier including Free.
**Cons:** Rebuilds — badly — a mature engine Neo4j already provides; couples algorithm-compute to the meaning layer; becomes debt we must delete when GDS arrives.
**Why rejected:** The central trap this ADR exists to prevent. Violates the Leverage principle.

### Alternative 3: Jump to AuraDS (paid GDS tier) now
**Description:** Skip Free; go straight to the data-science tier.
**Pros:** GDS available immediately.
**Cons:** Pays for an engine that has nothing to compute over at 121 Ku / 9-edge DAG; premature spend.
**Why rejected:** Density-gated, not calendar-gated. Revisit when the Horizon-1 gauge says so.

### Alternative 4: Stay self-hosted indefinitely
**Description:** Keep Docker/droplet Neo4j; never move to Aura.
**Pros:** Full server control; arbitrary plugins/flags.
**Cons:** Perpetual operator burden (version treadmill, memory tuning, backups) at a scale that does not need it; foregoes the managed benefits SKUEL is committed to.
**Why rejected:** Contradicts the standing AuraDB commitment; the control we'd keep is control we don't need at this scale.

## Consequences

### Positive
- ✅ A clear, honest headline: **AuraDB Free soon; GDS deliberately later; the thing that closes the gap to GDS is just authoring the curriculum graph well — which we'd do anyway.**
- ✅ No premature build: GDS stays out until content justifies it, with a marked pathway (no rebuilt-badly algorithm debt).
- ✅ The Horizon-1 gauge earns its keep in the present (authoring quality) independent of GDS.
- ✅ Clean mental model: GDS = another Digital-layer enhancer (ADR-043), Analog fallbacks hold the floor.

### Negative
- ⚠️ Some intelligence (keystone ranking, optimal routing, emergent clustering, structural similarity) is consciously **absent** until Horizon 2.
- ⚠️ A future Free→AuraDS graduation is a migration (dump/restore) — but within the managed Neo4j family, and the app code is unchanged (GDS calls are additive behind a port born at H2).

### Neutral
- ℹ️ The `AURA-TEMPORARY` knobs remain live while self-hosting; they simply drop on migration.
- ℹ️ Deep live-request connection resilience (reconnect/circuit-breaker across query sites) is deferred; Horizon 0 handles only the startup/waking case now.

### Risks & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Someone hand-rolls a graph algorithm, accreting debt | Medium | Medium | The discipline + `# GDS-FUTURE:` marker + `PLANNED_METHODS` review; this ADR is the reference |
| Telemetry growth breaches the Free node cap | Medium | High | Horizon-0 retention policy (cap-safety); measured by the Horizon-1 gauge |
| Content never reaches GDS-meaningful density | Medium | Low | Acceptable — Analog fallbacks hold the floor indefinitely; GDS is opt-in upside, not a dependency |
| Premature migration to Free before retention lands | Low | Medium | Horizon 0 is the gate; do retention first |

## When to Revisit (Horizon 2 activation trigger)

Reconsider the GDS deferral when **both** hold:

1. **Density threshold** (measured by the Horizon-1 structural-health instrument): the prerequisite DAG
   spans most Kus with real depth (not a 9-edge stub), Ku average degree climbs well above ~2 with
   orphans trending to ~0, and ORGANIZES/MOC coverage is populated — i.e. the gauge's readiness score
   crosses a set threshold.
2. **A concrete GDS-powered feature** is worth the AuraDS cost (e.g. keystone-Ku prioritization feeding
   ZPD, or optimal learning-route computation replacing the heuristic).

At that point: introduce the algorithm-compute **port with its first real adapter**, graduate Free →
AuraDS, and implement the willingly-absent capabilities one at a time — each still delegating meaning
(ZPD/semantics/interpretation) to SKUEL, with its Analog fallback retained as the CORE-tier path.

### Deferred within Horizon 0: deep live-request connection resilience

Horizon 0 (shipped) handles the **startup/waking** case only: `Neo4jAdapter.connect` retries the
initial connectivity probe with bounded exponential backoff (`connect_with_retry`; bounds in
`core/constants.py` `Neo4jConnectRetry`), so a paused/waking AuraDB Free instance no longer crashes
bootstrap. Telemetry retention (`./dev telemetry-retention`, one-shot) keeps the graph under the Free
node cap.

What is **deliberately not built** is **mid-request** resilience — reconnect / circuit-breaker across
the ~124 `session.run` query sites, so an in-flight request survives an instance that pauses under
active traffic. This is a *documented pathway, not dead code*: there is no method to register in
`PLANNED_METHODS` because the work is unbuilt (that mechanism tracks staged-but-unwired *methods*, and
inventing an empty symbol would trip SKUEL026 / the bloat auditor). Instead this note is the marker.

**Revisit it when** a managed instance is observed pausing under real traffic (Free auto-pauses on
*inactivity*, so an actively-used instance rarely does — hence the low present value), or when moving
off a tier whose pause behavior differs. The natural home if built: a thin retry/reconnect wrapper at
the driver/executor seam (`TimedDriver` / `Neo4jQueryExecutor`), where a single chokepoint already
exists — *not* 124 call-site edits.
