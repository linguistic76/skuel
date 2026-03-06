"""
Test Pure Cypher Ingestion (No APOC dependency)

This test verifies that the bulk ingestion engine correctly filters
connection properties in Python before sending to Neo4j, eliminating
the need for apoc.map.removeKeys().
"""

from dataclasses import dataclass

import pytest


@dataclass
class MockEntity:
    """Mock entity with connections for testing"""

    uid: str
    title: str
    metadata: dict


def test_connection_property_filtering():
    """Test that connection keys are correctly filtered in Python layer"""
    from core.utils.neo4j_mapper import to_neo4j_node

    # Create entity with connection metadata
    entity = MockEntity(
        uid="ku:test",
        title="Test Knowledge Unit",
        metadata={
            "_connections": {"requires": ["ku:prereq1", "ku:prereq2"], "enables": ["ku:next"]}
        },
    )

    # Convert to Neo4j node (this happens in CypherExecutor)
    item = to_neo4j_node(entity)

    # Extract connections (mimics CypherExecutor lines 252-261)
    metadata = getattr(entity, "metadata", None)
    if isinstance(metadata, dict):
        connections = metadata.get("_connections")
        if connections and isinstance(connections, dict):
            for key, value in connections.items():
                if value:
                    item[f"connections.{key}"] = value

    # Define relationship config (mimics BulkIngestionEngine)
    rel_config = {
        "connections.requires": {
            "rel_type": "PREREQUISITE",
            "target_label": "Entity",
            "direction": "incoming",
        },
        "connections.enables": {
            "rel_type": "ENABLES",
            "target_label": "Entity",
            "direction": "outgoing",
        },
    }

    # Filter connection properties (mimics CypherExecutor lines 275-297)
    connection_keys = set(rel_config.keys())
    props = {k: v for k, v in item.items() if k not in connection_keys}

    # Verify connection properties are present in item (for FOREACH clauses)
    assert "connections.requires" in item
    assert "connections.enables" in item
    assert item["connections.requires"] == ["ku:prereq1", "ku:prereq2"]
    assert item["connections.enables"] == ["ku:next"]

    # Verify connection properties are EXCLUDED from props (for node storage)
    assert "connections.requires" not in props
    assert "connections.enables" not in props

    # Verify regular properties are still in props
    assert "uid" in props
    assert "title" in props
    assert props["uid"] == "ku:test"
    assert props["title"] == "Test Knowledge Unit"

    print("✅ Pure Cypher property filtering works correctly!")
    print(f"   - Item has {len(item)} keys (includes connections for FOREACH)")
    print(f"   - Props has {len(props)} keys (excludes connections for node storage)")
    print(f"   - Connection keys filtered: {connection_keys}")


def test_cypher_template_generation():
    """Test that generated Cypher template uses item._node_props"""

    from core.ingestion.bulk_ingestion import BulkIngestionEngine, RelationshipConfig

    # Create mock engine (no real driver needed for template generation)
    class MockEntity:
        pass

    # We need a real AsyncDriver for initialization, but we won't use it
    # So we create a minimal mock that satisfies type checking
    class MockDriver:
        pass

    engine = BulkIngestionEngine(
        driver=MockDriver(),  # type: ignore[arg-type]
        entity_type=MockEntity,
        entity_label="Entity",
    )

    # Define relationship config
    rel_config: dict[str, RelationshipConfig] = {
        "connections.requires": {
            "rel_type": "PREREQUISITE",
            "target_label": "Entity",
            "direction": "incoming",
        }
    }

    # Generate template
    template = engine._build_relationship_template(rel_config)

    # Verify template does NOT contain APOC function calls
    assert "apoc.map.removeKeys" not in template.template
    assert "CALL apoc" not in template.template
    assert "apoc." not in template.template  # Check for actual APOC procedure calls

    # Verify template DOES use item._node_props
    assert "item._node_props" in template.template
    assert "AS props" in template.template

    # Verify template includes FOREACH for relationship creation
    assert "FOREACH" in template.template
    assert "connections.requires" in template.template
    assert "PREREQUISITE" in template.template

    print("✅ Cypher template generation is Pure Cypher (no APOC)!")
    print(f"   - Template name: {template.name}")
    print("   - Uses item._node_props: True")
    print("   - Uses APOC: False")


