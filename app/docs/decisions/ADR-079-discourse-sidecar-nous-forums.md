---
updated: 2026-07-16
---

# ADR-079: Discourse Sidecar for NOUS Community Forums (Staged)

**Status:** Proposed — **staged, not scheduled.** This is a choices-doc written ahead of need
(per the "write the choices-doc before big builds" working agreement) so the design is ready
when the community-scale trigger arrives (§ *Activation trigger*). No code, no container, no
roadmap slot yet.
**Date:** 2026-07-16
**Deciders:** Mike
**Related:** ADR-052 (Firefly III — the sidecar precedent this follows), ADR-044 (Neo4j as
committed architectural choice — forum data stays OUT of the graph), ADR-070 Decision 9
(human-initiated sync, no background watchers — the reconciler cadence model),
`docs/architecture/SEARCH_ARCHITECTURE.md` (NOUS topic/sub-topic semantics, #642–#644).

---

## Context

SKUEL's curriculum is organized under **NOUS topics** (the `nous` field on Ku, surfaced through
`KuService.list_nous_topics()` — a dynamic distinct-values query, not a hardcoded enum). As the
user base grows past founder-plus-small-groups, each NOUS topic is a natural gathering place:
learners working the same topic should be able to discuss it with each other, not only with the
Askesis companion.

SKUEL's **Leverage Maintained Software** principle says we do not build what mature open-source
software already does well — Firefly III owns finance (ADR-052), Prometheus/Grafana own
observability. Forum software is a textbook case: moderation tooling, trust levels, notification
digests, spam defense, and threading represent years of hard-won product work we should not
reimplement.

**Name disambiguation, recorded so it is never relitigated:** the product evaluated here is
**Discourse** (open-source GPLv2 forum software; runs forum.obsidian.md, meta.discourse.org, the
Rust and Docker forums). **Disqus** — one letter away — is a proprietary, ad-monetized embedded
comment widget with a tracking-heavy business model. Disqus is not forum software and is
rejected outright (§ *Alternatives*).

Constraints that shape the design:

- SKUEL is Neo4j-only by commitment (ADR-044). A forum brings PostgreSQL + Redis; that stack
  must stay behind a service boundary SKUEL never reaches into.
- Users must not manage a second account. SKUEL's graph-native auth is the identity source.
- NOUS topics are data, not schema — the topic list changes as content is authored, so forum
  structure must follow the graph, not be hand-maintained.
- Entity independence: no machinery coupling between forum plumbing and domain entities.
  Forum mapping is infrastructure configuration, never a field on Ku or a new EntityType.

## Decision (proposed shape)

Run **Discourse as a sidecar**, integrated over HTTP only — the Firefly III pattern exactly.

1. **Deployment: sidecar, own stack.** Discourse ships its own `discourse_docker` launcher
   (Rails + PostgreSQL + Redis) and does not fit vanilla docker-compose. It runs *beside*
   SKUEL's compose stack as an independent service, like Firefly. SKUEL never touches its
   database — HTTP API and SSO handshake only. Sizing floor: 2 GB RAM + swap (4 GB
   recommended), 2 cores, 20 GB disk, and a **working SMTP relay** (a hard Discourse
   requirement SKUEL does not currently have — part of the activation cost, not the decision).

2. **Identity: DiscourseConnect, SKUEL as the identity provider.** Discourse outsources ALL
   registration and login to SKUEL via DiscourseConnect (HMAC-SHA256 signed payload against a
   shared secret). One account, SKUEL's. Role mapping at SSO time: ADMIN → Discourse admin,
   TEACHER → moderator/group membership, MEMBER/REGISTERED → regular user. Suspending a SKUEL
   user locks them out of the forum for free.

3. **Structure: one Discourse category per NOUS topic, reconciler-synced.** An idempotent
   reconciler reads `list_nous_topics()` and creates/renames matching Discourse categories via
   the admin API. `nous_subtopic` values may become Discourse **tags** within the category
   (co-occurrence semantics per #644 — sub-topics are not a hierarchy, so tags fit better than
   sub-categories). Sync is **human-initiated** (admin button / `./dev` command), matching the
   ADR-070 Decision 9 no-background-watcher stance. Deletion is deliberately asymmetric: a NOUS
   topic disappearing from the graph flags the category for manual archive — the reconciler
   never destroys community writing.

