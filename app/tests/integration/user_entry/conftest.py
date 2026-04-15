"""
UserEntry Integration Test Fixtures — ADR-054
==============================================

Scaffolding for the UserEntry integration suite. Inherits the
session-scoped ``neo4j_container`` / ``neo4j_uri`` / driver fixtures
from ``tests/integration/conftest.py``; this module is the place to add
UserEntry-specific factory fixtures as Commit 3 lands the flow tests:

- ``test_submit_to_review_cycle.py``
- ``test_journal_audio_pipeline.py``
- ``test_review_queue_graph_pattern.py``
- ``test_revision_edge_property.py``

Keep domain-agnostic plumbing in the parent conftest; keep UserEntry
builders (entry factory, group+exercise seeding, etc.) here.
"""

from __future__ import annotations
