---
title: Service Docstring Style
updated: 2026-05-28
category: patterns
related_skills:
- python
related_docs:
- DOCSTRING_STANDARDS.md
- ../decisions/ADR-044-hexagonal-boundary-enforcement.md
---
# Service Docstring Style

> **Core Principle**: "In `core/services/`, docstrings describe **intent** in domain language; the backend describes **mechanism**."

A narrow companion to [DOCSTRING_STANDARDS.md](DOCSTRING_STANDARDS.md). That doc covers the universal three-layer model (implementation / pattern / architecture). This one covers the specific drift that the layer model permits at the service/backend boundary.

---

## Why this exists

SKUEL021 forbids raw Cypher in `core/` *used strings* but skips docstrings — prose can't execute, so flagging it would be noise without security value. The intentional consequence: a service docstring **can** describe its backend's Cypher and the linter won't push back.

That permission is correct at the runtime layer, but it leaves a documentation-discipline gap. A service docstring that quotes Cypher:

- Drifts from the backend as the backend evolves (no enforced link)
- Duplicates mechanism that already lives in the backend docstring
- Trains readers to think above the hexagonal boundary in below-the-boundary terms

The rule below closes the gap by convention rather than lint.

---

## The rule

For files in `core/services/`:

1. **Service-level docstrings describe WHAT the operation means** in domain language — what the caller gets, what the operation is *for*, what invariants hold.
2. **Mechanism (Cypher, traversals, label sets, APOC behavior) lives in the backend docstring**, not the service docstring.
3. **Cross-reference the backend method** with a `Backend:` line so a reader who wants the mechanism has a one-hop path.

Files in `core/utils/`, `adapters/`, and tests are out of scope — Cypher in docstrings there is often the teaching subject and should stay.

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

## Relationship to SKUEL021

SKUEL021 will not fail your build if you describe Cypher in a service docstring. This document is the reason that's OK in tooling terms but discouraged in review terms. PR reviewers may point at this doc when asking for an intent rewrite.

If you want the discipline mechanized later, a *warning-level* (non-blocking) lint over `core/services/**/*.py` that flags Cypher-shaped fragments in docstrings would close the loop without inflating SKUEL021's purpose.

---

**Last Updated**: 2026-05-28
**Status**: Current
