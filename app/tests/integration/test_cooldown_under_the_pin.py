"""A report written by a process started on the laptop's clock counts toward its cooldown.

The activity-report cooldown compares ``datetime(created_at)`` with the server's
``datetime()``, and the writer stamps ``created_at`` with a naive
``datetime.now()``. On the laptop (America/Vancouver, UTC-7) that stamp read as
UTC was seven hours old, so the cooldown never fired. Every entry point now pins
its process clock to UTC first (``core/utils/process_clock.py``), so the stamp is
UTC whatever zone the process was started in.

The probe (``probes/cooldown_under_the_pin.py``) is its own process, started here
under ``TZ=America/Vancouver`` against the shared testcontainer: it pins itself,
writes one generated report through the real writer, and reports what
``check_cooldown`` counts.

See: /docs/roadmap/utc-instants-arc.md § PR 4 (the cooldown pin)
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

pytestmark = [pytest.mark.asyncio(loop_scope="session"), pytest.mark.integration]

APP = Path(__file__).resolve().parents[2]
PROBE = Path(__file__).parent / "probes" / "cooldown_under_the_pin.py"
USER = "user_cooldown_pin"


async def test_a_report_written_by_a_vancouver_started_process_is_in_cooldown(
    neo4j_driver, neo4j_uri
) -> None:
    await neo4j_driver.execute_query("MERGE (:User {uid: $uid})", uid=USER)
    try:
        # The probe's own process: started on the laptop's clock, with the container's
        # password in its environment (CI's carries none for the settings to validate).
        env = {
            **os.environ,
            "TZ": "America/Vancouver",
            "PYTHONPATH": str(APP),
            "NEO4J_PASSWORD": "testpassword",
        }
        run = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, str(PROBE), neo4j_uri, USER],
            cwd=APP,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert run.returncode == 0, run.stderr[-3000:]
        result = json.loads(run.stdout.strip().splitlines()[-1])

        # Its stamp is the UTC wall clock, not the Vancouver one seven hours behind.
        stamped = datetime.fromisoformat(result["created_at"]).replace(tzinfo=UTC)
        assert abs(datetime.now(UTC) - stamped) < timedelta(minutes=5), result
        assert result["recent_count"] == 1, result
    finally:
        await neo4j_driver.execute_query(
            "MATCH (u:User {uid: $uid}) OPTIONAL MATCH (u)-[:OWNS]->(r:ActivityReport) "
            "DETACH DELETE r, u",
            uid=USER,
        )
