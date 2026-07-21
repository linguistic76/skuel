#!/usr/bin/env python3
"""
Generate the Graph Vocabulary Contract view — docs/reference/GRAPH_CONTRACT.yaml
================================================================================

The emitted Analog view of the graph contract (2026-07 DSL review, step 5 of the
contract-hardening sequence). One YAML document, five sections:

- ``meta``          — sources and computed coverage counts
- ``relationships`` — every ``RelationshipName`` member (the SKUEL030-enforced
                      edge vocabulary), keyed by graph-facing value
- ``labels``        — every ``NeoLabel`` member (the CYP011-enforced label
                      vocabulary), keyed by graph-facing value; each configured
                      label also names its semantic-layer ``semantic_types``
- ``semantic_edge_properties`` — the sanctioned edge-property vocabulary a
                      semantic edge may carry (roadmap Phase 2)
- ``findings``      — names that appear in persistence Cypher but are NOT
                      vocabulary (the SKUEL030 baseline: known bugs, never
                      accepted names)

**Source roles are asymmetric by design.** The enums are the completeness
spine: every member appears exactly once, so the view can never imply that an
unconfigured edge does not exist. The relationship registry is the *sole*
metadata source: ``contract:`` blocks are read from
``core/models/relationship_registry.py`` and nowhere else. ``contract: null``
states a mechanical fact — the generic relationship machinery
(UnifiedRelationshipService / graph enrichment / ingestion mapping) has no
config for the name — not a judgment that the edge is unmodelled: registry
membership is conditional by design (see the maintenance note in
``relationship_names.py``), and many edges are served by dedicated backend
code instead.

The output is a pure function of its sources — no timestamps — so the drift
test can regenerate and byte-compare it
(``tests/unit/scripts/test_generate_graph_contract.py``).

Usage:
    uv run python scripts/generate_graph_contract.py          # regenerate
    uv run python scripts/generate_graph_contract.py --check  # exit 1 on drift
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import TypedDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from cypher_vocabulary import load_vocabulary  # type: ignore[import-not-found]
from lint_skuel import SkuelLinter  # type: ignore[import-not-found]

from core.infrastructure.relationships.semantic_relationships import RelationshipMetadata
from core.models.enums.entity_enums import EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName
from core.models.relationship_registry import (
    LABEL_CONFIGS,
    LATERAL_RELATIONSHIP_SPECS,
    DomainRelationshipConfig,
    UnifiedRelationshipDefinition,
)

ARTIFACT_PATH = PROJECT_ROOT / "docs" / "reference" / "GRAPH_CONTRACT.yaml"

# Trait name per RelationshipName predicate method (Dynamic Enum Pattern:
# classification comes from enum behavior, never from parsing section comments).
_TRAIT_PREDICATES: tuple[tuple[str, str], ...] = (
    ("knowledge", "is_knowledge_relationship"),
    ("blocking", "is_blocking_relationship"),
    ("ownership", "is_ownership_relationship"),
    ("evidence", "is_evidence_relationship"),
    ("learning_progress", "is_learning_progress_relationship"),
    ("life_path", "is_life_path_relationship"),
    ("parent_child", "is_parent_child_relationship"),
    ("prerequisite", "is_prerequisite_relationship"),
    ("lateral", "is_lateral_relationship"),
)

_PLAIN_SCALAR_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./|\-]*$")
_YAML_RESERVED = {"true", "false", "null", "yes", "no", "on", "off", "~"}


def _scalar(value: object) -> str:
    """Render one YAML scalar, quoting only when a plain scalar would misparse."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, int):
        return str(value)
    text = str(value)
    if _PLAIN_SCALAR_RE.fullmatch(text) and text.lower() not in _YAML_RESERVED:
        return text
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _flow_seq(values: list[object]) -> str:
    return "[" + ", ".join(_scalar(v) for v in values) + "]"


def _flow_map(pairs: list[tuple[str, str]]) -> str:
    """Render a flow mapping from (key, pre-rendered value) pairs."""
    return "{" + ", ".join(f"{k}: {v}" for k, v in pairs) + "}"


# =============================================================================
# Gathering — walk the registry structures into per-name occurrence data
# =============================================================================


