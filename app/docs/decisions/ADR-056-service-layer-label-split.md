---
title: "ADR-056: Service-Layer Label Split — entity_label + config_lookup_label"
updated: 2026-06-17
status: current
category: decisions
tags: [adr, decisions, service-layer, domain-config, neo4j, registry]
related:
  - ADR-026-unified-relationship-registry
  - ADR-031-baseservice-mixin-decomposition
---

# ADR-056: Service-Layer Label Split — `entity_label` + `config_lookup_label`

**Status:** Accepted
**Date:** 2026-04-21
**Related:**
[ADR-026 Unified Relationship Registry](ADR-026-unified-relationship-registry.md),
[ADR-031 BaseService Mixin Decomposition](ADR-031-baseservice-mixin-decomposition.md)

## Context

`DomainConfig.entity_label` was doing two jobs at once:

1. **Neo4j base-label** — the string the mixin layer puts into Cypher
   `MATCH (n:Entity:{label})` patterns. For Activity Domains this is
   `"Entity"`; for the Ku subsystem it is `"Ku"`.
2. **`LABEL_CONFIGS` registry key** — the string
   `context_operations_mixin.get_with_context()` uses to look up the
   domain's `DomainRelationshipConfig` (graph-enrichment patterns,
   prerequisite/enables relationships, post-processors).

The two strings are not the same. An Activity Domain wants `"Entity"` in
Cypher (so the multi-label match hits `:Entity:Task`, `:Entity:Goal`, …)
but `"Task"`, `"Goal"`, … as the registry key. The overload was papered
over by a `LABEL_CONFIGS["Entity"] → PS_CONFIG` backward-compat alias
that silently routed every Activity Domain service to PathStep's
curriculum patterns whenever it went to fetch its relationship
configuration. The alias looked like a harmless compatibility shim; it
was actually a semantic bug.

Nineteen services had grown `@property def entity_label` overrides to
work around this — each one a small local attempt to give the right
string to the right caller. The overrides were the fingerprint of the
overload.

## Decision

Split the single attribute into two:

| Attribute | Job | Example values |
|-----------|-----|----------------|
| `entity_label` | Neo4j base-label for Cypher matching. | `"Entity"`, `"Ku"` |
| `config_lookup_label` | `LABEL_CONFIGS` registry key. Defaults to `model_class.__name__`. | `"Task"`, `"Goal"`, `"PathStep"`, `"Ku"` |

**Changes:**

1. `DomainConfig` gains a `config_lookup_label: str | None = None`
   field next to `entity_label`. The factories
   `create_activity_domain_config()` and `create_curriculum_domain_config()`
   resolve it from `model_class.__name__` when omitted and **raise
   `ValueError`** if the resolved key is not in `LABEL_CONFIGS`.
   Missing registry entries fail at factory construction, not at
   first query.
2. `BaseService` exposes both as `@cached_property` accessors with
   matching five-priority fallback chains (direct attribute, class
   attribute, config, subclass hook, default).
3. The `LABEL_CONFIGS["Entity"] → PS_CONFIG` alias is **deleted**.
   Activity Domains now resolve to their own registry config. The
   nineteen `@property def entity_label` escape hatches are removed.
4. `ContextOperationsMixin` declares `config_lookup_label` as an abstract
   property next to `entity_label` and uses it for the registry lookup
   in `get_with_context()`. Cypher base-label usage continues to call
   `self.entity_label`.

**Fail-fast over fall-back.** The domain config factories (`create_activity_domain_config`,
`create_curriculum_domain_config`) validate `config_lookup_label` against `LABEL_CONFIGS`
at construction time and raise `ValueError` when the key is missing, rather than returning
a sentinel like `"Entity"` that would silently re-introduce the old alias behavior.

## Consequences

**Positive**

- Activity Domain services now resolve to the *correct* registry
  config. `TasksService.get_with_context()` reads from `TASKS_CONFIG`,
  not `PS_CONFIG`.
- Factory-level validation surfaces missing registry keys at startup.
- The nineteen per-service `entity_label` overrides are gone. New
  domains inherit the right behavior from the factory.
- `context_operations_mixin.py` now has two clearly-named abstract
  properties — the boundary between "Cypher label" and "registry key"
  is explicit in the protocol.

**Negative / follow-up**

- Callers that read `self.entity_label` expecting the old
  domain-specific string (`"Task"`, `"Goal"`, …) have silently shifted
  to returning the base label (`"Entity"`) for Activity Domains.
  Every mixin-layer call site that flows into logging, error-resource
  strings, `_domain` routing keys, or `target_label` filters must
  switch to `self.config_lookup_label`. See the follow-up commit that
  lands the mixin-layer cleanup and the registry-level normalization
  of `DomainRelationshipConfig.entity_label` to `"Entity"` for the
  three Activity Domains that still carried the domain-specific value
  (Tasks, Goals, Events).
- Tests tightened by the refactor
  (`test_relationship_registry.py`, `test_rich_context_pattern.py`)
  do not exercise the mixin paths with domain-discriminating
  assertions. A follow-up unit test in `test_baseservice_mixins.py`
  pins `config_lookup_label == "Task"` drives `get_by_relationship`'s
  `target_label` and `_domain` faceted-search routing.

## Alternatives Considered

1. **Keep the overload; formalize the alias.** Document the
   `"Entity"` key, keep the `PS_CONFIG` fallback as first-class
   behavior. Rejected — the alias is a semantic bug, not a
   compatibility artifact. Formalizing it would lock in the silent
   cross-domain routing that motivated the split.
2. **Split only at the registry level, not the service layer.**
   Rename `DomainRelationshipConfig.entity_label` to
   `config_lookup_label` and leave `DomainConfig` with a single
   `entity_label`. Rejected — `context_operations_mixin` still needs
   the two strings for distinct jobs (Cypher match vs. registry
   lookup). Splitting only at one layer would re-create the overload
   on the other.
3. **Add a lookup helper instead of a second field.**
   `DomainConfig.entity_label` stays single-valued, a helper method
   derives the registry key. Rejected — the two strings are
   configuration inputs, not derived values. Making one of them a
   method hides the split behind a call site.

## Related

- Extends [ADR-026 Unified Relationship Registry](ADR-026-unified-relationship-registry.md).
  ADR-026 introduced `DomainRelationshipConfig` and `LABEL_CONFIGS`;
  ADR-056 is the service-layer evolution that teaches `DomainConfig`
  how to talk to them without the `"Entity"` alias.
- Complements [ADR-031 BaseService Mixin Decomposition](ADR-031-baseservice-mixin-decomposition.md).
  The abstract `config_lookup_label` property on `ContextOperationsMixin`
  is the newest entry in the mixin-contract surface area documented
  there.
- In-repo skill record: `.claude/skills/activity-domains/SKILL.md`
  § "Two labels, two jobs" — quick reference for new-domain setup.
