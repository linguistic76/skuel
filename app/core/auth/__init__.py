"""
Core Authentication Utilities
==============================

Framework-free authentication primitives:
- Password hashing and verification (bcrypt)
- Graph-native authentication service (Neo4j sessions)

HTTP-coupled auth (session management, role decorators) lives in:
    adapters/inbound/auth/
"""

from core.auth.graph_auth import GraphAuthService
from core.auth.password import BCRYPT_ROUNDS, hash_password, verify_password

__all__ = [
    "BCRYPT_ROUNDS",
    "GraphAuthService",
    "hash_password",
    "verify_password",
]
