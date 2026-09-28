"""A process that writes an activity report and asks the cooldown about it — a probe.

Run by ``tests/integration/test_cooldown_under_the_pin.py`` as its own process,
started under whatever ``TZ`` the test gives it. Its first statement pins the
process clock to UTC, as every entry point's does; then it writes one generated
activity report through the real writer (``ActivityReport.create`` →
``ActivityReportService.persist``, the generator's own path) and prints, as JSON,
the report's stored ``created_at`` and what ``check_cooldown`` counts.

    python tests/integration/probes/cooldown_under_the_pin.py <neo4j-uri> <user-uid>
"""

from core.utils.process_clock import pin_process_clock_to_utc

pin_process_clock_to_utc()  # the UTC arc's bridge: before any clock read (ADR-089)

import asyncio  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
from datetime import datetime, timedelta  # noqa: E402

from adapters.persistence.neo4j.backends.misc_backends import (  # noqa: E402
    ActivityReportBackend,
    ActivityReportGeneratorBackend,
)
from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection  # noqa: E402
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor  # noqa: E402
from core.constants import ReportTimePeriod  # noqa: E402
from core.models.enums.neo_labels import NeoLabel  # noqa: E402
from core.models.enums.pipeline import ReportSource  # noqa: E402
from core.models.report.activity_report import ActivityReport  # noqa: E402
from core.models.type_hints import UserUID  # noqa: E402
from core.services.report.activity_report_service import ActivityReportService  # noqa: E402
from core.utils.zone_context import default_zone  # noqa: E402


async def probe(uri: str, user_uid: str) -> dict[str, object]:
    connection = Neo4jConnection(uri=uri, username="neo4j", password="testpassword")
    driver = await connection.connect()
    try:
        backend = ActivityReportBackend(
            driver, NeoLabel.ACTIVITY_REPORT, ActivityReport, base_label=NeoLabel.ENTITY
        )
        service = ActivityReportService(
            backend=backend, context_builder=None, event_bus=None, sharing_service=None
        )
        now = datetime.now()
        report = ActivityReport.create(
            user_uid=UserUID(user_uid),
            subject_uid=user_uid,
            content="probe",
            processor_type=ReportSource.AUTOMATIC,
            period_start=now - timedelta(days=7),
            period_end=now,
            time_period="7d",
            zone=default_zone(),
        )
        persisted = await service.persist(report)
        if persisted.is_error:
            raise RuntimeError(persisted.expect_error().message)
        cooldown = await ActivityReportGeneratorBackend(Neo4jQueryExecutor(driver)).check_cooldown(
            user_uid, ReportTimePeriod.MIN_REPORT_COOLDOWN_MINUTES, "7d"
        )
        if cooldown.is_error:
            raise RuntimeError(cooldown.expect_error().message)
        stored = await driver.execute_query(
            "MATCH (r:ActivityReport {uid: $uid}) RETURN r.created_at AS created_at",
            uid=report.uid,
        )
        return {
            "recent_count": cooldown.value[0]["recent_count"],
            "created_at": stored.records[0]["created_at"],
        }
    finally:
        await connection.close()


if __name__ == "__main__":
    print(json.dumps(asyncio.run(probe(sys.argv[1], sys.argv[2]))))
