---
title: Service Docstring Style
updated: 2026-07-29
category: patterns
related_skills:
- python
related_docs:
- DOCSTRING_STANDARDS.md
- ../decisions/ADR-044-hexagonal-boundary-enforcement.md
---
# Service Docstring Style

> **Core Principle**: "Above the hexagonal boundary, docstrings describe **intent** in domain language; the backend describes **mechanism**."

A narrow companion to [DOCSTRING_STANDARDS.md](DOCSTRING_STANDARDS.md). That doc covers the universal three-layer model (implementation / pattern / architecture). This one covers the specific drift that the layer model permits at the service/backend boundary.

---

## Why this exists

SKUEL021 forbids raw Cypher in `core/` *used strings* but skips docstrings — prose can't execute, so flagging it would be noise without security value. The intentional consequence: a service docstring **can** describe its backend's Cypher and the linter won't push back.

That permission is correct at the runtime layer, but it leaves a documentation-discipline gap. A service docstring that quotes Cypher:

- Drifts from the backend as the backend evolves (no enforced link)
- Duplicates mechanism that already lives in the backend docstring
- Trains readers to think above the hexagonal boundary in below-the-boundary terms

The rule below closed that gap by convention for a year; **SKUEL033 now enforces it** — both a docstring that *opens* with a clause and one that *hosts* a whole query (see § Relationship to SKUEL021 and SKUEL033). Convention alone was not enough, and the first bullet above is why: 14 docstrings across 6 files had drifted into naming their backend's clause before the rule existed, and when the query-block half was swept, **all three of its sites had drifted from the backend they documented**.

---

## The rule