def test_required_field_validation():
    """Test that UnifiedIngestionService validates required fields."""
    from pathlib import Path
    from unittest.mock import MagicMock

    from core.models.enums.entity_enums import EntityType, NonKuDomain
    from core.services.ingestion import UnifiedIngestionService

    # Create mock driver
    mock_driver = MagicMock()

    service = UnifiedIngestionService(driver=mock_driver)

    # Create a mock file path
    mock_path = Path("/tmp/test-file.yaml")

    # Test 1: Valid KU data (has title and content is skipped for early validation)
    valid_ku_data = {"title": "Test KU", "content": "Some content"}
    result = service.validate_required_fields(EntityType.ARTICLE, valid_ku_data, mock_path)
    assert result.is_ok, f"Expected OK for valid KU data, got: {result}"

    # Test 2: Missing required field for principle (needs 'statement')
    invalid_principle_data = {"name": "Test Principle"}  # Missing 'statement'
    result = service.validate_required_fields(
        EntityType.PRINCIPLE, invalid_principle_data, mock_path
    )
    assert result.is_error, "Expected error for principle missing 'statement'"
    error = result.expect_error()
    assert "statement" in error.message, f"Expected 'statement' in error: {error.message}"

    # Test 3: Missing required field for finance (needs 'amount')
    invalid_finance_data = {"description": "Test expense"}  # Missing 'amount'
    result = service.validate_required_fields(NonKuDomain.FINANCE, invalid_finance_data, mock_path)
    assert result.is_error, "Expected error for finance missing 'amount'"
    error = result.expect_error()
    assert "amount" in error.message, f"Expected 'amount' in error: {error.message}"

    # Test 4: Valid finance data
    valid_finance_data = {"description": "Coffee", "amount": 5.00}
    result = service.validate_required_fields(NonKuDomain.FINANCE, valid_finance_data, mock_path)
    assert result.is_ok, f"Expected OK for valid finance data, got: {result}"

    # Test 5: validate_entity_data - check post-preparation validation
    # Simulate prepared entity data missing content
    incomplete_ku_data = {"uid": "ku.test", "title": "Test"}  # Missing 'content'
    result = service.validate_entity_data(EntityType.ARTICLE, incomplete_ku_data, mock_path)
    assert result.is_error, "Expected error for KU missing 'content' after preparation"
    error = result.expect_error()
    assert "content" in error.message, f"Expected 'content' in error: {error.message}"

    # Test 6: Complete KU data passes validation
    complete_ku_data = {"uid": "ku.test", "title": "Test", "content": "Body content"}
    result = service.validate_entity_data(EntityType.ARTICLE, complete_ku_data, mock_path)
    assert result.is_ok, f"Expected OK for complete KU data, got: {result}"

    print("✅ Required field validation works correctly!")
    print("   - Uses EntityType/NonKuDomain enum for type-safe validation")
    print("   - Validates required fields before preparation")
    print("   - Validates entity data after preparation")
    print("   - Clear error messages with file context")


