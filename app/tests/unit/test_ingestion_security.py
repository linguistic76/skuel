"""
Security Tests for Ingestion Path Validation
==============================================

Pure unit tests for _validate_ingestion_path — no Neo4j needed.
Tests path traversal prevention and allowed paths enforcement.

Corresponds to manual Test 8 in tests/SYNC_SYSTEM_TEST_PLAN.md.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from adapters.inbound.ingestion_api import _validate_ingestion_path


# ============================================================================
# TEST 1: Empty path is rejected
# ============================================================================


def test_empty_path_rejected():
    """Empty path string should fail validation."""
    result = _validate_ingestion_path("")
    assert result.is_error
    assert "required" in result.expect_error().message.lower()


def test_none_path_rejected():
    """None path should fail validation."""
    result = _validate_ingestion_path(None)
    assert result.is_error


# ============================================================================
# TEST 2: Path traversal attacks are blocked
# ============================================================================


def test_path_traversal_blocked_when_allowed_paths_set(monkeypatch, tmp_path):
    """Path traversal via ../../ should be blocked when allowed paths are configured."""
    allowed_dir = tmp_path / "vault"
    allowed_dir.mkdir()

    monkeypatch.setenv("SKUEL_INGESTION_ALLOWED_PATHS", str(allowed_dir))

    # Attempt traversal
    result = _validate_ingestion_path(f"{allowed_dir}/../../etc/passwd")
    assert result.is_error
    assert "outside allowed" in result.expect_error().message.lower()


def test_path_traversal_resolves_to_outside_allowed(monkeypatch, tmp_path):
    """Even if path starts within allowed dir, traversal should resolve and check."""
    allowed_dir = tmp_path / "vault"
    allowed_dir.mkdir()

    monkeypatch.setenv("SKUEL_INGESTION_ALLOWED_PATHS", str(allowed_dir))

    # Path that looks like it's in vault but traverses out
    result = _validate_ingestion_path(f"{allowed_dir}/../secret")
    assert result.is_error


# ============================================================================
# TEST 3: Allowed paths are accepted
# ============================================================================


def test_allowed_path_succeeds(monkeypatch, tmp_path):
    """Path within allowed directories should succeed."""
    allowed_dir = tmp_path / "vault"
    allowed_dir.mkdir()

    monkeypatch.setenv("SKUEL_INGESTION_ALLOWED_PATHS", str(allowed_dir))

    result = _validate_ingestion_path(str(allowed_dir))
    assert result.is_ok
    assert result.value == allowed_dir.resolve()


def test_allowed_subdirectory_succeeds(monkeypatch, tmp_path):
    """Subdirectory of allowed path should succeed."""
    allowed_dir = tmp_path / "vault"
    sub_dir = allowed_dir / "docs" / "ku"
    sub_dir.mkdir(parents=True)

    monkeypatch.setenv("SKUEL_INGESTION_ALLOWED_PATHS", str(allowed_dir))

    result = _validate_ingestion_path(str(sub_dir))
    assert result.is_ok


# ============================================================================
# TEST 4: Multiple allowed paths (colon-separated)
# ============================================================================


def test_multiple_allowed_paths(monkeypatch, tmp_path):
    """Multiple colon-separated allowed paths should all work."""
    dir_a = tmp_path / "vault_a"
    dir_b = tmp_path / "vault_b"
    dir_a.mkdir()
    dir_b.mkdir()

    monkeypatch.setenv("SKUEL_INGESTION_ALLOWED_PATHS", f"{dir_a}:{dir_b}")

    # Both should succeed
    result_a = _validate_ingestion_path(str(dir_a))
    assert result_a.is_ok

    result_b = _validate_ingestion_path(str(dir_b))
    assert result_b.is_ok

    # Different path should fail
    result_c = _validate_ingestion_path(str(tmp_path / "unauthorized"))
    assert result_c.is_error


# ============================================================================
# TEST 5: No allowed paths env var = any path allowed (admin-only)
# ============================================================================


def test_no_allowed_paths_env_allows_any(monkeypatch, tmp_path):
    """When SKUEL_INGESTION_ALLOWED_PATHS is not set, any absolute path is allowed."""
    monkeypatch.delenv("SKUEL_INGESTION_ALLOWED_PATHS", raising=False)

    result = _validate_ingestion_path(str(tmp_path))
    assert result.is_ok


def test_resolved_path_returned(monkeypatch, tmp_path):
    """Returned path should be resolved (no symlinks or ..)."""
    monkeypatch.delenv("SKUEL_INGESTION_ALLOWED_PATHS", raising=False)

    # Path with .. components
    path_with_dots = f"{tmp_path}/subdir/../"
    result = _validate_ingestion_path(path_with_dots)
    assert result.is_ok
    assert ".." not in str(result.value)
