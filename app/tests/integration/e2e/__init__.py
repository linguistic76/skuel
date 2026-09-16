"""
End-to-End Tests
================

Whole workflows over the integration tier's testcontainer — event → background
worker → stored vector → search — rather than one service at a time. Fixtures:
this directory's conftest plus everything ``tests/integration/conftest.py``
provides by discovery.
"""