def canonical_label_configs() -> dict[str, DomainRelationshipConfig]:
    """LABEL_CONFIGS restricted to real NeoLabel keys, first key wins per config."""
    label_values = {label.value for label in NeoLabel}
    seen_configs: set[int] = set()
    canonical: dict[str, DomainRelationshipConfig] = {}
    for key, config in LABEL_CONFIGS.items():
        if key not in label_values or id(config) in seen_configs:
            continue
        seen_configs.add(id(config))
        canonical[key] = config
    return canonical


def legacy_label_config_aliases() -> list[str]:
    label_values = {label.value for label in NeoLabel}
    return [key for key in LABEL_CONFIGS if key not in label_values]


def _definition_entry(definition: UnifiedRelationshipDefinition) -> str:
    """One relationship definition as a flow mapping (defaults omitted)."""
    pairs: list[tuple[str, str]] = [
        ("direction", _scalar(definition.direction)),
        ("target", _scalar(definition.target_label)),
        ("context_field", _scalar(definition.context_field_name)),
        ("method", _scalar(definition.method_key)),
    ]
    if definition.fields != ("uid", "title"):
        pairs.append(("fields", _flow_seq(list(definition.fields))))
    if definition.use_confidence:
        pairs.append(("use_confidence", "true"))
    if definition.include_rel_type:
        pairs.append(("include_rel_type", "true"))
    if definition.single:
        pairs.append(("single", "true"))
    if definition.limit is not None:
        pairs.append(("limit", _scalar(definition.limit)))
    if definition.filter_property is not None:
        pairs.append(("filter_property", _scalar(definition.filter_property)))
        pairs.append(("filter_value", _scalar(definition.filter_value)))
    if definition.order_by_property is not None:
        pairs.append(("order_by", _scalar(definition.order_by_property)))
        if definition.order_direction != "ASC":
            pairs.append(("order_direction", _scalar(definition.order_direction)))
    if definition.include_edge_properties:
        pairs.append(("edge_properties", _flow_seq(list(definition.include_edge_properties))))
    if definition.yaml_field_path is not None:
        pairs.append(("ingestion_field", _scalar(definition.yaml_field_path)))
    if definition.ingestion_entity_type is not None:
        pairs.append(("ingestion_entity_type", _scalar(definition.ingestion_entity_type.value)))
    if definition.shared_neighbor_config is not None:
        shared = definition.shared_neighbor_config
        pairs.append(
            (
                "shared_neighbor",
                _flow_map(
                    [
                        (
                            "via",
                            _flow_seq([rel.value for rel in shared.intermediate_relationships]),
                        ),
                        ("target", _scalar(shared.target_label)),
                        ("alias", _scalar(shared.result_alias)),
                    ]
                ),
            )
        )
    return _flow_map(pairs)


def _config_definitions(config: DomainRelationshipConfig) -> list[UnifiedRelationshipDefinition]:
    """All definitions a config carries — ``relationships`` plus the KU-style
    self-contained definitions inside ``bidirectional_relationships``."""
    inline_bidirectional = [
        item
        for item in config.bidirectional_relationships
        if isinstance(item, UnifiedRelationshipDefinition)
    ]
    return [*config.relationships, *inline_bidirectional]


class ContractOccurrence(TypedDict):
    """One config's touchpoints for a relationship: definitions plus role-only uses."""

    config: str
    roles: list[str]
    definitions: list[str]
    creation_keys: list[str]


class Finding(TypedDict):
    """One SKUEL030-baselined name: a known silent-zero bug, not vocabulary."""

    kind: str
    sites: list[str]


