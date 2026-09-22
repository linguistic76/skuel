---
title: "Field-Name Guarding in Cypher — Which Guarantee, and Where"
updated: 2026-09-22
status: "ruled 2026-09-22 — one syntactic guard in the persistence layer; no HTTP route publishes a sort key; the named allowlist retired in favour of an enum-typed sort key; the five backend sites stay unguarded, deliberately"
registered: 2026-09-22
ruled: 2026-09-22
trigger: "the first caller that hands one of the five listed sites a value it did not author — a route parameter, a form field, or a **kwargs forward from a service whose caller is a route"
check: "grep -rn 'order_by' core/services/ps_service.py core/services/ps/ps_core_service.py adapters/inbound --include='*.py' — a route reaching PsService.list_steps' **kwargs, or any new HTTP handler declaring an order_by/sort parameter, fires this"
---

# Field-Name Guarding in Cypher — Which Guarantee, and Where

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

Neo4j cannot parameterize a property name, so every sort key and every property name in a
pattern is interpolated into query text. The persistence layer answered *"what guarantee do we
make about an interpolated property name?"* five different ways and, at a handful of sites, not
at all. This is the ruling on which guarantee belongs where — opened by
PR #1395, which deleted two consumer-less Cypher
validators and left this priced but untouched.

## The three guarantees, and why they are not interchangeable

| Guarantee | Mechanism | Answers |
|---|---|---|
| **Syntactic** | `validate_field_name` (`core/utils`, returns `bool`, ≤64 chars) / `validate_identifier` (`query/cypher/_helpers`, raises) | "is this string a safe identifier?" |
| **Model-derived** | membership in `fields(entity_class)` — every `crud_queries` builder | "is this a property on *this* entity?" |
| **Enum-typed** | the parameter's type — `NeoLabel`, `RelationshipName`, `ActivitySortKey` | "is this one of the names this call site may choose from?" |

`password_hash`, `embedding` and `email` pass the first and fail the other two. **A
consolidation that picks one mechanism for every site weakens the sites using a stronger one** —
which is why "collapse everything to one validator" was ruled out explicitly rather than
weighed.

## The measurement that decided it: `ORDER BY` is a disclosure oracle

Measured against the pinned kernel (`neo4j:2026.07.1`, testcontainer), not reasoned about:

| Probe | Result |
|---|---|
| `RETURN n.uid ORDER BY n.secret` — `secret` never projected | **permitted**; ASC returned exact secret-order, DESC its reverse, against a *different* control insertion order |
| `ORDER BY r.hidden`, relationship variable never returned | **permitted** — the `_relationship_ordered_mixin` shape works too |
| the same with `SKIP`/`LIMIT`, one row per request | **permitted** — a fully enumerable paginated oracle |
| `DISTINCT`, aggregation, or a `WITH` that drops the variable | **refused** — `CypherSyntaxError` |

**The bound:** `ORDER BY` runs after `WHERE`, so it cannot cross a visibility clause. It orders
rows the caller is already entitled to, by properties the *render* drops. So the oracle does not
make syntactic guarding *broken* — it makes it **incomplete in a nameable way**: sufficient
against injection, insufficient against property disclosure inside an already-authorized row
set. That distinction is the whole reason the ruling is "close the door" rather than "add
checks."

## What was ruled, and built

### One syntactic guard in the persistence layer, not two

`neo4j_schema_manager.py` carried private copies of `validate_label` **and** `validate_identifier`
— byte-identical bodies *and* error messages to `query/cypher/_helpers`' — behind its own copies
of the label frozenset and the identifier regex. `crud_queries.py` then imported the shared pair
under the `_`-prefixed spellings the schema manager used for its own, so **one identifier meant
two different functions depending on which module you were reading**. Both copies and both
aliases are gone; DDL and the read builders now refuse the same strings because it is one
function. Pinned by `TestPersistenceLayerSharesOneIdentifierGuard`.

`core/utils/validation_helpers.validate_field_name` stays where it is. Its `bool` contract is
different by design — its callers branch and drop, the adapter's callers raise — and collapsing
the two would mean rewriting control flow at every site to satisfy a cosmetic count.

### No HTTP route publishes a sort key

`GET /api/{domain}/list` accepted `?order_by=` and `?order_desc=` as free strings (FastHTML binds
them from the handler signature). That was the *only* live, user-controlled sort key in the
codebase, and the one the oracle above actually applies to. **No client ever sent it** — no JS,
no HTMX, no template, no test against the real handler. Both parameters are gone; the route takes
pagination only. Pinned by `TestListRouteExposesNoSortKey`.

