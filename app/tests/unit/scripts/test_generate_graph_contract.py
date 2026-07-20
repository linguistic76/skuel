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
from pathlib import Path

import yaml

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from generate_graph_contract import (  # type: ignore[import-not-found]
    ARTIFACT_PATH,
    render_contract,
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
    """Baselined names are known bugs — they must appear ONLY under findings."""
    document = yaml.safe_load(render_contract())

    finding_names = set(document["findings"])
    assert finding_names, "SKUEL030 baseline is non-empty today; empty means a gather bug"
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