def gather_relationship_contracts() -> tuple[
    dict[str, list[ContractOccurrence]], dict[str, list[str]]
]:
    """Per relationship value: one occurrence dict per config that touches it.

    Also returns the per-config edge list (first-touch order), recorded in the
    SAME walk that builds the occurrences: the label-side ``relationships`` list
    and the relationship-side ``config:`` occurrences must be two projections of
    one enumeration, or role-only edges (prerequisite/enables/ownership names
    with no definition, e.g. TASKS_CONFIG's REQUIRES_TASK) appear in one section
    and not the other.
    """
    contracts: dict[str, dict[str, ContractOccurrence]] = {}
    label_edges: dict[str, list[str]] = {}

    def occurrence(rel_value: str, config_key: str) -> ContractOccurrence:
        per_config = contracts.setdefault(rel_value, {})
        if config_key not in per_config:
            label_edges.setdefault(config_key, []).append(rel_value)
        return per_config.setdefault(
            config_key, {"config": config_key, "roles": [], "definitions": [], "creation_keys": []}
        )

    for config_key, config in canonical_label_configs().items():
        for definition in _config_definitions(config):
            entry = occurrence(definition.relationship.value, config_key)
            entry["definitions"].append(_definition_entry(definition))
        if config.ownership_relationship is not None:
            occurrence(config.ownership_relationship.value, config_key)["roles"].append("ownership")
        for role, names in (
            ("prerequisite", config.prerequisite_relationship_names),
            ("enables", config.enables_relationship_names),
        ):
            for name in names:
                occurrence(name.value, config_key)["roles"].append(role)
        for item in config.bidirectional_relationships:
            if isinstance(item, RelationshipName):
                occurrence(item.value, config_key)["roles"].append("bidirectional")
        for creation_key, (name, _target, _props) in config.relationship_creation_map.items():
            occurrence(name.value, config_key)["creation_keys"].append(creation_key)

    return (
        {value: list(per_config.values()) for value, per_config in contracts.items()},
        label_edges,
    )


def gather_label_entity_types() -> dict[str, list[str]]:
    """Label value → EntityType values mapping to it (from NeoLabel, the enum-canonical map)."""
    mapping: dict[str, list[str]] = {}
    for entity_type in EntityType:
        label = NeoLabel.from_entity_type(entity_type)
        mapping.setdefault(label.value, []).append(entity_type.value)
    return mapping


def gather_findings() -> dict[str, Finding]:
    """SKUEL030 baseline grouped by name: known bugs in persistence Cypher."""
    findings: dict[str, Finding] = {}
    for file_path, name in sorted(SkuelLinter.SKUEL030_BASELINE):
        # Labels are PascalCase, relationship types UPPER_SNAKE — the same shape
        # rule the Cypher scanner applies (cypher_vocabulary name regexes).
        kind = "relationship" if name.isupper() else "label"
        entry = findings.setdefault(name, {"kind": kind, "sites": []})
        if file_path not in entry["sites"]:
            entry["sites"].append(file_path)
    return dict(sorted(findings.items()))


def sanctioned_semantic_edge_properties() -> list[str]:
    """The typed base edge-property vocabulary a semantic edge may carry.

    Derived from the single writer (``build_semantic_merge``), which persists
    ``RelationshipMetadata.to_neo4j_properties()`` plus the ``semantic_type``
    predicate (roadmap Phase 1). Sourcing the set from the metadata dataclass
    itself keeps the contract in lockstep with the writer: a new *typed* metadata
    field drifts this artifact instead of going silently unsanctioned. The probe
    populates every optional field so no conditionally-emitted key is missed
    (``to_neo4j_properties`` omits falsy source/temporal/evidence/notes).

    This is the base set, not a hard-closed universe: ``RelationshipMetadata``
    also carries a free-form ``properties`` map that ``to_neo4j_properties()``
    merges verbatim, so an author (via ``TripleBuilder.custom(properties=...)``)
    could persist arbitrary extra keys. No caller does today — the extension is
    unexercised — so the contract declares the typed base and flags ``properties``
    as the open escape hatch rather than inventing unbounded keys. A future
    consumer that starts writing custom props must not assume this set is
    exhaustive.
    """
    probe = RelationshipMetadata(
        source="registry",
        valid_from=datetime(2000, 1, 1),
        valid_until=datetime(2000, 1, 1),
        evidence=["registry"],
        notes="registry",
    )
    return sorted(set(probe.to_neo4j_properties()) | {"semantic_type"})


# =============================================================================
# Rendering
# =============================================================================


