"""Explore UI Orchestrator
=========================

Application orchestrator for the Explore & Knowledge Hub. Consolidates
KU, PathStep, UserRelationship, Exercise, and LearningLoopQuery services
into a single unified facade for UI rendering.

Absorbs the heavy ``_load_explore_data`` helper and the Vis.js graph
generation that previously lived inline inside ``explore_ui.py``.

All service dependencies are required — bootstrap raises if any are missing
(Fail-Fast Dependency Philosophy).
"""

import asyncio
from typing import TYPE_CHECKING, Any

from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.services.exercises.exercise_service import ExerciseService
    from core.services.ku_service import KuService
    from core.services.ps_service import PsService
    from core.services.submissions.learning_loop_query_service import LearningLoopQueryService
    from core.services.user_relationship_service import UserRelationshipService


class ExploreOrchestrator:
    """Facade for the Explore / Knowledge Hub UI layer.

    Abstracts cross-domain reads so the UI routing layer depends only on this
    orchestrator. All service dependencies are required — bootstrap raises if
    any are missing (Fail-Fast Dependency Philosophy).
    """

    def __init__(
        self,
        ku_service: "KuService",
        ps_service: "PsService",
        user_relationship_service: "UserRelationshipService",
        exercises_service: "ExerciseService",
        learning_loop_query_service: "LearningLoopQueryService",
    ) -> None:
        self._ku = ku_service
        self._ps = ps_service
        self._user_relationships = user_relationship_service
        self._exercises = exercises_service
        self._learning_loop_queries = learning_loop_query_service

    # ------------------------------------------------------------------
    # Ku operations
    # ------------------------------------------------------------------

    async def get_ku(self, uid: str) -> Result[Any]:
        """Fetch a Knowledge Unit by UID."""
        return await self._ku.get_ku(uid)

    async def get_ku_learning_state(self, user_uid: str, ku_uid: str) -> Result[dict]:
        """Get a user's learning state for a specific KU."""
        return await self._ku.get_ku_learning_state(user_uid, ku_uid)

    async def get_exercises_for_curriculum(self, ku_uid: str) -> Result[list]:
        """Get exercises associated with a KU."""
        return await self._exercises.get_exercises_for_curriculum(ku_uid)

    async def get_pinned_entities(self, user_uid: str) -> Result[Any]:
        """Get UIDs of entities pinned by the user."""
        return await self._user_relationships.get_pinned_entities(user_uid)

    # ------------------------------------------------------------------
    # PathStep operations
    # ------------------------------------------------------------------

    async def get_ps_with_content(self, uid: str) -> Result[Any]:
        """Fetch a PathStep with its full content body."""
        return await self._ps.get_with_content(uid)

    async def record_ps_view(self, user_uid: str, ps_uid: str) -> None:
        """Record that a user viewed a PathStep (best-effort)."""
        await self._ps.mastery.record_view(user_uid, ps_uid)

    async def get_ps_learning_state(self, user_uid: str, ps_uid: str) -> Result[Any]:
        """Get learning mastery state for a specific PathStep."""
        return await self._ps.mastery.get_learning_state(user_uid, ps_uid)

    async def get_exercises_for_path_step(self, ps_uid: str) -> Result[list]:
        """Get exercises linked to a PathStep (unauthenticated read-only view)."""
        return await self._ps.get_exercises_for_path_step(ps_uid)

    async def get_exercises_for_path_step_with_status(
        self, ps_uid: str, user_uid: str
    ) -> Result[list]:
        """Get exercises for a PathStep with per-user submission/feedback status."""
        return await self._exercises.get_exercises_for_path_step_with_status(ps_uid, user_uid)

    async def get_submissions_for_path_step(self, user_uid: str, ps_uid: str) -> Result[list]:
        """Get a user's submissions + feedback for a specific PathStep."""
        return await self._learning_loop_queries.get_submissions_for_path_step(user_uid, ps_uid)

    # ------------------------------------------------------------------
    # Index data aggregation (was _load_explore_data)
    # ------------------------------------------------------------------

    async def load_explore_index(
        self, user_uid: str | None
    ) -> tuple[list[tuple[Any, str]], set[str], dict[str, str]]:
        """Load all Ku + PS items, pins, and learning states for the index page.

        Runs independent queries concurrently via asyncio.gather.

        Returns:
            (unified_items, pinned_uids, learning_states)
        """
        # Content queries
        ku_coro = self._ku.core.list(limit=500)
        ps_coro = self._ps.core.list(limit=200)

        # User-specific queries
        pins_coro = (
            self._user_relationships.get_pinned_entities(user_uid) if user_uid else asyncio.sleep(0)
        )
        ku_states_coro = (
            self._ku.get_user_learning_states(user_uid) if user_uid else asyncio.sleep(0)
        )
        ps_states_coro = (
            self._ps.mastery.get_in_progress_step_uids(user_uid) if user_uid else asyncio.sleep(0)
        )

        (
            ku_result,
            ps_result,
            pins_result,
            ku_states_result,
            ps_states_result,
        ) = await asyncio.gather(ku_coro, ps_coro, pins_coro, ku_states_coro, ps_states_coro)

        # Assemble items
        items: list[tuple[Any, str]] = []
        if (
            ku_result
            and not getattr(ku_result, "is_error", False)
            and getattr(ku_result, "value", None)
        ):
            items.extend((ku, "ku") for ku in ku_result.value)
        if (
            ps_result
            and not getattr(ps_result, "is_error", False)
            and getattr(ps_result, "value", None)
        ):
            raw = ps_result.value if isinstance(ps_result.value, list) else ps_result.value[0]
            items.extend((ps, "ps") for ps in raw)

        # Assemble user-specific data
        pinned_uids: set[str] = set()
        learning_states: dict[str, str] = {}

        if user_uid:
            if (
                pins_result
                and not getattr(pins_result, "is_error", False)
                and getattr(pins_result, "value", None)
            ):
                pinned_uids = set(pins_result.value)

            if (
                ku_states_result
                and getattr(ku_states_result, "is_ok", False)
                and getattr(ku_states_result, "value", None)
            ):
                for rec in ku_states_result.value:
                    ku_uid = rec.get("uid", "")
                    if rec.get("is_understood"):
                        learning_states[ku_uid] = "Understood"
                    elif rec.get("is_studying"):
                        learning_states[ku_uid] = "Studying"

            if (
                ps_states_result
                and not getattr(ps_states_result, "is_error", False)
                and getattr(ps_states_result, "value", None)
            ):
                for ps_uid in ps_states_result.value:
                    learning_states[ps_uid] = "In Progress"

        return items, pinned_uids, learning_states

    # ------------------------------------------------------------------
    # Learning universe graph (was inline in /api/explore/graph)
    # ------------------------------------------------------------------

    async def generate_learning_graph(
        self, user_uid: str | None
    ) -> dict[str, list[dict[str, Any]]]:
        """Build the Vis.js {nodes, edges} JSON for the learning universe.

        Returns the full graph payload dict ready for JSONResponse.
        """
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []

        if not user_uid:
            return {"nodes": nodes, "edges": edges}

        # Studying / understood KUs
        states_result = await self._ku.get_user_learning_states(user_uid)
        if states_result.is_ok and states_result.value:
            for rec in states_result.value:
                ku_uid = rec.get("uid", "")
                ku_title = rec.get("title", ku_uid)
                state = "studying" if rec.get("is_studying") else "understood"
                if rec.get("is_studying") or rec.get("is_understood"):
                    nodes.append(
                        {
                            "id": ku_uid,
                            "label": ku_title,
                            "type": "ku",
                            "group": "related",
                            "learning_state": state,
                            "is_pinned": False,
                        }
                    )

        # In-progress PathSteps
        in_progress_result = await self._ps.mastery.get_in_progress_step_uids(user_uid)
        if not in_progress_result.is_error and in_progress_result.value:
            in_progress_ps_uids = list(in_progress_result.value[:10])
            if in_progress_ps_uids:
                batch_result = await self._ps.get_steps_batch(in_progress_ps_uids)
                if batch_result.is_ok and batch_result.value:
                    nodes.extend(
                        {
                            "id": ps.uid,
                            "label": ps.title or ps.uid,
                            "type": "ps",
                            "group": "related",
                            "learning_state": "in_progress",
                            "is_pinned": False,
                        }
                        for ps in batch_result.value
                    )

        # Mark pinned entities
        pins_result = await self._user_relationships.get_pinned_entities(user_uid)
        if pins_result.is_ok and pins_result.value:
            pinned_set = set(pins_result.value)
            for node in nodes:
                if node["id"] in pinned_set:
                    node["is_pinned"] = True

        # Virtual "You" center node
        if nodes:
            nodes.insert(
                0,
                {
                    "id": "__you__",
                    "label": "You",
                    "type": "you",
                    "group": "center",
                    "learning_state": None,
                    "is_pinned": False,
                },
            )
            edges.extend(
                {
                    "from": "__you__",
                    "to": node["id"],
                    "color": {"color": "#94A3B8", "opacity": 0.4},
                    "width": 1,
                    "dashes": [4, 4],
                }
                for node in nodes[1:]
            )

        return {"nodes": nodes, "edges": edges}

    # ------------------------------------------------------------------
    # Sidebar data aggregation (was _fetch_sidebar_data in ui/explore/nav.py)
    # ------------------------------------------------------------------

    async def get_sidebar_data(self, user_uid: str) -> dict[str, Any]:
        """Fetch learning states, pins, and in-progress items for the Explore sidebar.

        Runs independent queries concurrently via asyncio.gather.

        Returns dict with keys:
            studying_kus: list of {uid, title} dicts
            understood_kus: list of {uid, title} dicts
            in_progress_ps: list of PathStep entities
            pinned_uids: set of pinned entity UIDs
            pinned_items: list of (uid, title, entity_type) tuples
        """
        ku_states_coro = self._ku.get_user_learning_states(user_uid)
        ps_uids_coro = self._ps.mastery.get_in_progress_step_uids(user_uid)
        pins_coro = self._user_relationships.get_pinned_entities(user_uid)

        ku_states_result, ps_uids_result, pins_result = await asyncio.gather(
            ku_states_coro, ps_uids_coro, pins_coro
        )

        # Process Ku learning states
        studying_kus: list[dict[str, str]] = []
        understood_kus: list[dict[str, str]] = []
        if (
            ku_states_result
            and getattr(ku_states_result, "is_ok", False)
            and getattr(ku_states_result, "value", None)
        ):
            for rec in ku_states_result.value:
                ku_uid = rec.get("uid", "")
                ku_title = rec.get("title", ku_uid)
                if rec.get("is_understood"):
                    understood_kus.append({"uid": ku_uid, "title": ku_title})
                elif rec.get("is_studying"):
                    studying_kus.append({"uid": ku_uid, "title": ku_title})

        # Process PS in-progress (batch-fetch entities for the top 5)
        in_progress_ps: list[Any] = []
        if (
            ps_uids_result
            and not getattr(ps_uids_result, "is_error", False)
            and getattr(ps_uids_result, "value", None)
        ):
            uids = ps_uids_result.value[:5]
            if uids:
                batch_result = await self._ps.get_steps_batch(uids)
                if batch_result.is_ok and batch_result.value:
                    in_progress_ps = list(batch_result.value)

        # Process pinned entities
        pinned_uids: set[str] = set()
        pinned_items: list[tuple[str, str, str]] = []
        if (
            pins_result
            and getattr(pins_result, "is_ok", False)
            and getattr(pins_result, "value", None)
        ):
            pinned_uids = set(pins_result.value)
            # Resolve titles for pinned items — check against already-loaded data
            known_titles: dict[str, tuple[str, str]] = {}
            for rec in studying_kus + understood_kus:
                known_titles[rec["uid"]] = (rec["title"], "ku")
            for ps in in_progress_ps:
                known_titles[ps.uid] = (ps.title or ps.uid, "ps")

            for pin_uid in pins_result.value:
                if pin_uid in known_titles:
                    title, et = known_titles[pin_uid]
                    pinned_items.append((pin_uid, title, et))
                elif pin_uid.startswith("ku_"):
                    ku_result = await self._ku.get_ku(pin_uid)
                    if ku_result.is_ok and ku_result.value:
                        pinned_items.append((pin_uid, ku_result.value.title or pin_uid, "ku"))
                elif pin_uid.startswith("ps:"):
                    pinned_items.append((pin_uid, pin_uid, "ps"))

        return {
            "studying_kus": studying_kus[:5],
            "understood_kus": understood_kus,
            "in_progress_ps": in_progress_ps[:2],
            "pinned_uids": pinned_uids,
            "pinned_items": pinned_items,
        }