Alongside it, `CrudOperationsMixin.list` now defaults its sort key on *both* branches instead of
only the user-scoped one. `limit`/`offset` there are a pagination window, and over an unordered
result Neo4j may return rows in a different order per call — so page 2 could repeat or skip a row
from page 1. Pinned by `TestListAlwaysCarriesASortKey`.

### `crud_queries` no longer contradicts itself

Three sort builders in that module checked `order_by` against the model and warned-and-dropped a
miss; the two array builders beside them interpolated both `order_by` **and** `field` with no
check at all. Same file, same parameter names, two policies. Both array builders now take
`entity_class` and use the model:

- `field` **raises** on a miss — it lands in the `WHERE`-clause pattern, where a silent drop
  would change *which rows match*, not only their order.
- `order_by` **warns and drops**, matching its three siblings.

### The named allowlist is retired; the sort key carries its own vocabulary

`_ALLOWED_ORDER_BY` — a 12-name frozenset in `_backend_helpers.py` — guarded two sites, and a
caller-supplied value reached neither.

- `_LpStepMixin.list_all_paths_with_steps`' `order_by`/`order_desc` were **consumer-less through
  the whole stack**. `lp_core_service.list_all_paths` forwarded them; its three callers
  (`LpService.list_all_paths`, `learning_paths_ui.py`, `pathways_orchestrator`) pass `limit` only,
  and the facade never declared the parameters at all. Both are gone from the backend, the
  service and both `LpOperations` declarations; the query is fixed at `ORDER BY p.uid ASC`, which
  is what it already emitted and what keeps successive `SKIP`/`LIMIT` pages disjoint.
- `_KnowledgeContextMixin.find_connected_activities`' `order_by` is reached only by
  `PsApplicationDiscoveryService`'s six in-file wrappers, which pass six literals — `start_time`,
  `created_at`, `due_date`, `target_date`, `created_at`, `strength`. Five distinct names, and the
  frozenset's other seven (`uid`, `updated_at`, `title`, `status`, `priority`, `completed_at`,
  `name`) were unreachable at both sites: the check could not fail.

So the mechanism was a guard over a value that does not vary — the class
PR #1395 deleted four gates for, and the same reason this
file already gives for operators and sort directions having no validator.

The parameter is load-bearing even though the frozenset was not: the six wrappers genuinely sort
six ways. It is now typed `ActivitySortKey` (`core/models/enums/activity_enums.py`), a five-member
`StrEnum`, and the membership check is gone. That **strengthens** the site rather than dropping to
the weaker syntactic guarantee: membership is now structural and mypy-checked at every call site
instead of a runtime frozenset a new caller could miss. It also makes one function internally
consistent — `node_label` is a `NeoLabel`, `rel_types` are `RelationshipName` values, and the sort
key was the lone raw `str` beside them.

Fixed while there: that function resolved its label as
`node_label.value if isinstance(node_label, NeoLabelEnum) else str(node_label)`. The `else` branch
interpolated any string verbatim into `MATCH (n:{label})`, defeating the declared `NeoLabel` type;
it is now `node_label.value`. Pinned by `TestActivitySortKeyIsTheAllowlist` and
`TestLearningPathCatalogueExposesNoSortKey`.

### `LpService.list()` is deleted, not migrated

The parameters that survived the route were a symptom: the *method* had no production caller.

`CrudOperationsMixin.list` accepts `order_by`/`order_desc` as documented aliases of
`sort_by`/`sort_order`, and they are live — `teaching_forms_ui.py` passes literals through them.
`LpService` never inherited that: it is a plain facade with no `BaseService` in its MRO, and it
*reimplemented* `list()` with a Python-side `sorted()` over a truncated fetch. Its docstring called
it "CRUDRouteFactory compatible", but `PATHWAYS_CONFIG` declares no `crud=` — LP wires a manual
`api_factory`. No route, service or UI file called it; its only callers were six tests written to
exercise it.

Behind those tests it had accrued three defects, none of them reachable: it sorted *after*
truncating to `limit + offset`, so `order_by` returned the sorted top of an arbitrary window rather
than the true top-N; the `user_uid` branch dropped `offset` entirely; and a bare
`except (AttributeError, TypeError): pass` silently skipped sorting on an unknown key. The same shape as
`OwnershipRouteFactory`, which sat registered nowhere while its eight tests passed
([done/docs-defiction-pass.md](done/docs-defiction-pass.md), PR 3): a consumer-less mechanism
accrues defects its own tests cannot see.

