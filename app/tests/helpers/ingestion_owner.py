"""The owner a test run names for ingestion.

No account stands in for an unnamed owner (ADR-091 S9): the app refuses to boot
without ``SKUEL_DEFAULT_USER_UID``, and ``UnifiedIngestionService`` takes its
default owner as a required argument. A test that builds the service passes this one
unless it names an owner of its own, and ``tests/conftest.py`` sets
``SKUEL_DEFAULT_USER_UID`` and ``SKUEL_CONTENT_VAULT_OWNER`` to it, so the owner never
differs by machine. The integration tier seeds its ``:User`` node
(``ensure_test_users``): the bulk door refuses an owner with no account.

It has a user uid's shape, ``user_{16 hex}`` — boot refuses a configured owner
that is not one (``VaultConfig.validate_owners``).
"""

from core.models.type_hints import UserUID

INGESTION_TEST_OWNER = UserUID("user_7e57000000000000")
