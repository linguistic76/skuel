"""The composition root's backends, built for a test.

A test that needs a backend ``create_all_backends`` builds (``services_bootstrap/_backends.py``)
takes it from that one constructor, never from a copy of its arguments — so the test
runs the class, label, base label and entity class production runs.
``tests/unit/test_production_backend_census.py`` fails a test that builds one another way.

``build_production_backends(driver)["tasks_backend"]`` over any driver — the shared
container's, a test's own graph, a mock; the integration ``production_backends``
fixture is the same dict over ``neo4j_driver``.
"""

from typing import Any

from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.ports import QueryExecutor
from services_bootstrap._backends import create_all_backends


def build_production_backends(
    driver: Any,  # boundary: neo4j AsyncDriver or a test double
    executor: QueryExecutor | None = None,
) -> dict[str, Any]:  # boundary: create_all_backends' named heterogeneous backends
    """Every backend ``create_all_backends`` builds, over ``driver``.

    ``executor`` defaults to a ``Neo4jQueryExecutor`` over the same driver, as the
    composition root builds it; a unit test passes its own fake.
    """
    return create_all_backends(driver, executor or Neo4jQueryExecutor(driver))
