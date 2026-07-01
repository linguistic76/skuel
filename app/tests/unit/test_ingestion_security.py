"""
Security Tests for Ingestion Path Validation
==============================================

Pure unit tests for `_validate_ingestion_path` — no Neo4j needed.
Tests path traversal prevention, allowlist enforcement, and the
default-deny fallback chain (SKUEL_INGESTION_ALLOWED_PATHS → INGESTION_PATH
→ fail closed).

Corresponds to manual Test 8 in tests/SYNC_SYSTEM_TEST_PLAN.md.
"""

from __future__ import annotations

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
# TEST 5: Default-deny fallback chain
# ============================================================================
# Was previously "no env var = any path allowed (admin-only)". That was the
# bug — admin role gates request _ownership_, not _filesystem reach_. Even an
# authenticated admin should be confined to declared roots. The new contract:
#
#   SKUEL_INGESTION_ALLOWED_PATHS  (explicit override) > INGESTION_PATH (vault
#   default) > fail closed.


def test_neither_env_var_set_fails_closed(monkeypatch, tmp_path):
    """With NO allowlist env var set, every path is rejected (default-deny)."""
    monkeypatch.delenv("SKUEL_INGESTION_ALLOWED_PATHS", raising=False)
    monkeypatch.delenv("INGESTION_PATH", raising=False)

    result = _validate_ingestion_path(str(tmp_path))

    assert result.is_error
    msg = result.expect_error().message.lower()
    assert "allowlist" in msg or "not configured" in msg


def test_ingestion_path_used_as_fallback_allowlist(monkeypatch, tmp_path):
    """When SKUEL_INGESTION_ALLOWED_PATHS is unset, INGESTION_PATH defines the only allowed root."""
    vault = tmp_path / "vault"
    vault.mkdir()

    monkeypatch.delenv("SKUEL_INGESTION_ALLOWED_PATHS", raising=False)
    monkeypatch.setenv("INGESTION_PATH", str(vault))

    # Inside the vault → allowed
    inside = vault / "ku" / "topic.md"
    inside.parent.mkdir(parents=True)
    inside.touch()
    assert _validate_ingestion_path(str(inside)).is_ok

    # Outside the vault → rejected
    outside = tmp_path / "elsewhere" / "secret.md"
    outside.parent.mkdir(parents=True)
    outside.touch()
    assert _validate_ingestion_path(str(outside)).is_error


def test_explicit_allowlist_takes_precedence_over_ingestion_path(monkeypatch, tmp_path):
    """SKUEL_INGESTION_ALLOWED_PATHS overrides INGESTION_PATH when both are set."""
    explicit = tmp_path / "explicit_root"
    vault = tmp_path / "vault"
    explicit.mkdir()
    vault.mkdir()

    monkeypatch.setenv("SKUEL_INGESTION_ALLOWED_PATHS", str(explicit))
    monkeypatch.setenv("INGESTION_PATH", str(vault))

    # Inside the explicit root → allowed
    assert _validate_ingestion_path(str(explicit / "a.md")).is_ok

    # Inside the (now-shadowed) vault → rejected
    assert _validate_ingestion_path(str(vault / "b.md")).is_error


def test_resolved_path_returned(monkeypatch, tmp_path):
    """Returned path should be resolved (no symlinks or `..`)."""
    monkeypatch.delenv("SKUEL_INGESTION_ALLOWED_PATHS", raising=False)
    monkeypatch.setenv("INGESTION_PATH", str(tmp_path))

    sub = tmp_path / "subdir"
    sub.mkdir()

    path_with_dots = f"{sub}/../"
    result = _validate_ingestion_path(path_with_dots)
    assert result.is_ok
    assert ".." not in str(result.value)


def test_symlink_file_rejected_before_resolution(tmp_path):
    """A symlinked file path is rejected on the original path, so /api/ingest/file
    can't slip an external target past the vault symlink boundary (which
    _validate_ingestion_path would otherwise resolve away)."""
    from adapters.inbound.ingestion_api import _reject_symlink_file

    target = tmp_path / "real.md"
    target.write_text("x")
    link = tmp_path / "link.md"
    link.symlink_to(target)

    assert _reject_symlink_file(str(link)).is_error
    assert _reject_symlink_file(str(target)).is_ok
    assert _reject_symlink_file(None).is_ok
