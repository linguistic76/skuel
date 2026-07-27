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

from core.models.type_hints import UserUID
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from core.models.enums import MasteryLevel
    from core.models.forms.form_template import FormTemplate
    from core.models.shared.dual_track import DualTrackResult
    from core.ports.form_protocols import FormTemplateOperations
    from core.ports.relationship_backend_protocols import UserRelationshipOperations
    from core.services.exercises.exercise_service import ExerciseService
    from core.services.ku_service import KuService
    from core.services.ps_service import PsService
    from core.services.user import UserContext
    from core.services.user_entry.learning_loop_query import LearningLoopQueryService


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
        user_relationship_service: "UserRelationshipOperations",
        exercises_service: "ExerciseService",
        learning_loop_query_service: "LearningLoopQueryService",
        form_template_service: "FormTemplateOperations | None" = None,
    ) -> None:
        self._ku = ku_service
        self._ps = ps_service
        self._user_relationships = user_relationship_service
        self._exercises = exercises_service
        self._learning_loop_queries = learning_loop_query_service
        self._form_templates = form_template_service

    # ------------------------------------------------------------------
    # Ku operations
    # ------------------------------------------------------------------

    async def get_ku(self, uid: str) -> Result[Any]:
        """Fetch a Knowledge Unit by UID."""
        return await self._ku.get_ku(uid)

    async def get_ku_with_content(self, uid: str) -> Result[Any]:
        """Fetch a Ku with its lesson body (:Content subtree, ADR-074)."""
        return await self._ku.get_with_content(uid)

    async def get_ku_learning_state(self, user_uid: UserUID, ku_uid: str) -> Result[dict]:
        """Get a user's learning state for a specific KU."""
        return await self._ku.get_ku_learning_state(user_uid, ku_uid)

    async def get_ku_cited_resources(self, ku_uid: str) -> Result[list[dict[str, Any]]]:
        """Get the curated Resources a Ku cites (CITES_RESOURCE edges).

        Named distinctly from the PathStep ``get_cited_resources`` so the two
        entity paths stay unambiguous.
        """
        return await self._ku.get_cited_resources(ku_uid)

    async def assess_ku_mastery(
        self,
        user_uid: UserUID,
        ku_uid: str,
        user_level: "MasteryLevel",
        user_evidence: str,
        user_context: "UserContext",
        user_reflection: str | None = None,
        store_callback: (
            "Callable[[str, DualTrackResult[MasteryLevel]], Awaitable[None]] | None"
        ) = None,
    ) -> "Result[DualTrackResult[MasteryLevel]]":
        """Run a dual-track Knowledge-mastery assessment for a Ku (ADR-030)."""
        return await self._ku.assess_mastery_dual_track(
            user_uid,
            ku_uid,
            user_level,
            user_evidence,
            user_context,
            user_reflection=user_reflection,
            store_callback=store_callback,
        )

    async def get_exercises_for_curriculum(self, ku_uid: str) -> Result[list]:
        """Get exercises associated with a KU."""
        return await self._exercises.get_exercises_for_curriculum(ku_uid)

    async def get_pinned_entities(self, user_uid: UserUID) -> Result[Any]:
        """Get UIDs of entities pinned by the user."""
        return await self._user_relationships.get_pinned_entities(user_uid)

    async def list_nous_topics(self) -> Result[list[str]]:
        """Curriculum-wide NOUS topic vocabulary (graph-derived, anonymous-safe).

        Feeds the library facet bar's NOUS dropdown. Unscoped — no user_uid —
        so non-registered viewers get the same public taxonomy.

        Backend: KuService.list_nous_topics → KuSearchService.list_all_categories.
        """
        return await self._ku.list_nous_topics()

    # ------------------------------------------------------------------
    # PathStep operations
    # ------------------------------------------------------------------

    async def get_ps_with_content(self, uid: str) -> Result[Any]:
        """Fetch a PathStep with its full content body."""
        return await self._ps.get_with_content(uid)

    async def record_ps_view(self, user_uid: UserUID, ps_uid: str) -> None:
        """Record that a user viewed a PathStep (best-effort)."""
        await self._ps.mastery.record_view(user_uid, ps_uid)

    async def get_ps_learning_state(self, user_uid: UserUID, ps_uid: str) -> Result[Any]:
        """Get learning mastery state for a specific PathStep."""
        return await self._ps.mastery.get_learning_state(user_uid, ps_uid)

    async def get_used_kus(self, ps_uid: str) -> Result[list[dict[str, Any]]]:
        """Get the atomic Kus a PathStep composes (USES_KU edges)."""
        return await self._ps.get_used_kus(ps_uid)

    async def get_cited_resources(self, ps_uid: str) -> Result[list[dict[str, Any]]]:
        """Get the curated Resources a PathStep cites (CITES_RESOURCE edges)."""
        return await self._ps.get_cited_resources(ps_uid)

    async def get_exercises_for_path_step(self, ps_uid: str) -> Result[list]:
        """Get exercises linked to a PathStep (unauthenticated read-only view)."""
        return await self._ps.get_exercises_for_path_step(ps_uid)

    async def get_exercises_for_path_step_with_status(
        self, ps_uid: str, user_uid: UserUID
    ) -> Result[list]:
        """Get exercises for a PathStep with per-user submission/feedback status."""
        return await self._exercises.get_exercises_for_path_step_with_status(ps_uid, user_uid)

    async def get_submissions_for_path_step(self, user_uid: UserUID, ps_uid: str) -> Result[list]:
        """Get a user's submissions + feedback for a specific PathStep."""
        return await self._learning_loop_queries.get_submissions_for_path_step(user_uid, ps_uid)

    async def get_forms_for_path_step(self, ps_uid: str) -> "Result[list[FormTemplate]]":
        """Get FormTemplates embedded in a PathStep via EMBEDS_FORM."""
        if self._form_templates is None:
            return Result.ok([])
        return await self._form_templates.get_forms_for_path_step(ps_uid)

    # ------------------------------------------------------------------
    # Library card decorations (pins + learning states)
    # ------------------------------------------------------------------

    async def load_card_decorations(
        self, user_uid: UserUID | None
    ) -> tuple[set[str], dict[str, str]]:
        """Pins + learning-state labels for decorating library cards.

        The catalog content itself comes from SearchRouter.faceted_search
        (One Path Forward — July 2026 /explore/library consolidation); this
        loads only the per-user overlay. Anonymous browse gets empty
        decorations. Runs the three user queries concurrently; each fails
        soft — a missing overlay degrades a badge, never the grid.

        Returns:
            (pinned_uids, learning_states) — states keyed by entity UID with
            labels "Understood"/"Studying" (Ku) and "In Progress" (PathStep).
        """
        pinned_uids: set[str] = set()
        learning_states: dict[str, str] = {}
        if not user_uid:
            return pinned_uids, learning_states

        pins_result, ku_states_result, ps_states_result = await asyncio.gather(
            self._user_relationships.get_pinned_entities(user_uid),
            self._ku.get_user_learning_states(user_uid),
            self._ps.mastery.get_in_progress_step_uids(user_uid),
        )

        if not getattr(pins_result, "is_error", False) and getattr(pins_result, "value", None):
            pinned_uids = set(pins_result.value)

        if getattr(ku_states_result, "is_ok", False) and getattr(ku_states_result, "value", None):
            for rec in ku_states_result.value:
                ku_uid = rec.get("uid", "")
                if rec.get("is_understood"):
                    learning_states[ku_uid] = "Understood"
                elif rec.get("is_studying"):
                    learning_states[ku_uid] = "Studying"

        if not getattr(ps_states_result, "is_error", False) and getattr(
            ps_states_result, "value", None
        ):
            for ps_uid in ps_states_result.value:
                learning_states[ps_uid] = "In Progress"

        return pinned_uids, learning_states

    # ------------------------------------------------------------------
    # Learning universe graph (was inline in /api/explore/graph)
    # ------------------------------------------------------------------

    async def generate_learning_graph(
        self, user_uid: UserUID | None
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
                        # `get_steps_batch` is positional: a UID whose PathStep
                        # was deleted while the user's in-progress edge survived
                        # comes back as None, and `ps.uid` would 500 the page.
                        for ps in batch_result.value
                        if ps is not None
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

    async def get_sidebar_data(self, user_uid: UserUID) -> dict[str, Any]:
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

            # Entity kind by lookup, never by UID prefix (ADR-013 never-sniff
            # rule). Two concurrent rounds instead of per-pin serial awaits:
            # batch the KU lookups, then batch PS lookups for the KU misses.
            unresolved = [uid for uid in pins_result.value if uid not in known_titles]
            ku_results = await asyncio.gather(
                *(self._ku.get_ku(uid) for uid in unresolved), return_exceptions=True
            )
            ku_titles: dict[str, str] = {
                uid: res.value.title or uid
                for uid, res in zip(unresolved, ku_results, strict=True)
                if not isinstance(res, BaseException) and res.is_ok and res.value
            }
            ku_misses = [uid for uid in unresolved if uid not in ku_titles]
            ps_results = await asyncio.gather(
                *(self._ps.get(uid) for uid in ku_misses), return_exceptions=True
            )
            ps_titles: dict[str, str] = {
                uid: res.value.title or uid
                for uid, res in zip(ku_misses, ps_results, strict=True)
                if not isinstance(res, BaseException) and res.is_ok and res.value
            }
            for pin_uid in pins_result.value:
                if pin_uid in known_titles:
                    title, et = known_titles[pin_uid]
                    pinned_items.append((pin_uid, title, et))
                elif pin_uid in ku_titles:
                    pinned_items.append((pin_uid, ku_titles[pin_uid], "ku"))
                elif pin_uid in ps_titles:
                    pinned_items.append((pin_uid, ps_titles[pin_uid], "ps"))

        return {
            "studying_kus": studying_kus[:5],
            "understood_kus": understood_kus,
            "in_progress_ps": in_progress_ps[:2],
            "pinned_uids": pinned_uids,
            "pinned_items": pinned_items,
        }

    # ------------------------------------------------------------------
    # Reading plan (real learner state; ZPD ready-set is a future arc)
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_reading_minutes(text: str | None) -> int:
        """Rough reading time at ~200 wpm; 0 when there is nothing to estimate."""
        words = len((text or "").split())
        return max(1, round(words / 200)) if words else 0

    async def get_reading_plan(self, user_uid: UserUID | None) -> dict[str, Any]:
        """Return the reading plan for the Explore reading-first surface.

        Real learner state only (de-faked 2026-07-04, care arc ruling): the
        shipped stub fabricated a read-history line, a nonexistent active
        path step, and invented ready-now cards that dead-ended in
        "not found". Now:

        - ``active_path_step`` — the user's real IN_PROGRESS PathStep, its
          USES_KU composition, and per-KU read state (``is_understood``).
        - ``featured`` — the next unread KU inside that step (real "why");
          falls back to the first library KU with honest copy.
        - ``last_completed`` / ``in_progress`` / ``also_ready`` / ``related``
          — empty until the intelligence behind them exists (read-history
          and the ZPD-derived ready set); the renderer collapses empty
          sections rather than inventing state.

        TODO: UserContextIntelligence.get_ready_to_read_today (own arc)
              fills also_ready/related from the ZPD assessment.
        """
        from datetime import date

        today = date.today()
        date_label = today.strftime("%A · %B ") + str(today.day)

        # list() returns (items, total_count) — use the real DB total, not the
        # page size, and fetch just one row for the fallback hero (Kody #505).
        library_total = 0
        first_library_ku: Any = None
        ku_result = await self._ku.core.list(limit=1)
        if not ku_result.is_error and ku_result.value:
            kus, library_total = ku_result.value
            first_library_ku = kus[0] if kus else None

        active_path_step: dict[str, Any] | None = None
        featured: dict[str, Any] = {}

        if user_uid:
            ps_uids_result = await self._ps.mastery.get_in_progress_step_uids(user_uid)
            ps_uids = list(ps_uids_result.value or []) if not ps_uids_result.is_error else []
            step: Any = None
            if ps_uids:
                batch_result = await self._ps.get_steps_batch(ps_uids[:1])
                if batch_result.is_ok and batch_result.value:
                    step = batch_result.value[0]
            if step is not None:
                used_result, states_result = await asyncio.gather(
                    self._ps.get_used_kus(step.uid),
                    self._ku.get_user_learning_states(user_uid),
                )
                understood: set[str] = set()
                if states_result.is_ok and states_result.value:
                    understood = {
                        rec.get("uid", "")
                        for rec in states_result.value
                        if rec.get("is_understood")
                    }
                knowledge_units: list[dict[str, Any]] = []
                current_ku: dict[str, Any] | None = None
                used_rows = (used_result.value or []) if used_result.is_ok else []
                for row in used_rows:
                    ku_uid = str(row.get("uid", ""))
                    if ku_uid in understood:
                        status = "read"
                    elif current_ku is None:
                        status = "current"
                    else:
                        status = "upcoming"
                    unit = {
                        "uid": ku_uid,
                        "title": row.get("title") or ku_uid,
                        "status": status,
                        "reading_minutes": 0,
                        "excerpt": None,
                    }
                    if status == "current":
                        current_ku = unit
                    knowledge_units.append(unit)

                units_total = len(knowledge_units)
                units_read = sum(1 for u in knowledge_units if u["status"] == "read")
                active_path_step = {
                    "uid": step.uid,
                    "title": step.title or step.uid,
                    "summary": step.description or "",
                    "contributes_to_lifepath": "",
                    "units_total": units_total,
                    "units_read": units_read,
                    "progress": (units_read / units_total) if units_total else 0.0,
                    "knowledge_units": knowledge_units,
                    # Capability tray (practice/apply) is per-step authored
                    # content — none exists yet, so the tray collapses.
                    "capabilities": [],
                }

                if current_ku is not None:
                    ku_detail = await self._ku.get_ku(current_ku["uid"])
                    detail = ku_detail.value if ku_detail.is_ok else None
                    excerpt = getattr(detail, "description", None) or ""
                    minutes = self._estimate_reading_minutes(
                        getattr(detail, "content", None) or excerpt
                    )
                    current_ku["reading_minutes"] = minutes
                    featured = {
                        "uid": current_ku["uid"],
                        "title": current_ku["title"],
                        "excerpt": excerpt,
                        "reading_minutes": minutes,
                        "status_label": "Up next in your step",
                        "why_now": (
                            f"It's the next idea in {step.title or 'your current step'}, "
                            "the step you're working through."
                        ),
                        "why": [
                            {
                                "met": True,
                                "text": (
                                    f"Part of {step.title or 'your current step'} — "
                                    "the path step you chose to study."
                                ),
                            }
                        ],
                    }

        pinned_uids: list[str] = []
        if user_uid:
            pins_result = await self._user_relationships.get_pinned_entities(user_uid)
            if not pins_result.is_error and pins_result.value:
                pinned_uids = list(pins_result.value)

        if not featured and first_library_ku is not None:
            excerpt = getattr(first_library_ku, "description", None) or ""
            featured = {
                "uid": getattr(first_library_ku, "uid", ""),
                "title": getattr(first_library_ku, "title", "") or "",
                "excerpt": excerpt,
                "reading_minutes": self._estimate_reading_minutes(
                    getattr(first_library_ku, "content", None) or excerpt
                ),
                "status_label": "From the library",
                "why_now": (
                    "A starting point from the library — enroll in a path step "
                    "for a guided sequence."
                ),
                "why": [],
            }

        return {
            "reader_name": "there",
            "date_label": date_label,
            "last_completed": {},
            "featured": featured,
            "in_progress": [],
            "also_ready": [],
            "active_path_step": active_path_step,
            "pinned_uids": pinned_uids,
            "related": [],
            "library": {
                "total": library_total,
                "tags": ["#attention", "#mindfulness", "#self-awareness", "#choices"],
            },
        }