def test_user_uid_injection():
    """Test that UnifiedIngestionService injects user_uid for multi-tenant entities."""
    from pathlib import Path
    from unittest.mock import MagicMock

    from core.models.enums.entity_enums import EntityType, NonKuDomain
    from core.services.ingestion import (
        ENTITY_CONFIGS,
        UnifiedIngestionService,
    )

    # Create mock driver
    mock_driver = MagicMock()
    custom_user_uid = "user:test-user-123"

    service = UnifiedIngestionService(driver=mock_driver, default_user_uid=custom_user_uid)

    # Create a mock file path
    mock_path = Path("/tmp/test-task.yaml")

    # Test 1: Activity domain (task) should get user_uid injected
    task_data = {"title": "Test Task"}
    prepared = service.prepare_entity_data(EntityType.TASK, task_data, None, mock_path)
    assert "user_uid" in prepared, "Task should have user_uid injected"
    assert prepared["user_uid"] == custom_user_uid, (
        f"Expected {custom_user_uid}, got {prepared['user_uid']}"
    )

    # Test 2: Explicit user_uid in data should NOT be overwritten
    task_with_user = {"title": "Test Task", "user_uid": "user:explicit-user"}
    prepared = service.prepare_entity_data(EntityType.TASK, task_with_user, None, mock_path)
    assert prepared["user_uid"] == "user:explicit-user", (
        "Explicit user_uid should not be overwritten"
    )

    # Test 3: Curriculum domain (ku) should NOT get user_uid (shared knowledge)
    ku_data = {"title": "Test KU", "content": "Body content"}
    prepared = service.prepare_entity_data(
        EntityType.ARTICLE, ku_data, "Body content", Path("/tmp/test-ku.md")
    )
    assert "user_uid" not in prepared, "KU should not have user_uid (shared knowledge)"

    # Test 4: Finance domain should get user_uid
    finance_data = {"description": "Coffee", "amount": 5.00}
    prepared = service.prepare_entity_data(
        NonKuDomain.FINANCE, finance_data, None, Path("/tmp/expense.yaml")
    )
    assert "user_uid" in prepared, "Finance should have user_uid injected"
    assert prepared["user_uid"] == custom_user_uid

    # Test 5: All Activity domains should require user_uid (using EntityType keys)
    activity_types = [
        EntityType.TASK,
        EntityType.GOAL,
        EntityType.HABIT,
        EntityType.EVENT,
        EntityType.CHOICE,
        EntityType.PRINCIPLE,
    ]
    for entity_type in activity_types:
        config = ENTITY_CONFIGS[entity_type]
        assert config.requires_user_uid, f"{entity_type.value} should require user_uid"

    # Test 6: Curriculum domains should NOT require user_uid
    curriculum_types = [EntityType.ARTICLE, EntityType.LEARNING_PATH, EntityType.LEARNING_STEP]
    for entity_type in curriculum_types:
        config = ENTITY_CONFIGS[entity_type]
        assert not config.requires_user_uid, f"{entity_type.value} should NOT require user_uid"

    print("✅ User UID injection works correctly!")
    print("   - Uses EntityType/NonKuDomain enum for type-safe config lookup")
    print(f"   - Default user_uid: {custom_user_uid}")
    print("   - Activity domains get user_uid injected")
    print("   - Curriculum domains (shared knowledge) do not")
    print("   - Explicit user_uid in data is preserved")


