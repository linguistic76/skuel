"""
Auth Models Package
===================

Graph-native authentication models for SKUEL.

This package provides frozen dataclasses for:
- Session: User session stored as Neo4j node
- AuthEvent: Audit trail events stored as Neo4j nodes
- PasswordResetToken: Admin-generated password reset tokens

Design Philosophy:
- Full graph-native: All auth state lives in Neo4j
- Immutable models: Frozen dataclasses for thread safety
- Audit trail: Every auth action creates an AuthEvent

See Also:
- ADR: Graph-Native Authentication System
- /core/auth/graph_auth.py: Main authentication service
- /adapters/persistence/neo4j/session_backend.py: Neo4j persistence
"""

from core.models.auth.auth_event import AuthEvent, AuthEventType
from core.models.auth.password_reset_token import PasswordResetToken
from core.models.auth.session import Session

__all__ = [
    "AuthEvent",
    "AuthEventType",
    "PasswordResetToken",
    "Session",
]