4. **Surface: embedded, plus a plain link.** Discourse's JavaScript embedding renders a topic's
   comment stream in an iframe on external pages — a "Discussion" section on Ku/PathStep detail
   pages, with topic-list embeds for a NOUS topic's recent activity. Known constraint: a
   Discourse topic's `embed_url` is **fixed at creation** and cannot be changed via the API, so
   embeds must key off stable SKUEL URLs (the dot-normalized UIDs are stable; the URL scheme in
   front of them must be treated as frozen once embedding starts). Where embedding is more
   trouble than it is worth, a plain "Discuss on the forum →" link is the honest fallback.

5. **Boundary: a port in `core/ports/`, an adapter in `adapters/external/discourse/`.**
   `DiscourseOperations` (category CRUD, SSO payload verification/signing) implemented by a
   REST client — the same shape as `firefly_client`. The NOUS-topic → category-id mapping lives
   in the adapter's own storage or config, **not** on Ku nodes and not as graph edges. Forum
   posts are NOT entities: no EntityType, no ingestion, no embeddings, no search-router domain.
   If forum content ever deserves graph presence, that is a new ADR.

## Alternatives considered

- **Disqus** — rejected. Proprietary comment widget, ad/tracking business model, not a forum,
  not open source. Named here only because the similarity to "Discourse" invites confusion.
- **NodeBB** (Node.js + MongoDB, real-time chat feel) and **Flarum** (PHP, lightest ops) —
  credible open-source rivals, both cheaper to run. Rejected because neither matches the
  DiscourseConnect + admin API + embedding maturity that this integration leans on, and
  Discourse's moderation/trust-level system is best-in-class for the healthy-community goal.
  Flarum in particular gates SSO and moderation depth behind paid/third-party extensions.
- **giscus / GitHub Discussions** — rejected. Requires public GitHub identity and repository
  coupling; SKUEL's community is not a public GitHub audience, and the content↔repo boundary
  keeps community content away from the public repo.
- **Build a forum inside SKUEL** — rejected on principle. Threading, moderation queues, spam
  defense, digests, and trust systems are exactly the "already available, actively maintained"
  category the leverage principle exists for.

## Consequences

**Positive**
- ✅ Community discussion per NOUS topic with zero forum-feature development or maintenance.
- ✅ One identity (SKUEL's), one login, role mapping for free via DiscourseConnect.
- ✅ Forum structure follows the graph automatically through the reconciler.
- ✅ Clean blast radius: the sidecar can be paused, resized, or removed without touching SKUEL.

**Negative**
- ⚠️ A second stack to operate: Rails + PostgreSQL + Redis, its own launcher, periodic rebuilds
  (~1.5 GB headroom or swap during rebuild), roughly 4 GB RAM in practice.
- ⚠️ SMTP becomes a hard dependency for the first time (Discourse cannot run without it).
- ⚠️ A second backup surface (Discourse's Postgres + uploads), outside SKUEL's Neo4j story.
- ⚠️ `embed_url` immutability freezes the embedded pages' URL scheme.

**Risks**

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Empty-room effect (categories with no posts) | High at first | Medium — deadens the feature | Activation trigger below; launch with few topics, split later |
| SSO secret leak = account takeover on forum | Low | High | Secret via `get_credential()`, rotate on suspicion; forum holds no SKUEL data |
| Discourse upgrade breaks embed/SSO surface | Low | Medium | Both are core Discourse features (stable for a decade); pin + test on bump |
| NOUS rename orphans a category | Medium | Low | Reconciler renames by stored category-id mapping, never by string match |

## Activation trigger

Build this when **community scale is real, not projected** — concretely, when there are
multiple active non-founder cohorts (groups working NOUS topics under teachers) and
discussion is being forced into channels that don't fit (journal entries addressed to peers,
teacher-relay questions). Until then this ADR is inventory, not backlog: the empty-room effect
at current scale would cost credibility that is hard to win back.

At activation, the prerequisites are: SMTP provider choice, host sizing (or a separate small
droplet for the sidecar), a moderation policy (who wields TEACHER→moderator power), and a
privacy pass (forum usernames/display names are visible to other members — confirm what SSO
sends is what users expect to be public).

## When to revisit

- If SKUEL's community model changes (e.g., fully private 1:1 teaching, no peer visibility),
  the forum premise dissolves — retire this ADR rather than force it.
- If Discourse licensing/governance shifts materially, re-run the NodeBB/Flarum comparison.
- If forum content ever needs to feed learning intelligence (search, ZPD, grounding), STOP —
  that crosses the "posts are not entities" line and requires a new ADR with a privacy design.
