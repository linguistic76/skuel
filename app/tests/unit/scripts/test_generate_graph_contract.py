"""
Drift + honesty guards for docs/reference/GRAPH_CONTRACT.yaml
=============================================================

The contract view is a checked-in generated artifact whose freshness is
enforced: any registry/enum/baseline change that lands without regenerating
the YAML fails here (the CREDENTIAL_CATALOG mirror-test pattern, applied to a
whole artifact instead of a mirrored set; BASESERVICE_METHOD_INDEX.md follows
the same pattern via test_generate_method_index.py).

The honesty guards pin the properties the artifact exists to provide:
- every enum member appears (the view can never imply an unconfigured name
  does not exist), and
- no SKUEL030-baselined name is ever presented as vocabulary.
"""

import sys
from datetime import datetime
from pathlib import Path

import yaml

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from generate_graph_contract import (  # type: ignore[import-not-found]
    ARTIFACT_PATH,
    render_contract,
    sanctioned_semantic_edge_properties,
)

from core.infrastructure.relationships.semantic_relationships import (
    RelationshipMetadata,
    SemanticRelationshipType,
)
from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName


def test_artifact_is_fresh() -> None:
    """The checked-in YAML must byte-match a fresh render of its sources."""
    assert ARTIFACT_PATH.exists(), (
        f"{ARTIFACT_PATH} is missing. "
        "Generate it: cd app && uv run python scripts/generate_graph_contract.py"
    )
    assert ARTIFACT_PATH.read_text(encoding="utf-8") == render_contract(), (
        "docs/reference/GRAPH_CONTRACT.yaml is stale — the enums, the relationship "
        "registry, or the SKUEL030 baseline changed without regenerating the view. "
        "Run: cd app && uv run python scripts/generate_graph_contract.py"
    )


def test_artifact_parses_with_complete_vocabulary_spine() -> None:
    """Valid YAML; every enum member present exactly once; coverage counts true."""
    document = yaml.safe_load(render_contract())

    relationship_keys = set(document["relationships"])
    label_keys = set(document["labels"])
    assert relationship_keys == {member.value for member in RelationshipName}
    assert label_keys == {label.value for label in NeoLabel}

    coverage = document["meta"]["coverage"]
    assert coverage["relationships"]["total"] == len(relationship_keys)
    assert coverage["labels"]["total"] == len(label_keys)
    with_contract = sum(
        1
        for entry in document["relationships"].values()
        if entry.get("contract") is not None or "lateral" in entry
    )
    assert coverage["relationships"]["with_contract"] == with_contract
    assert coverage["labels"]["with_contract"] == sum(
        1 for entry in document["labels"].values() if entry.get("contract") is not None
    )


def test_findings_are_never_presented_as_vocabulary() -> None:
    """Baselined names are known bugs — they must appear ONLY under findings.

    The SKUEL030 baseline is EMPTY since the semantic-relationship-layer roadmap
    Phase 1 closed §9 (its last two pairs). The disjointness invariant below then
    holds vacuously; it stays to guard the next time the baseline grows. An empty
    findings section is the expected state, not a gather bug.
    """
    document = yaml.safe_load(render_contract())

    finding_names = set(document["findings"] or {})
    assert finding_names.isdisjoint(document["relationships"]), (
        "A SKUEL030-baselined name appears in the relationships vocabulary section. "
        "If the name was legitimately registered, its baseline entries must be "
        "deleted (the baseline is a shrinking list of known bugs, never vocabulary)."
    )
    assert finding_names.isdisjoint(document["labels"]), (
        "A SKUEL030-baselined name appears in the labels vocabulary section. "
        "If the name was legitimately registered, its baseline entries must be "
        "deleted (the baseline is a shrinking list of known bugs, never vocabulary)."
    )


def test_contract_occurrences_reference_configured_labels() -> None:
    """Every relationship occurrence's `config` key is a label with a contract."""
    document = yaml.safe_load(render_contract())

    configured_labels = {
        value for value, entry in document["labels"].items() if entry.get("contract") is not None
    }
    for value, entry in document["relationships"].items():
        for occurrence in entry.get("contract") or []:
            assert occurrence["config"] in configured_labels, (
                f"relationship {value} cites config {occurrence['config']!r}, "
                "which has no label contract entry"
            )


# =============================================================================
# Semantic-layer surfaces (roadmap Phase 2)
# =============================================================================


def test_label_semantic_types_are_valid_predicates() -> None:
    """Every `semantic_types` value under labels is a real SemanticRelationshipType.

    The label spine names edges (RelationshipName); the semantic layer names
    predicates (SemanticRelationshipType). This guards the second surface — a
    typo or a migrated-away predicate value can never masquerade as sanctioned
    vocabulary (the drift rule test_semantic_neo4j_name_drift.py enforces for
    to_neo4j_name(), applied here to the emitted contract).
    """
    document = yaml.safe_load(render_contract())
    valid_values = {predicate.value for predicate in SemanticRelationshipType}

    seen_any = False
    for label, entry in document["labels"].items():
        contract = entry.get("contract")
        if not contract:
            continue
        for value in contract.get("semantic_types", []):
            seen_any = True
            assert value in valid_values, (
                f"label {label} lists semantic_type {value!r}, which is not a "
                "SemanticRelationshipType value"
            )
    assert seen_any, "no label emitted semantic_types — the Phase 2 surface vanished"


def test_semantic_edge_properties_match_the_write_path() -> None:
    """The declared property set equals the TYPED base build_semantic_merge emits.

    build_semantic_merge writes RelationshipMetadata.to_neo4j_properties() plus
    the semantic_type predicate. Re-deriving the expectation from the metadata
    dataclass here (not from the render) catches a generator hand-edited to
    diverge from the writer — a new typed metadata field must appear in both or
    fail. The free-form `properties` map is intentionally excluded from the
    declared set (it is unbounded); the open_extension block below is where the
    contract stays honest about it.
    """
    document = yaml.safe_load(render_contract())
    emitted = set(document["semantic_edge_properties"]["properties"])

    probe = RelationshipMetadata(
        source="registry",
        valid_from=datetime(2000, 1, 1),
        valid_until=datetime(2000, 1, 1),
        evidence=["registry"],
        notes="registry",
    )
    expected = set(probe.to_neo4j_properties()) | {"semantic_type"}

    assert emitted == expected, (
        "semantic_edge_properties drifted from RelationshipMetadata's write path: "
        f"contract has {emitted - expected} extra, missing {expected - emitted}"
    )
    # The generator's own helper must agree with the writer too.
    assert emitted == set(sanctioned_semantic_edge_properties())


def test_semantic_edge_properties_flag_the_open_extension() -> None:
    """The declared set is honest that it is NOT hard-closed.

    RelationshipMetadata.to_neo4j_properties() merges a free-form `properties`
    map verbatim (reachable via TripleBuilder.custom(properties=...)), so the
    typed set above cannot claim exhaustiveness. The open_extension block records
    that escape hatch so a Phase-4 consumer does not read the typed list as a
    closed universe (Codex #744 P2).
    """
    document = yaml.safe_load(render_contract())
    extension = document["semantic_edge_properties"]["open_extension"]
    assert extension["field"] == "properties"
    assert extension["exhaustive"] is False
