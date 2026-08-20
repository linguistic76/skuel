# LP intelligence: two backend methods that were never built

**Status:** OPEN — ruled *build, but not now* (Mike, 2026-08-20)
**Blocked by:** the stabilize-and-content phase directive. This is feature work.
**Found by:** Scope C backend-handle typing (#1099)

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

## What building it means

1. **Reconcile the two contracts that already exist and disagree.**
   `docs/intelligence/LP_INTELLIGENCE.md` § "Method 3" documents a return shape
   for this feature — a list of **dicts** with `path_uid`, `title`,
   `relevance_score`, `estimated_weeks`, `prerequisites_met`, `step_count`,
   `reason`. The **caller** wants something else: the engine does `rec.path.tags`,
   `rec.relevance_score *= 1.5` and `rec.reason = ...` — attribute access on an
   object with a nested `.path`, and a *mutable* relevance score it re-weights
   before re-sorting. Neither is authoritative yet. Pick one deliberately; do not
   discover the mismatch halfway through implementing.
   `get_user_progress_summary` wants whatever `ProgressSummary` is.
2. Declare them on the right ports — `LpOperations` and
   `UserProgressBackendOperations` respectively. Note the latter currently
   declares 13 methods and none of them is this one.
3. Implement in `adapters/persistence/neo4j/`, with typed rows per
   `BACKEND_OPERATIONS_ISP.md § "A New Port Declares Typed Rows"`.
4. Type the three handles, delete their explanatory comments, and delete this doc.
5. Re-run the Scope C census — it should reach 0.

## Prior art worth reading first

`ZPDService` already answers "what should this learner do next?" and is the
pedagogical gravity well (`docs/architecture/ASKESIS_PEDAGOGICAL_ARCHITECTURE.md`).
**Check whether path recommendation is genuinely a separate capability or whether
ZPD has since absorbed it** — if the latter, the honest outcome is to delete the
two features rather than build them, and that is a different ruling from the one
on record.