For files in the intent-only trees — `core/services/`, `core/orchestrator/`, `core/ports/`, `core/models/` (the **No** rows of [the table below](#where-this-applies), which is the authority on scope):

1. **Docstrings describe WHAT the operation means** in domain language — what the caller gets, what the operation is *for*, what invariants hold.
2. **Mechanism (Cypher, traversals, label sets, APOC behavior) lives in the backend docstring**, not above the boundary.
3. **Cross-reference the backend method** with a `Backend:` line so a reader who wants the mechanism has a one-hop path.

Files in `core/utils/`, `adapters/`, and tests are out of scope — Cypher in docstrings there is often the teaching subject and should stay.

**`MERGE` is an upsert, so "Create" is a lossy rewrite.** The contract a caller needs is the idempotency: what survives a repeat call, what wins on conflict. `MERGE a MASTERED edge; higher score always wins` became *"Record mastery of a KU; the highest score ever reported always wins"* — the clause name went, the guarantee stayed. Check the implementing backend before rewording; several ports had non-obvious semantics that a generic rewrite would have silently dropped.

---

## Intent vs. mechanism — side by side

### Example 1: A facade-level read method

```python
# ❌ Mechanism-flavored (status-quo legal, discipline-discouraged)
async def get_path_steps_using(self, ku_uid: str) -> Result[list[PathStep]]:
    """
    Run `MATCH (ps:PathStep)-[:USES_KU]->(ku:Ku {uid: $ku_uid}) RETURN ps`
    against the backend and convert records to PathStep objects.
    """
```

```python
# ✅ Intent-first (preferred)
async def get_path_steps_using(self, ku_uid: str) -> Result[list[PathStep]]:
    """
    Get every PathStep that composes this Ku.

    Used by the Ku detail page to surface "where does this knowledge appear?"

    Backend: KuBackend.get_path_steps_using
    See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md (PathStep -> Ku composition)
    """
```

### Example 2: A write method with non-obvious effect

```python
# ❌ Mechanism-flavored
async def mark_mastered(self, user_uid: UserUID, ku_uid: str) -> Result[bool]:
    """
    MERGE a (user)-[:MASTERED {score: 0.7, method: 'self_report'}]->(ku)
    relationship. If IN_PROGRESS exists, leave it (history).
    """
```

```python
# ✅ Intent-first
async def mark_mastered(self, user_uid: UserUID, ku_uid: str) -> Result[bool]:
    """
    Record that the user self-reports understanding of this Ku.

    Self-reported mastery is distinct from assessed mastery; the IN_PROGRESS
    state is preserved so the learning trajectory remains auditable.

    Backend: KuBackend.mark_mastered
    See: /docs/architecture/knowledge_substance_philosophy.md
    """
```

### Example 3: When mechanism *is* the intent

Sometimes the operation's identity *is* its mechanism (e.g. a pure projection helper). In those cases, describing the shape is fine — but still in domain terms, not Cypher:

```python
# ✅ Acceptable — describes shape, not query syntax
async def get_user_learning_states(self, user_uid: UserUID) -> Result[list[dict]]:
    """
    For each Ku the user has touched, return its current learning state
    (`is_studying`, `is_understood`). Used to hydrate the sidebar.

    Backend: KuBackend.get_user_learning_states
    """
```

---

## The `Backend:` cross-reference convention

When a service method delegates to a single backend method, add one line:

```
Backend: <BackendClass>.<method_name>
```

Rules:

- One line, not a paragraph.
- Place it after the description, before `See:` / `Args:` / `Returns:`.
- Use the backend class as imported via TYPE_CHECKING — keep names in sync.
- Omit when the service method orchestrates multiple backend calls; describe the orchestration in intent terms and let the implementation be the source of truth for the call list.

This is **documentation glue**, not a contract. It exists so a reader chasing mechanism reaches the backend in one hop without forcing the service docstring to host implementation detail.

---

## Where this applies

| Location | Intent-only docstrings? | Cypher in docstrings OK? |
|----------|-------------------------|--------------------------|
| `core/services/` | Yes | No (move down to backend) |
| `core/orchestrator/` | Yes | No (orchestrators describe flow, not query) |
| `core/utils/` | No — teaching docs allowed | Yes (USAGE EXAMPLES blocks) |
| `core/ports/` | Yes (protocols are contracts) | No (protocols don't have implementations) |
| `adapters/persistence/neo4j/` | No | Yes — backend is the right home |
| `core/models/` | Yes | No (models are data, not query) |

---

## Quick checklist

Before merging a `core/services/` change:

- [ ] Does the docstring describe **what the operation means**, not how it queries?
- [ ] If the method delegates to one backend method, is there a `Backend:` line?
- [ ] If you wrote `MATCH`, `MERGE`, `CREATE`, `RETURN` in the docstring — could the backend docstring carry that instead?
- [ ] Does the `See:` line point at architecture/pattern depth, not just restate the code?

---

## Relationship to SKUEL021 and SKUEL033

SKUEL021 will not fail your build if you describe Cypher in a service docstring — it skips docstrings by node identity, correctly, because prose cannot execute. This document is the reason that's OK in tooling terms but discouraged in review terms.

**The mechanization this section used to propose now exists: SKUEL033.** It is the warning-level rule described here — with two refinements learned from building it:

- **Scope is the table above, not `core/services/` alone.** SKUEL033 reads the four `core/` rows whose *Cypher in docstrings OK?* cell says **No**, and a test reparses that table to keep the rule and the doc from drifting apart. Change a row here and the linter's test tells you to change the rule.
- **It flags two shapes: HEAD and QUERY BLOCK.** Head = a docstring that *opens* with a clause. Query block = two or more non-head lines that are each themselves Cypher, i.e. the docstring *hosts* a query — classically indented under a `Pattern:` heading. The block shape was this section's last open gap and was closed in #875; the paragraph below records what closing it found.
- **Prose that merely names a clause mid-sentence stays legal** under both shapes. It is describing a neighbour, not documenting itself in mechanism terms. `core/ports/query_types.py`'s row-shape references are the canonical keep: a TypedDict naming the ``RETURN <alias>`` its row mirrors is documenting **the contract**, because nothing statically links a Cypher alias to a TypedDict key — delete the reference and the only written record of what the key mirrors goes with it.
- **The block threshold is two clause lines in one contiguous run**, so a one-line embedded query stays legal, as does a query split across a blank line. Both halves are measured limits, not oversights: a wrapped English sentence puts a clause word at a line head with an operand after it (a one-line threshold measured 8 sites, 5 legitimate), and the run requirement is what keeps a docstring documenting **two non-adjacent aliases** — legitimate under this document — from reaching the threshold on two prose references. A line opening with a backtick is treated as a *reference*, never as query text, so an inline ``RETURN <alias>`` can never combine with another into a phantom block. Its failure direction is a miss, which is the fail-safe one *because* SKUEL033 fails `--strict`; tests assert every limit.

**Closing the block gap found that every instance had drifted** — which is the first reason this document gives for the rule. Three sites, three drifts: a port advertising an `entry` **node** where its backend returns 14 flat scalars (and omitting a whole aggregation); a model documenting `duration({minutes: 15})` and alias `failed_attempts` where the backend parameterises the window and aliases `failed_count`, while never mentioning the *second*, per-IP rate limiter; and a config dataclass showing `shared_count: 1` where its generator does a two-step aggregation — documenting the bug the generator exists to avoid. **A docstring quoting Cypher is not merely redundant; unenforced, it reliably becomes wrong.** Prefer stating the guarantee, and where the row shape *is* the contract, document the shape and the alias rather than the query.

`core/utils/` is deliberately exempt, per its **Yes** row: its USAGE EXAMPLES blocks are the teaching subject. That exemption is also load-bearing for SKUEL021's own regression guard, which binds to `core/utils/` precisely because it is the one tree where docstring Cypher is permanently correct.

**See:** [linter_rules.md § Rule: SKUEL033](linter_rules.md#rule-skuel033---above-boundary-docstrings-state-intent-not-mechanism)

---

**Last Updated**: 2026-07-29
**Status**: Current
