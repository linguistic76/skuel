"""
File Permission Wrapper
========================

Security wrapper to restrict file access to only explicitly allowed paths.
Implements strict permission mode for tools like Claude Code.

This ensures that only files within the configured vault root and
explicitly opened files are accessible.
"""

__version__ = "1.0"

import os
from pathlib import Path

from core.config.settings import get_vault_config
from core.utils.logging import get_logger

logger = get_logger("skuel.file_permissions")


class FilePermissionManager:
    """
    Manages file access permissions for the application.

    In strict mode, only explicitly allowed files are accessible.
    This prevents tools from accessing files outside the vault.
    """

    def __init__(self) -> None:
        """Initialize permission manager with vault configuration."""
        self.vault_config = get_vault_config()
        self.vault_root = Path(self.vault_config.vault_root)
        self.explicitly_opened: set[Path] = set()
        self.permission_mode = os.getenv("VAULT_PERMISSION_MODE", "strict")

        logger.info(
            f"FilePermissionManager initialized - mode: {self.permission_mode}, "
            f"vault: {self.vault_root}"
        )

    def is_path_allowed(self, file_path: Path | str) -> bool:
        """
        Check if a path is allowed for access.

        Args:
            file_path: Path to check

        Returns:
            True if access is allowed, False otherwise
        """
        path = Path(file_path).resolve()

        # Always allow access to vault subdirectories
        if self._is_in_vault(path):
            # Check if it's in an allowed subdirectory
            relative = path.relative_to(self.vault_root)
            subdir = str(relative).split("/")[0] if "/" in str(relative) else str(relative)

            if subdir in self.vault_config.allowed_subdirs:
                return True

        # In strict mode, check if file was explicitly opened
        if self.permission_mode == "strict":
            return path in self.explicitly_opened

        # In permissive mode, allow vault access
        return self._is_in_vault(path)

    def _is_in_vault(self, path: Path) -> bool:
        """Check if path is within vault root."""
        try:
            path.resolve().relative_to(self.vault_root.resolve())
            return True
        except ValueError:
            return False

    def open_file(self, file_path: Path | str):
        """
        Mark a file as explicitly opened.

        Args:
            file_path: Path to mark as opened
        """
        path = Path(file_path).resolve()
        self.explicitly_opened.add(path)
        logger.debug(f"File explicitly opened: {path}")

    def close_file(self, file_path: Path | str):
        """
        Remove a file from explicitly opened set.

        Args:
            file_path: Path to remove from opened set
        """
        path = Path(file_path).resolve()
        self.explicitly_opened.discard(path)
        logger.debug(f"File closed: {path}")

    def validate_read(self, file_path: Path | str) -> Path | None:
        """
        Validate a file read operation.

        Args:
            file_path: Path to validate

        Returns:
            Resolved path if allowed, None if denied

        Raises:
            PermissionError: If access is denied in strict mode
        """
        path = Path(file_path).resolve()

        if not self.is_path_allowed(path):
            error_msg = f"Access denied: {path} is not in allowed paths"
            logger.warning(error_msg)

            if self.permission_mode == "strict":
                raise PermissionError(error_msg)
            return None

        return path

    def validate_write(self, file_path: Path | str) -> Path | None:
        """
        Validate a file write operation.

        Args:
            file_path: Path to validate

        Returns:
            Resolved path if allowed, None if denied

        Raises:
            PermissionError: If access is denied
        """
        path = Path(file_path).resolve()

        # Writes are only allowed within vault
        if not self._is_in_vault(path):
            error_msg = f"Write access denied: {path} is outside vault root"
            logger.warning(error_msg)
            raise PermissionError(error_msg)

        # Check if in allowed subdirectory
        relative = path.relative_to(self.vault_root)
        subdir = str(relative).split("/")[0] if "/" in str(relative) else str(relative)

        if subdir not in self.vault_config.allowed_subdirs:
            error_msg = f"Write access denied: {subdir} is not an allowed subdirectory"
            logger.warning(error_msg)
            raise PermissionError(error_msg)

        return path

    def get_neo4j_import_path(self) -> Path:
        """Get the Neo4j import directory path."""
        return self.vault_root / self.vault_config.neo4j_import_dir

    def get_neo4j_export_path(self) -> Path:
        """Get the Neo4j export directory path."""
        return self.vault_root / self.vault_config.neo4j_export_dir

    def ensure_directories(self):
        """Ensure all required directories exist."""
        # Create vault root if needed
        self.vault_root.mkdir(parents=True, exist_ok=True)

        # Create allowed subdirectories
        for subdir in self.vault_config.allowed_subdirs:
            (self.vault_root / subdir).mkdir(parents=True, exist_ok=True)

        logger.info("Ensured all vault directories exist")


# Global instance
_permission_manager: FilePermissionManager | None = None


def get_permission_manager() -> FilePermissionManager:
    """Get or create the global permission manager instance."""
    global _permission_manager
    if _permission_manager is None:
        _permission_manager = FilePermissionManager()
        _permission_manager.ensure_directories()
    return _permission_manager


def validate_file_read(file_path: Path | str) -> Path | None:
    """
    Validate a file read operation.

    Args:
        file_path: Path to validate,

    Returns:
        Resolved path if allowed, None if denied
    """
    return get_permission_manager().validate_read(file_path)


def validate_file_write(file_path: Path | str) -> Path | None:
    """
    Validate a file write operation.

    Args:
        file_path: Path to validate,

    Returns:
        Resolved path if allowed, None if denied
    """
    return get_permission_manager().validate_write(file_path)


def mark_file_opened(file_path: Path | str):
    """Mark a file as explicitly opened."""
    get_permission_manager().open_file(file_path)


def mark_file_closed(file_path: Path | str):
    """Mark a file as closed."""
    get_permission_manager().close_file(file_path)