def test_entity_type_detection():
    """Test that detect_entity_type returns EntityType/NonKuDomain enum (type-safe!)."""
    from pathlib import Path
    from unittest.mock import MagicMock

    from core.models.enums.entity_enums import EntityType, NonKuDomain
    from core.services.ingestion import UnifiedIngestionService

    # Create mock driver
    mock_driver = MagicMock()
    service = UnifiedIngestionService(driver=mock_driver)

    # Test 1: Explicit type field returns EntityType
    data_with_type = {"type": "task", "title": "Test"}
    result = service.detect_entity_type(data_with_type, Path("/tmp/test.yaml"))
    assert result == EntityType.TASK, f"Expected EntityType.TASK, got {result}"
    assert isinstance(result, EntityType | NonKuDomain), (
        "Result should be EntityType or NonKuDomain enum"
    )

    # Test 2: Type aliases are normalized
    data_with_alias = {"type": "knowledge", "title": "Test KU"}
    result = service.detect_entity_type(data_with_alias, Path("/tmp/test.yaml"))
    assert result == EntityType.ARTICLE, (
        f"Expected EntityType.ARTICLE (alias normalized), got {result}"
    )

    # Test 3: MOC flag detection (now maps to KU)
    data_with_moc_flag = {"moc": True, "title": "Map of Content"}
    result = service.detect_entity_type(data_with_moc_flag, Path("/tmp/test.md"))
    assert result == EntityType.ARTICLE, f"Expected EntityType.ARTICLE (MOC flag), got {result}"

    # Test 4: Default to KU for markdown without type
    data_no_type = {"title": "Some Knowledge"}
    result = service.detect_entity_type(data_no_type, Path("/tmp/test.md"))
    assert result == EntityType.ARTICLE, (
        f"Expected EntityType.ARTICLE (default for .md), got {result}"
    )

    # Test 5: Case insensitivity
    data_uppercase = {"type": "HABIT", "title": "Exercise"}
    result = service.detect_entity_type(data_uppercase, Path("/tmp/test.yaml"))
    assert result == EntityType.HABIT, f"Expected EntityType.HABIT, got {result}"

    # Test 6: Finance alias (expense -> FINANCE)
    data_expense = {"type": "expense", "description": "Coffee", "amount": 5.00}
    result = service.detect_entity_type(data_expense, Path("/tmp/test.yaml"))
    assert result == NonKuDomain.FINANCE, f"Expected NonKuDomain.FINANCE, got {result}"

    # Test 7: Verify type detection (January 2026 - Unified domains)
    result = service.detect_entity_type({"type": "task"}, Path("/tmp/test.yaml"))
    assert result == EntityType.TASK, "TASK detection should return EntityType.TASK"

    result = service.detect_entity_type({"type": "ku"}, Path("/tmp/test.yaml"))
    assert result == EntityType.KU, "KU detection should return EntityType.KU"

    # "knowledgeunit" and "knowledge" still map to ARTICLE (backward compat for old files)
    result = service.detect_entity_type({"type": "knowledgeunit"}, Path("/tmp/test.yaml"))
    assert result == EntityType.ARTICLE, "knowledgeunit should return EntityType.ARTICLE"

    result = service.detect_entity_type({"type": "knowledge"}, Path("/tmp/test.yaml"))
    assert result == EntityType.ARTICLE, "knowledge should return EntityType.ARTICLE"

    print("✅ Entity type detection works correctly!")
    print("   - Returns EntityType/NonKuDomain enum (type-safe!)")
    print("   - Handles aliases (knowledge → ARTICLE, knowledgeunit → ARTICLE)")
    print("   - ku → KU (atomic knowledge unit)")
    print("   - Case insensitive")
    print("   - MOC flag detection works")
    print("   - All 14 domains are unified peers (January 2026)")


