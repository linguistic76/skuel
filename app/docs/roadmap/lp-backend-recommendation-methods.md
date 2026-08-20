# LP intelligence: two backend methods that were never built

**Status:** RULED — *build, but not now* (Mike, 2026-08-20; **confirmed
2026-08-20 after the ZPD investigation below**, with the investigator's
delete recommendation on the table — build wins). Registered in
[`deferred-work.md`](deferred-work.md) § LP Recommendation Backend Methods;
trigger = Mike schedules it.
**Blocked by:** the stabilize-and-content phase directive. This is feature work.
**Found by:** Scope C backend-handle typing (#1099)
**ZPD investigation:** done 2026-08-20 (PR #1103) — see § Has ZPD absorbed this?

## What is missing

Two methods are **called** by LP intelligence and **defined nowhere in the repo**:

| Caller | Method called | Handle |
|---|---|---|
| `core/services/lp_intelligence/learning_recommendation_engine.py` | `find_paths_for_user(user_uid, user_context)` | `learning_backend` |
| `core/services/lp_intelligence/learning_state_analyzer.py` | `get_user_progress_summary(user_uid)` | `progress_backend` |

`git log -S` traces both call sites to the initial commit, with no definition
ever present. They are **never-wired**, not orphaned — nothing was deleted out
from under them.

## What that costs today

Both calls raise `AttributeError`, and both are inside
`except (ValueError, TypeError, AttributeError, KeyError)` blocks that log
*"backend unavailable"*. So:

- `LpIntelligenceService.recommend_learning_paths(...)` **always returns
  `Result.ok([])`** — the whole path-recommendation feature is inert.
- `LearningStateAnalyzer._get_progress_summary(...)` **always returns `None`**.

The log line makes a coding defect read as a configuration or outage problem.
That is the failure class recorded in `docs/technical_debt/
RETURN_VALUE_ERRORS_ANALYSIS.md` — error handling that makes a defect look like
an outage.

## Why the handles stay untyped until this is decided

`learning_backend` and `progress_backend` (analyzer), plus
`LpIntelligenceService.progress_backend` which only forwards to the analyzer,
are deliberately left `Any | None` with the reason in a comment at each site.
Typing them against a real protocol turns the phantom call into a mypy error
whose only honest fix is to build the method — which is this decision, not a
retype. Scope C closed at 3 handles for exactly this reason.

**Do not "fix" those three by deleting the call branches.** That deletes the only
surviving marker of an intended feature, and deletion was explicitly ruled out.

## Has ZPD absorbed this? (investigated 2026-08-20)

**Verdict: No — and by design it never will. Coverage of the *function* is
partial and conditional, and the gap is precisely nameable.**

ZPD never names a LearningPath:

- Every `ZPDAction` from `_build_recommended_actions` is Ku-keyed
  (`entity_type="path_step"`, `ku_uid` set; three types: learn / reinforce /
  unblock). Nothing ranks or recommends an LP as a unit.
- `ZPDAssessment.engaged_paths` (LP UIDs partially traversed) is descriptive
  input; no consumer outside the ZPD files reads it at all.
- The zone stays Ku-grain by explicit ruling (the PS-enabler bridge rolls
  PathSteps down to their composed Kus). The design doc scopes it: *"It does
  not recommend content directly (Askesis does that, using ZPDAssessment as
  input)"* — `docs/roadmap/done/zpd-service-architecture.md` § What ZPDService
  Does NOT Do.
- Askesis disclaims the feature's shape outright: *"not a recommendation
  engine"*, *"not a news feed"*
  (`ASKESIS_PEDAGOGICAL_ARCHITECTURE.md` § 1, § 10).

**What IS covered (the partial part):**

- The phantom's only wired trigger — next-path guidance after
  `LearningPathCompleted` — is *conditionally* served at Ku grain, and the
  condition matters (measured; Codex finding on PR #1103): ZPD's current zone
  is built from engagement edges only (Task/UserEntry `APPLIES_KNOWLEDGE`,
  Habit `REINFORCES_KNOWLEDGE` — `zpd_backend.py`); it reads neither
  `MASTERED` nor path completion, while LP completion itself is computed from
  `(User)-[:MASTERED]->(Ku)` (`_lp_progress_mixin.py`). In the normal learning
  loop the same work that earns mastery also lays engagement edges, and
  proximal expansion then crosses path boundaries via PREREQUISITE_FOR /
  ENABLES / COMPLEMENTARY_TO, pulling the learner into adjacent territory
  without any LP being named. But a learner whose mastered Kus lack activity
  edges gets no onward pull — coverage is mediated by engagement, not
  guaranteed by completion.
- Step-grain, state-keyed recommendation is live and real:
  `UserContextIntelligence.get_optimal_next_path_steps()` (ZPD as primary
  signal) and `LpIntelligenceService.get_recommended_path_steps()`
  (backend-implemented with typed rows — NOT a phantom).
- Whole-LP ranking exists, live, on a different key:
  `LifePathVisionService.recommend_learning_paths(themes)` — reachable via
  `POST /api/lifepath/vision` → `LifePathService.capture_and_recommend` —
  matches vision themes against LP search and returns frozen
  `LpRecommendation` rows. Path *choice* in the product today is
  vision-anchored (capture → recommend → designate), deliberately not
  state-keyed. ⚠ Same method name, different service, different capability —
  do not conflate the two.

**The gap (what nothing does):** rank whole LearningPaths by *learning state*
(readiness / mastery). ZPD holds the state; nothing maps it to LP units.

**New evidence the *build, but not now* ruling did not have — the feature is
dead ABOVE as well as below:**

- `LpIntelligenceService.recommend_learning_paths` has **zero callers** — no
  route, no UI, no other service (verified across `adapters/inbound/`, `ui/`,
  `core/`).
- The only runtime entry is the wired event handler
  (`services_bootstrap/_event_wiring.py` subscribes
  `handle_learning_path_completed`) — and the event it publishes,
  `LearningRecommendationGenerated`, has **zero subscribers**. Its sole
  publishers are this engine's two handlers. The bloat scan files it as INFO
  ("published but no subscriber — fine if fire-and-forget"), but it is a
  delivery mechanism, not telemetry.
- The sibling handler `handle_knowledge_mastered` is itself a stub — it always
  publishes an empty `recommended_ku_uids: []` behind a "Placeholder" comment.
- Grain confusion inside the flow: the LP-completion handler puts LP UIDs into
  the event's `recommended_ku_uids` field.

**Consequence:** building `find_paths_for_user` alone would light up a chain
that terminates in an unsubscribed event — recommendations no user can see.
An honest build includes a consumer surface, which makes this a full feature,
squarely parked by the phase directive.

## What building it means

1. **Contract: neither existing shape survives — decided on the core-domain
   norm, not on local precedent.** ⚠ Measured (Codex finding on PR #1103):
   the existing recommendation types are NOT uniformly frozen —
   `LpRecommendation` is `@dataclass(frozen=True)`, but `ContentRecommendation`
   is a mutable `@dataclass` (`core/services/lp_intelligence/types.py`) and
   `LpRecommendedStep` is a `TypedDict` (`core/ports/query_types.py`); the
   engine docstring's "Returns frozen dataclasses for recommendations" is
   itself fiction. The justification for a frozen contract is the core-domain
   norm (Type System: frozen dataclasses at the core; `Entity` itself is
   frozen) plus the one live LP-recommendation precedent (`LpRecommendation`).
   On that basis the `LP_INTELLIGENCE.md` § "Method 3" **dict** spec loses,
   and the caller's mutation (`rec.path.tags`, `rec.relevance_score *= 1.5`,
   `rec.reason = ...`) gets rewritten to recompute-and-rebuild
   (`dataclasses.replace`), not mutate. Build a frozen path-recommendation
   dataclass with a flat `lp_uid` (no nested mutable `.path`).
   `get_user_progress_summary` wants whatever `ProgressSummary` is.
2. Declare them on the right ports — `find_paths_for_user` on `LpOperations`
   (at runtime `learning_backend` IS the LP backend:
   `LpIntelligenceService.__init__` passes `self.backend`), and
   `get_user_progress_summary` on `UserProgressBackendOperations` (which
   currently declares 13 methods, none of them this one).
3. Implement in `adapters/persistence/neo4j/`, with typed rows per
   `BACKEND_OPERATIONS_ISP.md § "A New Port Declares Typed Rows"`.
4. **Build a consumer** — a UI surface (e.g. a "recommended paths" section) or
   a real subscriber to `LearningRecommendationGenerated`. Without one the
   build is inert by construction (see the investigation above).
5. Reconcile the naming collision with
   `LifePathVisionService.recommend_learning_paths` — two same-named methods
   answering different questions on different keys is the same-root-word trap.
6. Type the three handles, delete their explanatory comments, and delete this doc.
7. Re-run the Scope C census — it should reach 0.

## What deleting it means

Honest scope — larger than this doc previously recorded: the two dead call
branches + the three handle comments + `LP_INTELLIGENCE.md` § Method 3's spec
(marked superseded or removed), **plus the rest of the dead constellation**:
both event handlers (`handle_learning_path_completed` and the placeholder stub
`handle_knowledge_mastered`), their two subscriptions in
`services_bootstrap/_event_wiring.py`, `LearningRecommendationGenerated`
itself (these handlers are its only publishers), and
`tests/integration/test_lp_recommendations_flow.py`. This doc then moves to
`docs/roadmap/done/` carrying the ruling. The census reaches 0 the same way.

⚠ Adjacent but OUT of this decision's scope: `analyze_learning_state`,
`recommend_content`, `detect_interventions`, and `optimize_learning_session`
also have zero callers outside the sub-service constellation — the
`LearningStateAnalyzer` / `LearningRecommendationEngine` surface is largely
unconsumed. That is a separate, larger question; flagged here, not scoped.

## Recommendation on record (investigator, 2026-08-20)

**Delete.** The gap — state-keyed whole-LP ranking — is real but unhoused:
nothing would display it, and the product's live path-choice surface is
deliberately vision-anchored. If the gap is ever wanted, it is better specced
fresh as a feature WITH a consumer than kept alive as three `Any` handles
guarding branches that swallow AttributeErrors. The intent survives in this
doc (moved to `done/`) either way. Mike decides — ZPD absorption alone did
not turn out to be the discriminator, so the delete-on-absorption authorization
from the prior ruling does not fire on its own.

**→ Decided (Mike, 2026-08-20): build, but not now.** The recommendation above
was considered and not taken — the gap is wanted, so the feature stays a
deferred build, registered in [`deferred-work.md`](deferred-work.md) § LP
Recommendation Backend Methods. The three handles and their comments remain
the in-code markers until the build is scheduled.