def _render_relationship(
    member: RelationshipName,
    occurrences: list[ContractOccurrence],
    lines: list[str],
) -> None:
    lines.append(f"  {member.value}:")
    if member.name != member.value:
        lines.append(f"    enum_member: {member.name}")

    traits = [trait for trait, predicate in _TRAIT_PREDICATES if getattr(member, predicate)()]
    if traits:
        lines.append(f"    traits: {_flow_seq(traits)}")

    lateral = LATERAL_RELATIONSHIP_SPECS.get(member)
    if lateral is not None:
        lines.append("    lateral:")
        lines.append(f"      category: {_scalar(lateral.category)}")
        lines.append(f"      symmetric: {_scalar(lateral.is_symmetric)}")
        if lateral.inverse_type is not None:
            lines.append(f"      inverse: {lateral.inverse_type.value}")
        lines.extend(
            f"      {flag}: true"
            for flag in ("requires_same_parent", "requires_same_depth", "check_cycles")
            if getattr(lateral, flag)
        )

    if not occurrences:
        lines.append("    contract: null")
        return

    lines.append("    contract:")
    for entry in occurrences:
        lines.append(f"      - config: {entry['config']}")
        if entry["roles"]:
            lines.append(f"        roles: {_flow_seq(entry['roles'])}")
        if entry["creation_keys"]:
            lines.append(f"        creation_keys: {_flow_seq(entry['creation_keys'])}")
        if entry["definitions"]:
            lines.append("        definitions:")
            lines.extend(f"          - {definition}" for definition in entry["definitions"])


def _render_label(
    label: NeoLabel,
    entity_types: list[str],
    config: DomainRelationshipConfig | None,
    edges: list[str],
    lines: list[str],
) -> None:
    lines.append(f"  {label.value}:")
    if entity_types:
        lines.append(f"    entity_types: {_flow_seq(entity_types)}")
    if config is None:
        lines.append("    contract: null")
        return
    lines.append("    contract:")
    lines.append(f"      domain: {_scalar(config.domain.value)}")
    if config.ownership_relationship is not None:
        lines.append(f"      ownership: {config.ownership_relationship.value}")
    if config.is_shared_content:
        lines.append("      shared_content: true")
    if edges:
        lines.append("      relationships:")
        lines.extend(f"        - {value}" for value in edges)
    # Semantic-layer registration (roadmap Phase 2): the precise predicates this
    # config's find_by_semantic_filter defaults to (config.semantic_types, live-read
    # in _intelligence_mixin). Emitted as SemanticRelationshipType values — the
    # namespaced predicate surface, distinct from the RelationshipName edge spine.
    if config.semantic_types:
        semantic_values = [predicate.value for predicate in config.semantic_types]
        lines.append(f"      semantic_types: {_flow_seq(semantic_values)}")