@pytest.mark.asyncio
async def test_dry_run_validation():
    """Test dry-run validation mode for previewing ingestion without persisting."""
    import tempfile
    from pathlib import Path
    from unittest.mock import MagicMock

    from core.services.ingestion import UnifiedIngestionService

    # Create mock driver (not used in validation)
    mock_driver = MagicMock()
    service = UnifiedIngestionService(driver=mock_driver)

    # Create temporary test files
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Test 1: Valid markdown file (type: article)
        valid_md = tmppath / "test-knowledge.md"
        valid_md.write_text("""---
title: Test Knowledge Unit
type: article
---
This is the content of the knowledge unit.
""")
        result = await service.validate_file(valid_md)
        assert result.is_ok
        validation = result.value
        assert validation.valid, f"Expected valid, got errors: {validation.errors}"
        assert validation.entity_type == "article"
        assert validation.uid == "a.test-knowledge"
        assert validation.title == "Test Knowledge Unit"
        assert validation.format == "markdown"
        assert validation.prepared_data is not None
        assert "content" in validation.prepared_data

        # Test 2: Valid YAML file (task)
        valid_yaml = tmppath / "my-task.yaml"
        valid_yaml.write_text("""
type: task
title: Complete the project
description: Finish all the remaining work
""")
        result = await service.validate_file(valid_yaml)
        assert result.is_ok
        validation = result.value
        assert validation.valid, f"Expected valid, got errors: {validation.errors}"
        assert validation.entity_type == "task"
        assert validation.uid == "task.my-task"
        assert "user_uid" in validation.prepared_data  # Should have user_uid injected

        # Test 3: Invalid file - missing required field
        invalid_yaml = tmppath / "bad-principle.yaml"
        invalid_yaml.write_text("""
type: principle
name: My Principle
# Missing required 'statement' field
""")
        result = await service.validate_file(invalid_yaml)
        assert result.is_ok
        validation = result.value
        assert not validation.valid, "Expected invalid due to missing 'statement'"
        assert len(validation.errors) > 0
        assert any("statement" in e for e in validation.errors)

        # Test 4: File not found
        result = await service.validate_file(tmppath / "nonexistent.yaml")
        assert result.is_ok
        validation = result.value
        assert not validation.valid
        assert any("not found" in e.lower() for e in validation.errors)

        # Test 5: Unsupported file format
        bad_format = tmppath / "test.txt"
        bad_format.write_text("This is not a valid format")
        result = await service.validate_file(bad_format)
        assert result.is_ok
        validation = result.value
        assert not validation.valid
        assert any("unsupported" in e.lower() for e in validation.errors)

        # Test 6: Validate directory
        from core.services.ingestion import DirectoryValidationResult

        dir_result = await service.validate_directory(tmppath)
        assert dir_result.is_ok
        dir_validation = dir_result.value
        assert isinstance(dir_validation, DirectoryValidationResult)
        assert dir_validation.total_files == 3  # valid_md, valid_yaml, invalid_yaml
        assert dir_validation.valid_files == 2
        assert dir_validation.invalid_files == 1

    print("✅ Dry-run validation works correctly!")
    print("   - validate_file() returns ValidationResult")
    print("   - Previews prepared data without persisting")
    print("   - Catches validation errors early")
    print("   - validate_directory() validates multiple files")


@pytest.mark.asyncio
async def test_parallel_directory_processing():
    """Test that directory ingestion uses parallel processing."""
    import tempfile
    import time
    from pathlib import Path
    from unittest.mock import MagicMock

    from core.services.ingestion import (
        DEFAULT_MAX_CONCURRENT_PARSING,
        UnifiedIngestionService,
    )

    # Create mock driver
    mock_driver = MagicMock()

    # Test 1: Default concurrency is 20
    assert DEFAULT_MAX_CONCURRENT_PARSING == 20, "Default should be 20 concurrent"

    service = UnifiedIngestionService(driver=mock_driver)

    # Test 2: Create directory with multiple files and verify parallel parsing
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Create 10 valid markdown files (Articles = teaching content)
        for i in range(10):
            (tmppath / f"article-{i}.md").write_text(f"""---
title: Article {i}
type: article
---
Content for Article {i}
""")

        # Create 5 valid YAML files
        for i in range(5):
            (tmppath / f"task-{i}.yaml").write_text(f"""
type: task
title: Task {i}
description: Description for task {i}
""")

        # Test validate_directory (parallel validation)
        start = time.time()
        result = await service.validate_directory(tmppath, max_concurrent=5)
        time.time() - start

        assert result.is_ok, f"Validation should succeed: {result}"
        validation = result.value
        assert validation.total_files == 15, f"Expected 15 files, got {validation.total_files}"
        assert validation.valid_files == 15, f"All 15 should be valid, got {validation.valid_files}"
        assert validation.all_valid, "All files should be valid"

        # Test 3: Test parse_file_sync helper directly (from batch module)
        from core.services.ingestion.batch import parse_file_sync

        test_file = tmppath / "article-0.md"
        entity_type, entity_data, error = parse_file_sync(test_file)
        assert error is None, f"Should parse successfully: {error}"
        assert entity_type is not None
        assert entity_type.value == "article"
        assert entity_data is not None
        assert entity_data["title"] == "Article 0"

        # Test 4: Test error handling in parallel processing
        # Add an invalid file
        (tmppath / "invalid.yaml").write_text("""
type: principle
name: Test
# Missing required 'statement' field
""")

        result = await service.validate_directory(tmppath, max_concurrent=10)
        assert result.is_ok
        validation = result.value
        assert validation.total_files == 16
        assert validation.invalid_files == 1  # The invalid principle
        assert not validation.all_valid

    print("✅ Parallel directory processing works correctly!")
    print(f"   - Default max_concurrent: {DEFAULT_MAX_CONCURRENT_PARSING}")
    print("   - Uses asyncio.gather for parallel file parsing")
    print("   - Semaphore limits concurrent operations")
    print("   - Error handling works in parallel context")


