"""
Unit Tests for the Resource write side (Arc D, ruling 2026-07-03)
==================================================================

Resource became vault-ingestible: descriptor .md files carry curated metadata
(``type: resource``), and ``resource_uids:`` on PathStep/Ku YAML creates
``CITES_RESOURCE`` edges via the relationship registry — mirroring the
``exercise_uids`` / #496 pattern. Raw book texts stay walled on disk
(descriptor-only ruling; see services_bootstrap/compose.py Resources/ wall).

Test Categories:
1. Type detection (explicit ``type: resource``; never sniff)
2. ENTITY_CONFIGS schema (valid descriptor, missing-type rejection, UID prefix)
3. Registry edge wiring (PS + Ku ``resource_uids`` → CITES_RESOURCE)
4. Batch preparation — the #496 skip-field twin (mapper strips
   ``resource_uids``; the batch preparer must restore it for the edge MERGE)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.models.enums.entity_enums import EntityType
from core.services.ingestion.config import ENTITY_CONFIGS
from core.services.ingestion.detector import detect_entity_type
from core.services.ingestion.preparer import prepare_entity_data
from core.services.ingestion.validator import validate_entity_data, validate_uid_format

_FILE = Path("resource_atlas-of-the-heart.md")

_DESCRIPTOR = {
    "type": "resource",
    "uid": "resource:atlas-of-the-heart",
    "title": "Atlas of the Heart",
    "description": "Mapping 87 emotions and experiences that define being human.",
    "author": "Brené Brown",
    "publisher": "Random House",
    "publication_year": 2021,
    "isbn": "978-0399592553",
    "media_type": "book",
}


# ============================================================================
# 1. TYPE DETECTION
# ============================================================================


def test_explicit_resource_type_detected() -> None:
    assert detect_entity_type({"type": "resource"}, _FILE) is EntityType.RESOURCE


def test_markdown_without_type_rejected() -> None:
    """Never-sniff: a raw book .md with no ``type:`` frontmatter is not a
    Resource — the detector requires an explicit type (One Path Forward)."""
    with pytest.raises(ValueError, match="no 'type:' field"):
        detect_entity_type({}, Path("Transcend.md"))


# ============================================================================
# 2. ENTITY_CONFIGS SCHEMA
# ============================================================================


def test_resource_config_shape() -> None:
    config = ENTITY_CONFIGS[EntityType.RESOURCE]
    assert config.entity_label == "Resource"
    assert config.uid_prefix == "resource"
    assert config.required_fields == ("title",)
    assert config.embeddable is True  # EMBEDDING_FIELD_MAPS covers RESOURCE
    assert config.extracts_body_content is True  # descriptor body → content
    assert config.requires_user_uid is False  # admin-curated shared content


def test_valid_descriptor_prepares_and_validates() -> None:
    prepared = prepare_entity_data(EntityType.RESOURCE, dict(_DESCRIPTOR), None, _FILE)
    assert prepared["uid"] == "resource.atlas-of-the-heart"  # colon normalized
    assert prepared["entity_type"] == "resource"
    assert prepared["author"] == "Brené Brown"
    result = validate_entity_data(EntityType.RESOURCE, prepared, _FILE)
    assert result.is_ok


def test_descriptor_body_becomes_content() -> None:
    prepared = prepare_entity_data(
        EntityType.RESOURCE, dict(_DESCRIPTOR), "A short annotation.", _FILE
    )
    assert prepared["content"] == "A short annotation."


def test_uid_prefix_enforced() -> None:
    bad = dict(_DESCRIPTOR, uid="res:atlas-of-the-heart")
    result = validate_uid_format(EntityType.RESOURCE, bad, _FILE)
    assert result.is_error
    assert "resource." in str(result.expect_error().message)


def test_uid_accepts_both_separators() -> None:
    for uid in ("resource:transcend", "resource.transcend"):
        result = validate_uid_format(EntityType.RESOURCE, dict(_DESCRIPTOR, uid=uid), _FILE)
        assert result.is_ok, uid


def test_missing_title_falls_back_to_filename() -> None:
    """Title is required post-preparation but the preparer derives it from the
    filename when absent (the validator deliberately skips title pre-prepare) —
    so a title-less descriptor still ingests, with a humanized-stem title."""
    data = {k: v for k, v in _DESCRIPTOR.items() if k != "title"}
    prepared = prepare_entity_data(EntityType.RESOURCE, data, None, _FILE)
    assert prepared["title"] == "Resource_Atlas Of The Heart"  # humanized stem
    assert validate_entity_data(EntityType.RESOURCE, prepared, _FILE).is_ok


# ============================================================================
# 3. REGISTRY EDGE WIRING
# ============================================================================


def test_ps_rel_config_maps_resource_uids_to_cites_resource() -> None:
    rel_config = ENTITY_CONFIGS[EntityType.PATH_STEP].relationship_config
    assert rel_config is not None
    entry = rel_config.get("resource_uids")
    assert entry is not None
    assert entry["rel_type"] == "CITES_RESOURCE"
    assert entry["target_label"] == "Resource"
    assert entry["direction"] == "outgoing"


def test_ku_rel_config_maps_resource_uids_to_cites_resource() -> None:
    """The Askesis read query traverses CITES_RESOURCE from both PathSteps and
    KUs — the registry makes Ku-authored ``resource_uids:`` free."""
    rel_config = ENTITY_CONFIGS[EntityType.KU].relationship_config
    assert rel_config is not None
    entry = rel_config.get("resource_uids")
    assert entry is not None
    assert entry["rel_type"] == "CITES_RESOURCE"
    assert entry["target_label"] == "Resource"


def test_ps_normalizes_resource_uid_list() -> None:
    """Authored ``resource:...`` colon UIDs normalize to dots so the edge
    MERGE matches the stored node UID."""
    data = {
        "type": "PathStep",
        "uid": "ps:mindfulness:test",
        "title": "Test",
        "resource_uids": ["resource:transcend"],
    }
    prepared = prepare_entity_data(EntityType.PATH_STEP, data, None, Path("ps_test.md"))
    assert prepared["resource_uids"] == ["resource.transcend"]


# ============================================================================
# 4. BATCH ITEM PREPARATION — the #496 skip-field twin
# ============================================================================


def test_batch_items_keep_resource_uids_dropped_by_mapper() -> None:
    """to_neo4j_node strips RELATIONSHIP_SKIP_FIELDS (``resource_uids`` is in
    the skip set), but the bulk-upsert Cypher template reads that key off the
    item to MERGE the CITES_RESOURCE edges. prepare_batch_items must restore
    it onto the item while keeping it out of _node_props — the exact #496 bug
    shape (silently-zero edges)."""
    from adapters.persistence.neo4j.batch_preparer import prepare_batch_items

    rel_config = ENTITY_CONFIGS[EntityType.PATH_STEP].relationship_config
    assert rel_config is not None and "resource_uids" in rel_config

    entity = {
        "uid": "ps.test.step",
        "entity_type": "path_step",
        "title": "Test Step",
        "resource_uids": ["resource.transcend"],  # in the mapper's skip set
        "uses_kus": ["ku.test.one"],  # NOT in the skip set (control)
    }
    item = prepare_batch_items([entity], rel_config=rel_config)[0]

    assert item["resource_uids"] == ["resource.transcend"]
    assert item["uses_kus"] == ["ku.test.one"]
    assert "resource_uids" not in item["_node_props"]
    assert "uses_kus" not in item["_node_props"]


# ============================================================================
# 5. UI SAFETY — source_url scheme allowlist (Kody #502, stored-XSS class)
# ============================================================================


def test_safe_external_url_allows_http_https() -> None:
    from ui.primitives import safe_external_url

    assert safe_external_url("https://hypermedia.systems") == "https://hypermedia.systems"
    assert safe_external_url("http://example.org/x") == "http://example.org/x"
    assert safe_external_url("  https://example.org  ") == "https://example.org"


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "JavaScript:alert(1)",
        " \tjavascript:alert(1)",
        "data:text/html;base64,PHNjcmlwdD4=",
        "vbscript:x",
        "//evil.example",
        "ftp://example.org",
        "",
        None,
    ],
)
def test_safe_external_url_rejects_unsafe_schemes(url: str | None) -> None:
    from ui.primitives import safe_external_url

    assert safe_external_url(url) is None


def test_ku_batch_items_keep_resource_uids() -> None:
    """Ku ingestion gains its first rel_config with this arc — pin the same
    seam for the Ku door."""
    from adapters.persistence.neo4j.batch_preparer import prepare_batch_items

    rel_config = ENTITY_CONFIGS[EntityType.KU].relationship_config
    assert rel_config is not None and "resource_uids" in rel_config

    entity = {
        "uid": "ku.test.concept",
        "entity_type": "ku",
        "title": "Test Concept",
        "resource_uids": ["resource.atlas-of-the-heart"],
    }
    item = prepare_batch_items([entity], rel_config=rel_config)[0]

    assert item["resource_uids"] == ["resource.atlas-of-the-heart"]
    assert "resource_uids" not in item["_node_props"]