def render_contract() -> str:
    """Render the full artifact. Pure function of the imported sources."""
    _assert_vocabulary_consistency()

    relationship_contracts, label_edges = gather_relationship_contracts()
    label_configs = canonical_label_configs()
    label_entity_types = gather_label_entity_types()
    findings = gather_findings()

    relationships_with_contract = sum(
        1
        for member in RelationshipName
        if member.value in relationship_contracts or member in LATERAL_RELATIONSHIP_SPECS
    )

    lines = [
        "# =============================================================================",
        "# GRAPH VOCABULARY CONTRACT — AUTO-GENERATED, DO NOT EDIT",
        "# =============================================================================",
        "# Regenerate:   cd app && uv run python scripts/generate_graph_contract.py",
        "# Drift-guarded: tests/unit/scripts/test_generate_graph_contract.py",
        "#",
        "# The emitted Analog view of the graph contract (2026-07 DSL review, step 5).",
        "# Spine: every RelationshipName / NeoLabel member — the exact vocabulary",
        "# SKUEL030 / CYP011 enforce in persistence Cypher. Metadata: read solely from",
        "# core/models/relationship_registry.py (the generic relationship machinery's",
        "# config).",
        "#",
        "# `contract: null` is a mechanical fact, not a judgment: the name is valid",
        "# vocabulary that the generic machinery (UnifiedRelationshipService, graph",
        "# enrichment, ingestion mapping) has no config for — either deliberately plain",
        "# (served by dedicated backend code; registry membership is conditional by",
        "# design, see the maintenance note in relationship_names.py) or not yet",
        "# registered (the semantic-relationship-layer roadmap grows coverage).",
        "#",
        "# `findings:` names are NOT vocabulary. They appear in persistence Cypher but",
        "# are known silent-zero bugs (SKUEL030 baseline) — see",
        "# docs/patterns/CYPHER_VOCABULARY_FINDINGS.md for the triage.",
        "",
        "meta:",
        "  sources:",
        "    vocabulary:",
        "      relationships: core/models/relationship_names.py::RelationshipName",
        "      labels: core/models/enums/neo_labels.py::NeoLabel",
        "    contract: core/models/relationship_registry.py",
        "    findings: scripts/lint_skuel.py::SkuelLinter.SKUEL030_BASELINE",
        "  coverage:",
        "    relationships: "
        + _flow_map(
            [
                ("total", str(len(list(RelationshipName)))),
                ("with_contract", str(relationships_with_contract)),
            ]
        ),
        "    labels: "
        + _flow_map(
            [
                ("total", str(len(list(NeoLabel)))),
                ("with_contract", str(len(label_configs))),
            ]
        ),
        f"  legacy_label_config_aliases: {_flow_seq(list(legacy_label_config_aliases()))}",
        "",
        "relationships:",
    ]

    for member in RelationshipName:
        _render_relationship(member, relationship_contracts.get(member.value, []), lines)

    lines.append("")
    lines.append("labels:")
    for label in NeoLabel:
        _render_label(
            label,
            label_entity_types.get(label.value, []),
            label_configs.get(label.value),
            label_edges.get(label.value, []),
            lines,
        )

    lines.append("")
    lines.append("# Sanctioned edge-property vocabulary for semantic edges (roadmap Phase 2).")
    lines.append("# `properties` = the typed base set build_semantic_merge writes: every typed")
    lines.append("# RelationshipMetadata field plus semantic_type (the precise")
    lines.append("# SemanticRelationshipType predicate, Phase 1). NOT hard-closed —")
    lines.append("# RelationshipMetadata also carries a free-form `properties` map merged")
    lines.append("# verbatim (open_extension below), so a consumer must not treat this set as")
    lines.append("# exhaustive once custom props are written. Per-config `semantic_types:`")
    lines.append("# under labels names which predicates a domain's find_by_semantic_filter")
    lines.append("# defaults to. Phase 4 keys confidence-weighted traversal on this set.")
    lines.append("semantic_edge_properties:")
    lines.append(
        "  source: core/infrastructure/relationships/"
        "semantic_relationships.py::RelationshipMetadata.to_neo4j_properties"
    )
    lines.append(f"  properties: {_flow_seq(sanctioned_semantic_edge_properties())}")
    lines.append(
        "  open_extension: "
        + _flow_map(
            [
                ("field", "properties"),
                ("merged_by", "RelationshipMetadata.to_neo4j_properties"),
                ("exhaustive", "false"),
                ("callers_today", "0"),
            ]
        )
    )

    lines.append("")
    lines.append("# Known silent-zero bugs, NOT vocabulary (SKUEL030 baseline; shrinking list).")
    lines.append("findings:")
    for name, entry in findings.items():
        lines.append(f"  {name}:")
        lines.append(f"    kind: {entry['kind']}")
        lines.append("    sites:")
        lines.extend(f"      - {site}" for site in entry["sites"])

    lines.append("")
    return "\n".join(lines)


def _assert_vocabulary_consistency() -> None:
    """The runtime enums and the AST-read vocabulary (the linters' view) must agree.

    ``cypher_vocabulary.load_vocabulary`` is THE reader the linters trust; if the
    runtime import ever disagrees with it, the artifact would describe a different
    vocabulary than the one being enforced — fail loudly instead of emitting.
    """
    vocabulary = load_vocabulary()
    runtime_relationships = frozenset(member.value for member in RelationshipName)
    runtime_labels = frozenset(label.value for label in NeoLabel)
    if runtime_relationships != vocabulary.relationships or runtime_labels != vocabulary.labels:
        raise RuntimeError(
            "Runtime enums disagree with the AST-read vocabulary "
            "(cypher_vocabulary.load_vocabulary) — refusing to emit a contract "
            "that differs from what SKUEL030/CYP011 enforce."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate docs/reference/GRAPH_CONTRACT.yaml")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if the checked-in artifact differs from a fresh render (no write).",
    )
    args = parser.parse_args()

    content = render_contract()

    if args.check:
        on_disk = ARTIFACT_PATH.read_text(encoding="utf-8") if ARTIFACT_PATH.exists() else ""
        if on_disk != content:
            print("❌ GRAPH_CONTRACT.yaml is stale.")
            print("   Regenerate: cd app && uv run python scripts/generate_graph_contract.py")
            return 1
        print("✅ GRAPH_CONTRACT.yaml is fresh.")
        return 0

    ARTIFACT_PATH.write_text(content, encoding="utf-8")
    print(f"✅ Generated: {ARTIFACT_PATH}")
    print(f"   Total lines: {len(content.splitlines())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