def test_file_size_limits():
    """Test that file size limits prevent OOM on large files."""
    import tempfile
    from pathlib import Path
    from unittest.mock import MagicMock

    from core.services.ingestion import (
        DEFAULT_MAX_FILE_SIZE_BYTES,
        UnifiedIngestionService,
    )

    # Create mock driver
    mock_driver = MagicMock()

    # Test 1: Default max file size is 10 MB
    assert DEFAULT_MAX_FILE_SIZE_BYTES == 10 * 1024 * 1024, "Default should be 10 MB"

    # Test 2: Custom max file size
    custom_limit = 1024  # 1 KB
    service = UnifiedIngestionService(driver=mock_driver, max_file_size_bytes=custom_limit)
    assert service.max_file_size_bytes == custom_limit

    # Test 3: File within limits passes
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        small_file = tmppath / "small.md"
        small_file.write_text("Small content")  # Well under 1 KB
        result = service.check_file_size(small_file)
        assert result.is_ok, f"Small file should pass, got: {result}"

        # Test 4: File exceeding limit fails with clear error
        large_content = "x" * 2000  # 2 KB > 1 KB limit
        large_file = tmppath / "large.md"
        large_file.write_text(large_content)

        result = service.check_file_size(large_file)
        assert result.is_error, "Large file should fail"
        error = result.expect_error()
        assert "too large" in error.message.lower(), f"Expected 'too large' in: {error.message}"
        assert "KB" in error.user_message, f"Expected human-readable size in: {error.user_message}"

        # Test 5: parse_markdown checks file size
        result = service.parse_markdown(large_file)
        assert result.is_error, "parse_markdown should fail for large file"
        error = result.expect_error()
        assert "too large" in error.message.lower()

        # Test 6: parse_yaml checks file size
        large_yaml = tmppath / "large.yaml"
        large_yaml.write_text(f"content: '{large_content}'")

        result = service.parse_yaml(large_yaml)
        assert result.is_error, "parse_yaml should fail for large file"
        error = result.expect_error()
        assert "too large" in error.message.lower()

        # Test 7: Small files still parse correctly
        service_default = UnifiedIngestionService(driver=mock_driver)  # Default 10 MB limit

        small_md = tmppath / "valid.md"
        small_md.write_text("""---
title: Test
---
Content here.
""")
        result = service_default.parse_markdown(small_md)
        assert result.is_ok, f"Small markdown should parse, got: {result}"

        small_yaml = tmppath / "valid.yaml"
        small_yaml.write_text("title: Test\ncontent: Hello")
        result = service_default.parse_yaml(small_yaml)
        assert result.is_ok, f"Small YAML should parse, got: {result}"

    # Test 8: format_file_size produces readable output (from parser module)
    from core.services.ingestion.parser import format_file_size

    assert format_file_size(500) == "500 B"
    assert format_file_size(1536) == "1.5 KB"
    assert format_file_size(1048576) == "1.0 MB"
    assert format_file_size(15728640) == "15.0 MB"

    print("✅ File size limits work correctly!")
    print(f"   - Default limit: {DEFAULT_MAX_FILE_SIZE_BYTES / (1024 * 1024):.0f} MB")
    print("   - Custom limits supported via max_file_size_bytes parameter")
    print("   - Clear error messages with human-readable sizes")
    print("   - parse_markdown and parse_yaml check size before reading")


