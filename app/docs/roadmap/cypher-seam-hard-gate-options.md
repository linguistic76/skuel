# Cypher label/rel-type seam typing — hard-gate options (scoping only, NOT done)

*Created: 2026-05-24. Companion to the Phase-1 (rel-type → `RelationshipName`, PR #41) and
Phase-2 (label → `NeoLabel`, this branch) seam-typing work.*

## The question

Phase 1 + 2 typed the Cypher label/relationship-type interpolation seams to `NeoLabel` /
`RelationshipName`. As established in Phase 1, this enforcement is **documentation + a pyright
in-editor/CLI WARNING + cleaner enum dataflow — NOT a hard CI gate**, because:

- mypy's `arg-type` error code is **globally disabled** (`pyproject.toml`, one of the four
  globally-disabled codes), so mypy never rejects a raw `str` passed to a `NeoLabel` /
  `RelationshipName` parameter.
- pyright's `reportArgumentType` fires (it's how the seam is "seen"), but pyright runs in
  `typeCheckingMode=basic` and `reportArgumentType` is a **warning**, so it does not fail
  `./dev quality` or CI.

Should we promote the seam types to an actual hard gate? Below is the measured blast radius of
each path (measured 2026-05-24 on this branch). **No config was changed.**

## Option A — re-enable mypy `arg-type`

| Scope | arg-type violations | …of which label/rel-seam related |
|-------|--------------------:|---------------------------------:|
| Globally (`uv run mypy . --enable-error-code arg-type`) | **2003** | 54 |

Re-enabling globally surfaces 2003 must-fix errors for a 54-error seam benefit (~2.7%).
**Per-module** re-enable doesn't isolate the seam either: the 54 seam violations live in the
same backend/service modules that contain a large share of the other ~1949 (the "100% dynamic
backend" generic-typing patterns), so scoping `arg-type` to those modules still forces fixing
everything in them. **Non-viable.**

## Option B — promote pyright `reportArgumentType` to error

| Scope | `reportArgumentType` warnings to clear | …of which seam-related |
|-------|---------------------------------------:|-----------------------:|
| Globally | **747** | 58 |
| Scoped to `adapters/persistence/neo4j/` only | **129** | 45 |
| (`core/services/` ones, for reference) | 133 | — |
| (`other`, for reference) | 485 | — |

Promoting globally requires clearing 747 baseline warnings (689 unrelated). A **separate pyright
config root** scoped to `adapters/persistence/neo4j/` (+ the seam ports) is the *most feasible*
path, but still requires clearing **84 unrelated** `reportArgumentType` warnings in that subtree
first (129 total − 45 seam). That baseline-clearing is a deliberate project of its own.

## Recommendation: keep the WARNING-level status quo

Do **not** promote to a hard gate as a rider on the seam-typing work. Rationale:

1. **Cost/benefit is lopsided** — 130–750+ unrelated baseline violations to clear for a seam of
   ~45–58 sites.
2. **The seam is already defended in depth**, so the type is not the sole guard:
   - Runtime fail-fast: `UniversalNeo4jBackend._normalize_label` (`NeoLabel.is_valid`), the
     `validate_label` construction guard, `neo4j_schema_manager._validate_label` /
     `query/cypher/_helpers.validate_label` regex guards, and the `RelationshipName` registry
     validation (`create_relationship`, `_build_direction_pattern`).
   - Lint: the Cypher strict-validation check + `SKUEL001` (no APOC), `SKUEL013`
     (`RelationshipName`), `SKUEL014` (`EntityType`/`NonKuDomain`), `SKUEL021` (no raw Cypher in
     `core/services/`).
3. **Low intrinsic risk** — labels and relationship types come from a fixed enum source set at
   construction (`self.label`, config-sourced `RelationshipName`), not per-request user input, so
   the injection surface the gate would protect is already narrow.

If a hard gate is ever wanted, do it as its own initiative: clear the
`adapters/persistence/neo4j/` `reportArgumentType` baseline (~129), then add a scoped pyright
config root that sets `reportArgumentType = "error"` for that subtree + the seam ports.