Migrating it would have meant restructuring LP into a `BaseService` to serve a method nothing
calls, so the method and its six tests are gone. The two sibling shims beside it are *not* the same
finding and stay: `get` has a live caller (`context_retriever.py`), and `create`'s only reference is
a `getattr`-guarded branch already commented as reaching no surface.

## What stays unguarded, and why

These five sites interpolate a property name their caller supplies, through none of the three
guarantees. Each is deliberate, and the `trigger:` above is what would reopen it.

| Site | Interpolates | Why it stays |
|---|---|---|
| `_relationship_ordered_mixin.py:104,157,314,393` | `order_by_property` → `ORDER BY r.{…}` | `RelationshipSpec.order_by_property`, developer-authored: exactly two specs declare it, `"order"` and `"sequence"`, both `order_direction="ASC"` |
| `_relationship_ordered_mixin.py:~150` | `edge_properties` map projection | `RelationshipSpec.include_edge_properties`, two authored sites. The only request-reachable caller (`habits_ui.py:164,167`) resolves to specs that declare **neither** — so `edge_return` is the literal `properties(r)` and the sort clause is empty: zero interpolation on the live path |
| `_relationship_ordered_mixin.py:220` | `sequence_property` → `SET r.{…}` | A write, and the sharper of the set. Reached only through `OrderedRelationshipsMixin.reorder_relationships`, whose default is the literal `"sequence"` |
| `_relationship_ordered_mixin.py:451–459` | `match_pattern`, `return_parts`, `order_expression` | `get_hierarchical_children_deep` takes a whole MATCH pattern. Registered PLANNED and unwired (`_RELATIONSHIPS_HIERARCHY`, `scripts/detect_bloat.py`) — "no caller invokes the service entry point" |
| `curriculum_backends.list_steps_raw` | `order_field` ← `ps_core_service.py:366`'s `f"s.{order_by}"` | No HTTP caller passes `order_by`; every one passes `limit` (and sometimes `path_uid`). **This is the seam that widens** — `PsService.list_steps` forwards `**kwargs`, so a route accepting `?sort=` makes it live in one line |

Out of scope entirely: `exercise_backends.py:107`'s `order_by`. `_exercise_status_tail` is a
module-private query-fragment template with exactly three callers, all in the same file, all
passing Cypher *expression* literals (`"exercise.title"`, `"exercise.due_date ASC, exercise.created_at DESC"`).
It is not a parameter surface, and no identifier check applies to an expression.

**Explicitly not built:** a lint rule for unguarded interpolation. CYP003 deliberately excludes
structural composition, and PR #831 spent 19 rounds
and ~27 findings on a regex approximating a parser for zero measured delta.

**Considered and declined:** defaulting `list()`'s sort to the domain's `DomainConfig.search_order_by`
rather than `created_at`. It is more correct per domain (Events declares `event_date`) but changes
what every existing `list()` caller renders — a scope larger than closing the oracle, and a
separate decision.

## Census corrections to the brief that opened this

The brief this ruling answers was wrong in six places, recorded here because the shape of the
errors repeats — and because it descended from one whose most confidently stated claim was off
by a factor of 17:

1. **`validate_identifier` has 31 call sites across 5 modules, not "6, all in `crud_queries`."**
   The brief's census command was `grep -rn "_validate_identifier\|def validate_identifier"`,
   which can only match the underscore-prefixed spelling or the `def` line. `crud_queries` was
   the one module importing under the `_validate_identifier` alias — so "all in `crud_queries`"
   was an artifact of the alias collision the brief itself flagged as its strongest argument.
   The consolidation it priced at 26 sites was really ~50.
2. `_ALLOWED_ORDER_BY` holds **12** names, not 13 (stated twice).
3. The unguarded set omitted the `SET r.{sequence_property}` write, `get_hierarchical_children_deep`'s
   three raw slots, and the `field` interpolation in both array builders' `WHERE` clause.
4. "The edge-properties site is the live one" is true of the *method* and false of the
   *interpolation* — see the table above.
5. The duplication was a **pair** plus two constants, not one function.
6. **Request-reachability existed, at the sites the brief classified as safe.** It looked for it
   among the unguarded five and correctly found none; the live user-controlled sort key was on the
   CRUD list route, guarded by exactly the mechanism the brief was asking whether to extend.

Two of the three prose sites the brief listed as "already correct if the ruling is *leave it*"
were false as written: `.claude/skills/security/SKILL.md` claimed SKUEL "validates **all** such
values before interpolation", and `docs/security/ROUTE_AUTH_REQUIREMENTS.md` claimed they are
validated "**before any** f-string interpolation". Both now say what is true.