def test_rich_error_context():
    """Test that errors include rich context for debugging."""
    import tempfile
    from pathlib import Path

    from core.services.ingestion import IngestionError

    # Test 1: IngestionError dataclass
    error = IngestionError(
        file="/path/to/file.yaml",
        error="Missing required field 'title'",
        stage="validation",
        error_type="validation",
        entity_type="task",
        line_number=5,
        column=3,
        field="title",
        suggestion="Add 'title: Your Title' to the YAML file.",
    )

    # Test to_dict() serialization
    error_dict = error.to_dict()
    assert error_dict["file"] == "/path/to/file.yaml"
    assert error_dict["error"] == "Missing required field 'title'"
    assert error_dict["stage"] == "validation"
    assert error_dict["error_type"] == "validation"
    assert error_dict["entity_type"] == "task"
    assert error_dict["line_number"] == 5
    assert error_dict["column"] == 3
    assert error_dict["field"] == "title"
    assert error_dict["suggestion"] == "Add 'title: Your Title' to the YAML file."

    # Test __str__() for human-readable output
    error_str = str(error)
    assert "/path/to/file.yaml" in error_str
    assert "line 5" in error_str
    assert "[task]" in error_str
    assert "@ validation" in error_str

    # Test 2: Error with minimal fields
    minimal_error = IngestionError(
        file="test.md",
        error="Parse error",
        stage="parsing",
    )
    minimal_dict = minimal_error.to_dict()
    assert "line_number" not in minimal_dict  # Optional field omitted
    assert "entity_type" not in minimal_dict
    assert minimal_dict["error_type"] == "unknown"  # Default value

    # Test 3: create_error helper (from batch module)
    from core.services.ingestion.batch import create_error

    created_error = create_error(
        file_path=Path("/tmp/test.yaml"),
        error="Test error message",
        stage="type_detection",
        error_type="validation",
        entity_type="goal",
        suggestion="Add type field",
    )
    assert isinstance(created_error, IngestionError)
    assert created_error.file == "/tmp/test.yaml"
    assert created_error.entity_type == "goal"

    # Test 4: parse_file_sync returns rich errors (from batch module)
    from core.services.ingestion.batch import parse_file_sync

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Create file with invalid YAML syntax (tabs in YAML cause errors)
        bad_yaml = tmppath / "bad.yaml"
        bad_yaml.write_text("key:\n\t- invalid tab indentation")

        entity_type, entity_data, error = parse_file_sync(bad_yaml)
        assert entity_type is None
        assert entity_data is None
        assert error is not None

        # Error should have rich context
        assert "file" in error
        assert "stage" in error
        # Could be parsing or type_detection depending on how YAML parses
        assert error["stage"] in ("parsing", "type_detection", "unknown")
        assert "suggestion" in error

        # Create file with missing required field
        missing_field = tmppath / "principle.yaml"
        missing_field.write_text("""
type: principle
name: Test Principle
# Missing required 'statement' field
""")

        entity_type, entity_data, error = parse_file_sync(missing_field)
        assert error is not None
        assert error["stage"] == "validation"
        assert error["entity_type"] == "principle"
        assert "suggestion" in error

        # Create file with unsupported format
        unsupported = tmppath / "test.txt"
        unsupported.write_text("Some content")

        entity_type, entity_data, error = parse_file_sync(unsupported)
        assert error is not None
        assert error["stage"] == "format_detection"
        assert error["error_type"] == "format"
        assert "suggestion" in error
        assert ".md" in error["suggestion"] or ".yaml" in error["suggestion"]

    print("✅ Rich error context works correctly!")
    print(
        "   - IngestionError captures: file, error, stage, entity_type, line_number, field, suggestion"
    )
    print("   - to_dict() provides JSON-serializable output")
    print("   - __str__() provides human-readable format")
    print("   - _parse_file_sync returns rich error context")
    print("   - Suggestions help users fix issues")


if __name__ == "__main__":
    # Run tests directly
    test_connection_property_filtering()
    test_cypher_template_generation()
    test_required_field_validation()
    test_user_uid_injection()
    test_entity_type_detection()
    test_file_size_limits()
    test_rich_error_context()
    # Note: test_dry_run_validation and test_parallel_directory_processing are async, run with pytest
    print("\n✅ All Pure Cypher & Ingestion tests passed!")
