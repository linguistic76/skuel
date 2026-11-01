"""
Integration tests for the vision → recommendations read (testcontainer Neo4j).

``LifePathService`` over the real LifePath backend and a real ``LpService``: a
captured vision is saved and read back with its themes (and, once the learner
designates one, the path they chose), and its Learning Paths are found by one
search per theme. The LP text search matches its query as one
phrase, so the themes joined into one query would find only a path holding them
all side by side — these themes appear in no title together, and are found.

The designated path is read by its uid and scored against the themes whether
they find it or not — a path they miss, a draft the search hides, a vision with
no themes — and is never also among the other matches.

CORE tier (no LLM): theme extraction is the keyword fallback, which keeps the
statement's longer words when it names no known theme.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from core.models.pathways.learning_path_dto import LearningPathDTO
from core.services.lifepath.lifepath_service import LifePathService
from core.utils.result_simplified import ErrorCategory
from tests.helpers.seed_uids import seed_user_uid

pytestmark = pytest.mark.asyncio(loop_scope="session")

_USER_UID = seed_user_uid("test_lifepath_vision")
_STATEMENT = "Zephyrcraft, quillwork and lanternry for life"
_THEMES = ["zephyrcraft", "quillwork", "lanternry"]
_LP_TWO_THEMES = "lp.test.vision-zephyr-quill"
_LP_ONE_THEME = "lp.test.vision-lantern"
_LP_NO_THEME = "lp.test.vision-gardening"
_SEEDED = [_USER_UID, _LP_TWO_THEMES, _LP_ONE_THEME, _LP_NO_THEME]


@pytest_asyncio.fixture(loop_scope="session")
async def vision_graph(neo4j_driver, services):
    """A User with no vision, and three Learning Paths the themes find two of."""
    async with neo4j_driver.session() as session:
        await session.run("MATCH (n) WHERE n.uid IN $uids DETACH DELETE n", uids=_SEEDED)
        await session.run("MERGE (u:User {uid: $uid}) SET u.title = $uid", uid=_USER_UID)
    for uid, title, description in (
        (_LP_TWO_THEMES, "Zephyrcraft for Beginners", "Pairs well with quillwork."),
        (_LP_ONE_THEME, "Lanternry", "Light, carried."),
        (_LP_NO_THEME, "Gardening", "Soil and seasons."),
    ):
        created = await services.lp.core.backend.create(
            LearningPathDTO(uid=uid, title=title, description=description)
        )
        assert created.is_ok, created

    yield

    async with neo4j_driver.session() as session:
        await session.run("MATCH (n) WHERE n.uid IN $uids DETACH DELETE n", uids=_SEEDED)


@pytest_asyncio.fixture(loop_scope="session")
async def lifepath(production_backends, services) -> LifePathService:
    return LifePathService(backend=production_backends["lifepath_backend"], lp_service=services.lp)


class TestVisionRecommendations:
    async def test_a_captured_vision_is_read_back_with_its_themes(self, lifepath, vision_graph):
        captured = await lifepath.capture_vision(_USER_UID, _STATEMENT)
        assert captured.is_ok, captured
        assert captured.value["statement"] == _STATEMENT
        assert captured.value["themes"] == _THEMES
        assert captured.value["captured_at"]

        saved = await lifepath.get_vision(_USER_UID)
        assert saved.is_ok
        assert saved.value == {"statement": _STATEMENT, "themes": _THEMES, "life_path_uid": None}

    async def test_the_saved_vision_carries_the_designated_path(self, lifepath, vision_graph):
        """The recommendations page reads and scores this path as the current one."""
        assert (await lifepath.capture_vision(_USER_UID, _STATEMENT)).is_ok
        designated = await lifepath.core.designate_life_path(_USER_UID, _LP_ONE_THEME)
        assert designated.is_ok, designated

        saved = await lifepath.get_vision(_USER_UID)
        assert saved.is_ok
        assert saved.value == {
            "statement": _STATEMENT,
            "themes": _THEMES,
            "life_path_uid": _LP_ONE_THEME,
        }

    async def test_paths_are_found_by_any_theme_best_match_first(self, lifepath, vision_graph):
        found = await lifepath.match_learning_paths(_THEMES, None)

        assert found.is_ok, found
        assert found.value["current"] is None
        others = found.value["others"]
        assert [(m["lp_uid"], m["matching_themes"]) for m in others] == [
            (_LP_TWO_THEMES, ["zephyrcraft", "quillwork"]),
            (_LP_ONE_THEME, ["lanternry"]),
        ]
        assert [round(m["match_score"], 3) for m in others] == [0.667, 0.333]

    async def test_no_themes_find_no_paths(self, lifepath, vision_graph):
        found = await lifepath.match_learning_paths([], None)

        assert found.is_ok
        assert found.value == {"current": None, "others": []}

    async def test_a_designated_path_the_themes_miss_is_still_the_current_path(
        self, lifepath, vision_graph
    ):
        """A vision revised since the path was chosen: the path matches none of
        the new themes, and is shown at 0% rather than not at all."""
        found = await lifepath.match_learning_paths(_THEMES, _LP_NO_THEME)

        assert found.is_ok, found
        assert found.value["current"] == {
            "lp_uid": _LP_NO_THEME,
            "lp_name": "Gardening",
            "match_score": 0.0,
            "matching_themes": [],
        }
        assert [m["lp_uid"] for m in found.value["others"]] == [_LP_TWO_THEMES, _LP_ONE_THEME]

    async def test_a_designated_path_the_themes_find_is_answered_once(self, lifepath, vision_graph):
        found = await lifepath.match_learning_paths(_THEMES, _LP_TWO_THEMES)

        assert found.is_ok, found
        current = found.value["current"]
        assert current is not None
        assert current["lp_uid"] == _LP_TWO_THEMES
        assert round(current["match_score"], 3) == 0.667
        assert current["matching_themes"] == ["zephyrcraft", "quillwork"]
        assert [m["lp_uid"] for m in found.value["others"]] == [_LP_ONE_THEME]

    async def test_with_no_themes_the_designated_path_is_still_read(self, lifepath, vision_graph):
        found = await lifepath.match_learning_paths([], _LP_ONE_THEME)

        assert found.is_ok, found
        assert found.value["current"] == {
            "lp_uid": _LP_ONE_THEME,
            "lp_name": "Lanternry",
            "match_score": 0.0,
            "matching_themes": [],
        }
        assert found.value["others"] == []

    async def test_a_designated_path_now_a_draft_is_still_the_current_path(
        self, neo4j_driver, lifepath, vision_graph
    ):
        """The search hides a draft; the learner's own path is read by its uid."""
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (lp:Entity {uid: $uid}) SET lp.publication_state = 'draft'",
                uid=_LP_ONE_THEME,
            )

        unlisted = await lifepath.match_learning_paths(_THEMES, None)
        found = await lifepath.match_learning_paths(_THEMES, _LP_ONE_THEME)

        assert unlisted.is_ok, unlisted
        assert [m["lp_uid"] for m in unlisted.value["others"]] == [_LP_TWO_THEMES]
        assert found.is_ok, found
        current = found.value["current"]
        assert current is not None
        assert (current["lp_uid"], current["matching_themes"]) == (_LP_ONE_THEME, ["lanternry"])
        assert [m["lp_uid"] for m in found.value["others"]] == [_LP_TWO_THEMES]

    async def test_a_designated_path_that_cannot_be_read_fails_the_read(
        self, lifepath, vision_graph
    ):
        found = await lifepath.match_learning_paths(_THEMES, "lp.test.vision-nowhere")

        assert found.is_error
        assert found.expect_error().category == ErrorCategory.NOT_FOUND

    async def test_capture_and_recommend_recommends_from_the_saved_themes(
        self, lifepath, vision_graph
    ):
        result = await lifepath.capture_and_recommend(_USER_UID, _STATEMENT)

        assert result.is_ok, result
        assert result.value["vision"]["themes"] == _THEMES
        assert result.value["current_path"] is None
        assert [m["lp_uid"] for m in result.value["recommendations"]] == [
            _LP_TWO_THEMES,
            _LP_ONE_THEME,
        ]

    async def test_capture_and_recommend_answers_the_designated_path_once(
        self, lifepath, vision_graph
    ):
        designated = await lifepath.core.designate_life_path(_USER_UID, _LP_ONE_THEME)
        assert designated.is_ok, designated

        result = await lifepath.capture_and_recommend(_USER_UID, _STATEMENT)

        assert result.is_ok, result
        current = result.value["current_path"]
        assert current is not None
        assert current["lp_uid"] == _LP_ONE_THEME
        assert [m["lp_uid"] for m in result.value["recommendations"]] == [_LP_TWO_THEMES]

    async def test_a_vision_that_cannot_be_saved_is_not_captured(self, lifepath, vision_graph):
        unknown = seed_user_uid("test_lifepath_vision_nobody")
        result = await lifepath.capture_vision(unknown, _STATEMENT)

        assert result.is_error
        assert result.expect_error().category == ErrorCategory.NOT_FOUND
        assert (await lifepath.get_vision(unknown)).value is None

    async def test_a_designated_path_alone_is_no_vision(self, lifepath, vision_graph):
        designated = await lifepath.core.designate_life_path(_USER_UID, _LP_ONE_THEME)
        assert designated.is_ok, designated

        saved = await lifepath.get_vision(_USER_UID)
        assert saved.is_ok
        assert saved.value is None
