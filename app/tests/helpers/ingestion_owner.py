"""The owner a test run names for ingestion.

No account stands in for an unnamed owner (ADR-091 S9): the app refuses to boot
without ``SKUEL_DEFAULT_USER_UID``, and ``UnifiedIngestionService`` takes its
default owner as a required argument. A test that builds the service passes this one
unless it names an owner of its own, and ``tests/conftest.py`` sets
``SKUEL_DEFAULT_USER_UID`` to it, so the owner never differs by machine. The integration tier seeds its ``:User`` node
(``ensure_test_users``): the bulk door refuses an owner with no account.
"""

from core.models.type_hints import UserUID

INGESTION_TEST_OWNER = UserUID("user_test_ingestion")
