---
title: "AI Tier Consumer — the routed AI features wait for their first UI surface"
updated: 2026-10-01
status: "staged — the tier is repaired and routed (34 POST routes over 8 services), and nothing in the repo calls any of them"
registered: 2026-09-29
ruled: 2026-09-29
trigger: "the first UI surface that calls an AI route"
check: "git grep -n '/ai/' -- ui static — a hit outside a comment is the consumer; the PLANNED entries for PsAIService.search_by_semantic_query / suggest_step_applications / suggest_learning_sequence (and their PsService delegations) retire when a spec routes them"
---

# AI Tier Consumer — the routed AI features wait for their first UI surface

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

## What the tier is

The AI tier is the eight `BaseAIService` subclasses (`core/services/base_ai_service.py`;
six Activity, `PsAIService`, `LpAIService`) that `services_bootstrap/_ai_wiring.py` sets on
each facade's `.ai` slot when `INTELLIGENCE_TIER=full` and the LLM, embeddings and vector
search services are all built ([ADR-043](../decisions/ADR-043-intelligence-tier-toggle.md)).
Its one HTTP door is `adapters/inbound/ai_routes.py`: one `POST /api/{domain}/ai/{action}`
per `AIRouteSpec`, CSRF-protected, behind the auth, availability, tier, ownership and daily
LLM-quota gates, plus `GET /api/ai/status`. The reference is the
[base-ai-service skill](../../.claude/skills/base-ai-service/SKILL.md).

## What waits

**Nothing in the repository calls an AI route.** No file under `ui/` or `static/` names
`/api/*/ai/*` or `/api/ai/status` (the `check:` above), and the three `PsAIService` methods
without a spec — `search_by_semantic_query`, `suggest_step_applications`,
`suggest_learning_sequence` — and their `PsService` delegations have no caller either.
The tier has gates, tests and an ADR, and no consumer.

**Ruling (2026-09-29): keep and repair — the tier is staged, not abandoned.** It is
registered as visible backlog by this file and its `deferred-work.md` heading; `./dev bloat`
is deliberately not extended to routes. The three unrouted `PsAIService` methods and their
delegations are `PLANNED_METHODS` entries in `scripts/detect_bloat.py`, `DELAYED`,
`blocked_by` this file's heading — the detector does not find them on its own because the
facade loads them by name.

The trigger is a UI surface that calls one of the routes: a page or fragment that asks for a
task insight, a similar-goals list, a step explanation. When it lands, the routes it calls are
live, the consumer-less status here changes, and any method it needs that is still unrouted
gets its `AIRouteSpec` and loses its PLANNED entry.

## What the repair fixed (so the trigger finds a working tier)

The two shared helpers now match the services they are wired to: `_generate_insight` returns
the response's text and fails on a set `error`; `_rank_similar_entities` ranks the stored
vectors of an owner-scoped pool, and curriculum similarity goes through the draft-gated vector
index (`rank_similar_curriculum`). The base is typed (`LLMService | None`,
`EmbeddingsService | None`).

The routes: the six specs that named methods no service had are deleted (the whole
`knowledge/ai/*` prefix among them — a PathStep surface under a legacy segment, so no AI
route carries a `knowledge` segment); every spec whose method does not return a dict has a
`wrap_key` and every success is JSON; a failed `Result` answers the boundary's status for its
category with the client-safe error dict; the routes are `POST` only with `@csrf_protected`;
a spec whose `method_name` does not resolve on its AI class is refused at registration
(`create_ai_routes` raises at boot, in both tiers).

## Still open beside the trigger

- ~~`_SearchMixin.search`~~ — ruled 2026-09-30: deleted, with its `EntitySearchOperations`
  declaration (the mixin's case-sensitive `CONTAINS` had no production caller once
  `search_by_semantic_query` lost its keyword fallback; the service layer's `search` reads
  `text_search_raw`, still declared on `EntitySearchOperations`).
- **A draft uid as the *source* of a curriculum AI call.** The similarity listings gate
  drafts at the read; `insight` / `explain` / `practice` / `overview` / `strategy` and a
  similarity call *about* a draft uid read the uid they are given, under the standing by-uid
  rule (a by-uid read is deliberately ungated). Whether a `SHARED` AI spec should refuse a
  draft source is open.
- **The Activity similarity pools** are the owner's whole set — `find_all_by(…, user_uid=…)`
  (`core/services/whole_set_read.py`), up to `QueryLimit.MAXIMUM` rows — read and ranked in
  Python on each call. A vector query with a limit is the shape that scales
  (`TODO(blocked:embeddings)` in `tasks_ai_service.py`).
- **Prompt input is unbounded** — the `generate_*_insight` methods pass `description` whole,
  and the request models set no `max_length` on it.
