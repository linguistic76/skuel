"""The weekly life summary's curriculum section reads the learner's paths, over the bootstrapped app.

``GET /api/analytics/weekly-life-summary`` carries ``layer_0_knowledge.curriculum_progress``
(``AnalyticsMetricsService.calculate_curriculum_metrics``). Its figures come from two
reads: the learner's paths with their steps (``LpService.list_user_paths``) and the
entities the learner has mastered (``UserProgressService.get_mastered_uids``).

The learner enrolls at the real enroll door. Shared curriculum is seeded the way the
content vault writes it, and each MASTERED edge carries what ``mark_mastered`` writes.

    path        steps        learner mastered   reads as
    A           a1, a2       a1                 active, 1 of 2
    B           b1, a1       b1, a1             completed (a1 shared with A)
    D           d1           —                  active, 0 of 1
    C           c1           —                  not enrolled: not the learner's

Distinct steps on the learner's paths: a1, a2, b1, d1 — two mastered, two not. Another
learner has mastered a2, which must not count; C is the not-enrolled control.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from tests.helpers.seed_uids import seed_user_uid
from tests.integration._activity_link_rig import (
    seed_published_learning_path,
    seed_published_path_step,
    signed_in_client,
    write_edge,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import httpx
    from neo4j import AsyncDriver

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

MARK = "zzzwkcur"
LEARNER = seed_user_uid(f"{MARK}")
OTHER_LEARNER = seed_user_uid(f"{MARK}_other")

PATH_A = f"lp.{MARK}.a"
PATH_B = f"lp.{MARK}.b"
PATH_C = f"lp.{MARK}.c"
PATH_D = f"lp.{MARK}.d"
STEP_A1 = f"ps.{MARK}.a1"
STEP_A2 = f"ps.{MARK}.a2"
STEP_B1 = f"ps.{MARK}.b1"
STEP_C1 = f"ps.{MARK}.c1"
STEP_D1 = f"ps.{MARK}.d1"

PATH_STEPS = {
    PATH_A: [STEP_A1, STEP_A2],
    PATH_B: [STEP_B1, STEP_A1],
    PATH_C: [STEP_C1],
    PATH_D: [STEP_D1],
}

EMPTY_MARK = "zzzwkcurempty"
EMPTY_LEARNER = seed_user_uid(f"{EMPTY_MARK}")


async def _seed_curriculum(driver: AsyncDriver) -> None:
    for step in (STEP_A1, STEP_A2, STEP_B1, STEP_C1, STEP_D1):
        await seed_published_path_step(driver, step, f"Step {step}")
    for path, steps in PATH_STEPS.items():
        await seed_published_learning_path(driver, path, f"Path {path}")
        for sequence, step in enumerate(steps, start=1):
            await write_edge(driver, path, "HAS_STEP", step, {"sequence": sequence})


async def _master(driver: AsyncDriver, user_uid: str, step_uid: str) -> None:
    """A MASTERED edge with the properties ``mark_mastered`` writes."""
    await write_edge(
        driver,
        user_uid,
        "MASTERED",
        step_uid,
        {
            "mastered_at": datetime.now(UTC),
            "mastery_score": 1.0,
            "confidence": 1.0,
            "method": "step_completion",
        },
    )


async def _curriculum(client: httpx.AsyncClient) -> dict[str, Any]:  # boundary: JSON body
    response = await client.get("/api/analytics/weekly-life-summary")
    assert response.status_code == 200, response.text
    return response.json()["layer_0_knowledge"]["curriculum_progress"]


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def learner(skuel_app: Any) -> AsyncIterator[httpx.AsyncClient]:  # boundary: fasthtml-app
    driver = skuel_app.state.services.neo4j_driver
    async with signed_in_client(skuel_app, LEARNER, MARK) as client:
        await _seed_curriculum(driver)
        for path in (PATH_A, PATH_B, PATH_D):
            response = await client.post(f"/api/pathways/enroll/{path}")
            assert response.status_code == 200, response.text
        for step in (STEP_A1, STEP_B1):
            await _master(driver, LEARNER, step)
        async with driver.session() as session:
            await session.run("MERGE (u:User {uid: $uid})", uid=OTHER_LEARNER)
        await _master(driver, OTHER_LEARNER, STEP_A2)
        yield client


async def test_the_section_is_derived_from_the_learners_paths_and_mastered_steps(
    learner: httpx.AsyncClient,
) -> None:
    assert await _curriculum(learner) == {
        "active_learning_paths": 2,
        "completed_learning_paths": 1,
        "in_progress_path_steps": 2,
        "completed_path_steps": 2,
        "total_knowledge_units": 2,
        "mastered_knowledge_units": 2,
        "current_focus": {"lp_uid": PATH_A, "lp_title": f"Path {PATH_A}", "progress": 0.5},
    }


async def test_the_rendered_summary_shows_the_section(
    learner: httpx.AsyncClient,
) -> None:
    """The page's Layer 0 card shows the two figures it reads."""
    response = await learner.get("/ui/analytics/weekly-life-summary")
    assert response.status_code == 200, response.text
    page = " ".join(response.text.split())

    assert _stat(page, "Active Paths") == "2"
    assert _stat(page, "In-Progress Steps") == "2"


def _stat(page: str, label: str) -> str:
    """The value a ``StatCard`` renders under ``label``."""
    found = re.search(rf">{re.escape(label)}</span>\s*<div[^>]*>\s*<span[^>]*>([^<]*)<", page)
    assert found is not None, label
    return found.group(1)


async def test_a_learner_with_no_paths_reads_a_zero_section(
    skuel_app: Any,
) -> None:  # boundary: fasthtml-app
    """The positive control: a learner with nothing enrolled reads every figure as zero,
    not an absent section."""
    async with signed_in_client(skuel_app, EMPTY_LEARNER, EMPTY_MARK) as client:
        assert await _curriculum(client) == {
            "active_learning_paths": 0,
            "completed_learning_paths": 0,
            "in_progress_path_steps": 0,
            "completed_path_steps": 0,
            "total_knowledge_units": 0,
            "mastered_knowledge_units": 0,
            "current_focus": None,
        }
