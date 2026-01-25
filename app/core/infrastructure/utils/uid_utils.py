"""
UID Utilities
=============

Centralized UID generation and validation for all domain models.
Ensures consistent identifier format across the system.
"""

import re
import uuid


class UIDGenerator:
    """Centralized UID generation with various strategies"""

    @staticmethod
    def generate_uid(prefix: str, length: int = 8) -> str:
        """
        Generate a UID with prefix and random suffix.

        Args:
            prefix: Domain prefix (e.g., 'ku', 'task', 'user')
            length: Length of random suffix

        Returns:
            UID like 'ku_a3f2b891'
        """
        suffix = uuid.uuid4().hex[:length]
        return f"{prefix}_{suffix}"

    @staticmethod
    def generate_sequential_uid(prefix: str, counter: int) -> str:
        """
        Generate a sequential UID for testing or imports.

        Args:
            prefix: Domain prefix
            counter: Sequential number

        Returns:
            UID like 'ku_000042'
        """
        return f"{prefix}_{counter:06d}"

    @staticmethod
    def generate_hierarchical_uid(parent_uid: str, child_type: str) -> str:
        """
        Generate a UID that shows hierarchy.

        Args:
            parent_uid: Parent's UID
            child_type: Type of child entity

        Returns:
            UID like 'ku.math.algebra_a3f2b8'
        """
        suffix = uuid.uuid4().hex[:6]
        return f"{parent_uid}.{child_type}_{suffix}"

    @staticmethod
    def is_valid_uid(uid: str) -> bool:
        """
        Validate UID format.

        Args:
            uid: UID to validate

        Returns:
            True if valid format
        """
        # Allow dots for hierarchical UIDs
        pattern = r"^[a-z]+[a-z0-9._]*$"
        return bool(re.match(pattern, uid))

    @staticmethod
    def extract_prefix(uid: str) -> str:
        """
        Extract the prefix from a UID.

        Args:
            uid: UID to parse

        Returns:
            Prefix part (e.g., 'ku' from 'ku_123')
        """
        if "_" in uid:
            return uid.split("_")[0]
        elif "." in uid:
            return uid.split(".")[0]
        return uid
