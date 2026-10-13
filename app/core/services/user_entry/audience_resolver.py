"""
AudienceResolver — the one audience applier (ADR-088).

Every door that creates a ``UserEntry`` — ``UserEntryService.create_entry()``
for the ``/submissions/submit`` form and the JSON API, and the vault door through it —
hands the request's ``AudienceSpec`` (``core/models/user_entry/audience.py``,
the one parser) to this resolver, which turns the vocabulary into the two link
kinds (ADR-088 §1-§2): a feedback request (TEACHER_REVIEW only —
``SUBMITTED_TO_GROUP``, read by the group's owning teachers, or
``SUBMITTED_TO_TEACHER``, read by the one teacher it names, §9) and a share
(``SHARES_WITH`` / ``SHARED_WITH_GROUP`` — openable by its recipients).

Three steps, in the order ``create_entry`` runs them:
    1. ``validate``            — the pure rules (pipeline, privacy, feedback target)
    2. ``validate_references`` — every target resolved and authorised BEFORE the
                                 first write: exercise / predecessor claims,
                                 ``user:`` co-membership (R8), ``group:`` /
                                 ``teacher:`` reachability, and ``teachers``
                                 expanded to the exercise's teacher, or
                                 without an exercise to concrete groups
    3. ``resolve_and_share``   — the post-persist writes, of validated targets only

Public surface:
    - ``ResolvedAudience``  — what step 2 hands step 3
    - ``ShareOutcome``      — what step 3 hands the caller
    - ``AudienceResolver``

See: /docs/decisions/ADR-088-submit-and-share.md
See: /docs/decisions/ADR-054-user-entry-unified-submissions.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TypedDict

from core.models.enums import GroupMemberRole
from core.models.enums.pipeline import Pipeline
from core.models.type_hints import EntityUID, UserUID
from core.models.user_entry.audience import TEACHER_PREFIX, USER_PREFIX
from core.models.user_entry.user_entry_request import UserEntryCreateRequest
from core.services.mixins.link_edge_guard import PATH_STEP_FAR_END, admit_far_ends_for_owner
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.groups.group_service import GroupService
    from core.services.sharing.unified_sharing_service import UnifiedSharingService

logger = get_logger("skuel.services.user_entry.audience_resolver")

# A refused feedback request is a state-of-the-world fault, not a content
# fault: the vault sync reports it as an error to fix, never as a note
# ignored for its frontmatter (``batch.classify_user_entry_failure``).
FEEDBACK_TARGET_FIELD = "feedback_target"


@dataclass(frozen=True)
class TeacherTarget:
    """A feedback request filed with one teacher directly (ADR-088 §9, ADR-091 S3).

    ``teacher_uid`` is the teacher of the exercise ``exercise_uid`` the entry
    turns in against — its ``REVIEWED_BY`` teacher, the reviewer the write
    re-decides from it.
    """

    teacher_uid: str
    exercise_uid: str


@dataclass(frozen=True)
class ResolvedAudience:
    """The validated, concrete targets a spec resolved to — what the writes consume.

    ``teacher_groups`` are the explicit ``teacher:<group_uid>`` targets and
    ``teachers_groups`` the ``teachers`` expansion — together
    ``submit_groups``, where a feedback request goes; ``submit_teachers`` the
    ``teachers`` expansion's direct target, the exercise's teacher
    (ADR-091 S3); ``share_groups`` the
    ``group:`` targets; ``share_users`` the ``user:`` targets as
    ``(username, uid)`` pairs, each a verified co-member. ``public`` is the
    portfolio flag. Every uid here passed its authorisation check.
    """

    teacher_groups: tuple[str, ...] = ()
    teachers_groups: tuple[str, ...] = ()
    submit_teachers: tuple[TeacherTarget, ...] = ()
    share_groups: tuple[str, ...] = ()
    share_users: tuple[tuple[str, str], ...] = ()
    public: bool = False

    @property
    def submit_groups(self) -> tuple[str, ...]:
        """Every group the feedback request goes to, explicit targets first, no repeats."""
        return self.teacher_groups + tuple(
            g for g in self.teachers_groups if g not in self.teacher_groups
        )


class ShareOutcomePayload(TypedDict):
    """``ShareOutcome`` as a JSON response body — every tuple as a list, ``failed`` as
    ``{target, reason}`` rows; the shape the create and share doors return."""

    submitted_groups: list[str]
    newly_submitted_groups: list[str]
    submitted_teachers: list[str]
    newly_submitted_teachers: list[str]
    shared_groups: list[str]
    shared_users: list[str]
    newly_shared_users: list[str]
    failed: list[ShareFailurePayload]


class ShareFailurePayload(TypedDict):
    """One refused audience target and the reason it was refused."""

    target: str
    reason: str


@dataclass(frozen=True)
class ShareOutcome:
    """Result of a post-persist audience pass.

    ``submitted_groups`` are the groups whose feedback request stands after
    this pass — every ``SUBMITTED_TO_GROUP`` MERGE that matched, created or
    not (a re-filed request is a success, not zero reach);
    ``newly_submitted_groups`` is the created subset, the only thing that
    rings a teacher's bell. ``submitted_teachers`` /
    ``newly_submitted_teachers`` are the same pair for a request filed with a
    teacher directly (``SUBMITTED_TO_TEACHER``). ``shared_groups`` / ``shared_users`` are the
    share targets that landed; ``newly_shared_users`` is the subset whose
    ``SHARES_WITH`` this pass created — the only thing that rings a
    recipient's bell (R10: a re-share rings nobody twice, a group share
    rings no one). ``failed`` pairs each refused target with its
    error message.
    """

    submitted_groups: tuple[str, ...] = field(default_factory=tuple)
    newly_submitted_groups: tuple[str, ...] = field(default_factory=tuple)
    submitted_teachers: tuple[str, ...] = field(default_factory=tuple)
    newly_submitted_teachers: tuple[str, ...] = field(default_factory=tuple)
    shared_groups: tuple[str, ...] = field(default_factory=tuple)
    shared_users: tuple[str, ...] = field(default_factory=tuple)
    newly_shared_users: tuple[str, ...] = field(default_factory=tuple)
    failed: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    @property
    def any_success(self) -> bool:
        """Any link of any kind landed — the aggregate every non-feedback caller reads."""
        return self.any_feedback_request or bool(self.shared_groups) or bool(self.shared_users)

    @property
    def any_feedback_request(self) -> bool:
        """A feedback request stands — to a group, or to a teacher directly."""
        return bool(self.submitted_groups) or bool(self.submitted_teachers)

    @property
    def any_failure(self) -> bool:
        return bool(self.failed)

    def to_payload(self) -> ShareOutcomePayload:
        return {
            "submitted_groups": list(self.submitted_groups),
            "newly_submitted_groups": list(self.newly_submitted_groups),
            "submitted_teachers": list(self.submitted_teachers),
            "newly_submitted_teachers": list(self.newly_submitted_teachers),
            "shared_groups": list(self.shared_groups),
            "shared_users": list(self.shared_users),
            "newly_shared_users": list(self.newly_shared_users),
            "failed": [{"target": t, "reason": r} for t, r in self.failed],
        }


class AudienceResolver:
    """Validate, resolve and apply the audience of a ``UserEntryCreateRequest``.

    Stateless — callers pass the request, the owner and (for the writes) the
    freshly-persisted entry's uid. Write failures are collected into
    ``ShareOutcome`` rather than raised; the caller decides whether to
    compensate (delete what it created) or surface them.
    """

    def __init__(
        self,
        sharing_service: UnifiedSharingService | None,
        group_service: GroupService | None,
    ) -> None:
        self.sharing_service = sharing_service
        self.group_service = group_service
        self.logger = logger

    # =========================================================================
    # 1. VALIDATE — the pure rules
    # =========================================================================

    def validate(self, request: UserEntryCreateRequest) -> Result[None]:
        """The audience rules that need no lookup (ADR-088 §1, §8).

        - A private pipeline (``not Pipeline.allows_sharing()``) or a
          ``private: true`` entry cannot be *shared*: a ``group:``, ``user:``
          or ``public`` value is refused. A feedback request (``teachers`` /
          ``teacher:``) is Submit, not Share, and stays allowed.
        - ``pipeline=TEACHER_REVIEW`` with an explicit audience that names no
          feedback target is refused with guidance: a ``group:`` is a share
          and puts the entry in no queue (R5) — ``teacher:<group_uid>`` asks
          that group's teacher. An absent audience means ``teachers``.
        - A caller-supplied uid is the living channel — a draft, upserted in
          place (R9) — and a draft is never submitted or shared: an audience
          naming anyone is refused (``private`` names no one and stands). A
          vault note's audience rides on the frozen copy ``status: submitted``
          files, never on the note.
        """
        spec = request.audience
        if request.uid and (spec.names_feedback_target or spec.names_share):
            return Result.fail(
                Errors.validation(
                    "an entry with a caller-supplied uid is a living draft and is never "
                    f"submitted or shared (audience: {', '.join(spec.values())}) — remove "
                    "the uid to create a submission, or share the entry after it exists",
                    field="audience",
                )
            )
        if spec.names_share and not request.pipeline.allows_sharing():
            return Result.fail(
                Errors.validation(
                    f"pipeline={request.pipeline.value} is private (journals are not "
                    "shareable); a feedback request (teachers / teacher:<group_uid>) "
                    "is still allowed",
                    field="audience",
                )
            )
        if spec.names_share and request.private:
            return Result.fail(
                Errors.validation(
                    "a private entry (private: true) cannot be shared — remove the "
                    "group: / user: / public audience, or the private flag; a feedback "
                    "request (teachers / teacher:<group_uid>) is still allowed",
                    field="audience",
                )
            )
        if (
            request.pipeline == Pipeline.TEACHER_REVIEW
            and not spec.is_empty
            and not spec.names_feedback_target
        ):
            return Result.fail(
                Errors.validation(
                    "pipeline=teacher_review asks a teacher for feedback, but the "
                    f"audience ({', '.join(spec.values())}) names no teacher: a group: "
                    "share lets its members see the work and puts it in no queue. To "
                    "ask this group's teacher for feedback, use teacher:<group_uid> "
                    "(or teachers for all your teachers); a share may stand beside it",
                    field=FEEDBACK_TARGET_FIELD,
                )
            )
        return Result.ok(None)

    # =========================================================================
    # 2. VALIDATE REFERENCES — every target authorised before the first write
    # =========================================================================

    async def validate_references(
        self,
        user_uid: UserUID,
        request: UserEntryCreateRequest,
    ) -> Result[ResolvedAudience]:
        """Verify every claim the request makes, and resolve its audience to uids.

        Reference claims (any door can name any uid):
          - ``fulfills_exercise_uid``: the user must own the exercise, belong
            to a group it is shared with, be in progress on a PathStep it is
            linked to, or be the student a revision names — otherwise
            ``forbidden``.
          - ``transforms_of_uid``: the predecessor must be the user's own
            (``forbidden``), and must exist (``not_found``).
          - ``about_path_step_uid``: a published PathStep (``PATH_STEP_FAR_END``
            under ``link_edge_guard``'s rule) — it becomes the turn-in
            Interaction's ``INTERACTION_DURING`` edge. Anything else (a uid that
            names nothing, another user's entity, another kind of node, a draft)
            is ``not_found`` of the PathStep, one answer for all of them.

        Audience targets (ADR-088 §7-§8; "every door validates every target
        before its first write"):
          - ``user:<username>``: exists and shares a group with the owner
            (R8, default-group roster excluded) — unknown and non-co-member
            get one uniform not-found; the owner's own username is refused.
          - ``group:`` / ``teacher:``: exists, active, and the owner is a
            member or owner — one uniform not-found otherwise.
          - ``teachers`` (explicit, or the TEACHER_REVIEW default): with an
            exercise, the exercise's teacher directly — the teacher its vault
            file names (ADR-091 S3); a revision's is the exercise it revises
            (N8); a reviewer, never the submitter. Without an exercise, every
            group the owner is a student of. Expanded only on TEACHER_REVIEW —
            elsewhere it names a reviewer the pipeline never has and writes
            nothing. Explicit ``teacher:`` targets are validated on every
            pipeline.
          - A TEACHER_REVIEW request whose feedback targets resolve to no
            group and no teacher is refused here, pre-persist: an entry no
            teacher can open is never written.

        Without a sharing service the reference checks fail closed and any
        audience that needs a lookup is refused.
        """
        sharing = self.sharing_service
        spec = request.audience

        if sharing is None:
            needs_lookup = bool(
                request.fulfills_exercise_uid
                or request.transforms_of_uid
                or request.about_path_step_uid
                or spec.share_users
                or spec.group_targets
                or (request.pipeline == Pipeline.TEACHER_REVIEW and not spec.private)
            )
            if needs_lookup:
                return Result.fail(
                    Errors.forbidden(
                        action="resolve references",
                        reason=(
                            "Cannot verify referenced entities or audience targets — "
                            "sharing service unavailable."
                        ),
                    )
                )
            return Result.ok(ResolvedAudience(public=spec.public))

        refs = await self._validate_reference_claims(user_uid, request)
        if refs.is_error:
            return Result.fail(refs)

        people = await self.resolve_people(user_uid, spec.share_users)
        if people.is_error:
            return Result.fail(people)
        share_users = list(people.value)

        groups_check = await self.check_groups_reachable(user_uid, spec.group_targets)
        if groups_check.is_error:
            return Result.fail(groups_check)

        teacher_groups: tuple[str, ...] = spec.teacher_groups
        teachers_groups: tuple[str, ...] = ()
        submit_teachers: tuple[TeacherTarget, ...] = ()
        if request.pipeline == Pipeline.TEACHER_REVIEW and (spec.teachers or spec.is_empty):
            expanded = await self._expand_teachers(user_uid, request.fulfills_exercise_uid)
            if expanded.is_error:
                return Result.fail(expanded)
            teachers_groups, submit_teachers = expanded.value
            if not teacher_groups and not teachers_groups and not submit_teachers:
                return Result.fail(
                    Errors.validation(
                        "Submission reached no teacher: "
                        + (
                            "no teacher reviews this exercise for you"
                            if request.fulfills_exercise_uid
                            else "you are a student in no group"
                        )
                        + " — no feedback request could be filed",
                        field=FEEDBACK_TARGET_FIELD,
                    )
                )

        return Result.ok(
            ResolvedAudience(
                teacher_groups=teacher_groups,
                teachers_groups=teachers_groups,
                submit_teachers=submit_teachers,
                share_groups=tuple(spec.share_groups),
                share_users=tuple(share_users),
                public=spec.public,
            )
        )

    async def resolve_people(
        self, user_uid: UserUID, usernames: tuple[str, ...]
    ) -> Result[tuple[tuple[str, str], ...]]:
        """Resolve every ``user:<username>`` target to ``(username, uid)`` — each a verified co-member (R8).

        Unknown and non-co-member get one uniform not-found; the owner's own
        username is refused. Shared by the create path and the share door
        (``EntrySharingService``): one check, two doors.
        """
        sharing = self.sharing_service
        if sharing is None:
            if not usernames:
                return Result.ok(())
            return Result.fail(
                Errors.forbidden(
                    action="resolve recipients",
                    reason="Cannot verify recipients — sharing service unavailable.",
                )
            )
        share_users: list[tuple[str, str]] = []
        for username in usernames:
            resolved = await sharing.resolve_co_member(user_uid, username)
            if resolved.is_error:
                return Result.fail(resolved)
            recipient_uid = resolved.value
            if recipient_uid is None:
                return Result.fail(
                    Errors.not_found(resource="User", identifier=f"{USER_PREFIX}{username}")
                )
            if recipient_uid == user_uid:
                return Result.fail(
                    Errors.validation(
                        f"{USER_PREFIX}{username} is you — an entry is not shared with its owner",
                        field="audience",
                    )
                )
            share_users.append((username, recipient_uid))
        return Result.ok(tuple(share_users))

    async def check_groups_reachable(
        self, user_uid: UserUID, group_uids: tuple[str, ...]
    ) -> Result[None]:
        """Refuse any group target that does not exist, is inactive, or the user neither joined nor owns — one not-found for all three.

        One read for every target, whichever verb names it. Shared by the
        create path and the share door.
        """
        if not group_uids:
            return Result.ok(None)
        sharing = self.sharing_service
        if sharing is None:
            return Result.fail(
                Errors.forbidden(
                    action="resolve groups",
                    reason="Cannot verify group targets — sharing service unavailable.",
                )
            )
        reachable = await sharing.reachable_groups(user_uid, list(group_uids))
        if reachable.is_error:
            return Result.fail(reachable)
        for group_uid in group_uids:
            if group_uid not in reachable.value:
                return Result.fail(Errors.not_found(resource="Group", identifier=group_uid))
        return Result.ok(None)

    async def _validate_reference_claims(
        self,
        user_uid: UserUID,
        request: UserEntryCreateRequest,
    ) -> Result[None]:
        """The exercise / predecessor / PathStep-context claims — see ``validate_references``."""
        assert self.sharing_service is not None  # caller gates
        backend = self.sharing_service.backend
        fulfills_exercise_uid = request.fulfills_exercise_uid
        transforms_of_uid = request.transforms_of_uid

        if fulfills_exercise_uid:
            allowed = await backend.query_user_can_use_exercise(
                exercise_uid=EntityUID(fulfills_exercise_uid),
                user_uid=user_uid,
            )
            if allowed.is_error:
                return Result.fail(allowed)
            if not allowed.value:
                return Result.fail(
                    Errors.forbidden(
                        action="submit for exercise",
                        reason=(
                            f"Exercise {fulfills_exercise_uid} belongs to no PathStep "
                            "you are in progress on, and it is not a revision "
                            "addressed to you."
                        ),
                    )
                )

        if transforms_of_uid:
            owner = await backend.query_entity_owner(entity_uid=EntityUID(transforms_of_uid))
            if owner.is_error:
                return Result.fail(owner)
            if owner.value is None:
                return Result.fail(
                    Errors.not_found(resource="UserEntry", identifier=transforms_of_uid)
                )
            if owner.value != user_uid:
                return Result.fail(
                    Errors.forbidden(
                        action="transform predecessor entry",
                        reason=(f"Predecessor entry {transforms_of_uid} belongs to another user."),
                    )
                )

        if request.about_path_step_uid:
            admitted = await admit_far_ends_for_owner(
                backend,
                owner_uid=user_uid,
                far_uids=[request.about_path_step_uid],
                far_end=PATH_STEP_FAR_END,
            )
            if admitted.is_error:
                return Result.fail(admitted)

        return Result.ok(None)

    async def _expand_teachers(
        self,
        user_uid: UserUID,
        exercise_uid: str | None,
    ) -> Result[tuple[tuple[str, ...], tuple[TeacherTarget, ...]]]:
        """``teachers`` as concrete group uids, or a teacher to ask directly — see ``validate_references``.

        Returns ``(groups, teachers)``; at most one of the two is non-empty.

        Backend: SharingBackend.query_exercise_teacher;
        GroupService.get_user_groups (student role) without an exercise.
        """
        assert self.sharing_service is not None  # caller gates
        backend = self.sharing_service.backend
        if exercise_uid is None:
            if self.group_service is None:
                return Result.ok(((), ()))
            groups = await self.group_service.get_user_groups(
                user_uid, role=GroupMemberRole.STUDENT.value
            )
            if groups.is_error:
                return Result.fail(groups)
            return Result.ok((tuple(g.uid for g in (groups.value or [])), ()))

        # The exercise's teacher, asked directly: the teacher its vault file names
        # (REVIEWED_BY, ADR-091 S3). A revision resolves to the exercise it revises
        # (N8). The backend read is the whole rule (reviewer role, active, not the
        # submitter): zero rows for anything else, which leaves the request with no
        # target and refused.
        direct = await backend.query_exercise_teacher(
            exercise_uid=EntityUID(exercise_uid),
            user_uid=user_uid,
        )
        if direct.is_error:
            return Result.fail(direct)
        teachers: list[TeacherTarget] = []
        for record in direct.value or []:
            raw = record.get("teacher_uid") if isinstance(record, dict) else None
            if raw and all(t.teacher_uid != str(raw) for t in teachers):
                teachers.append(TeacherTarget(teacher_uid=str(raw), exercise_uid=exercise_uid))
        return Result.ok(((), tuple(teachers)))

    # =========================================================================
    # 3. RESOLVE & SHARE — the post-persist writes
    # =========================================================================

    async def resolve_and_share(
        self,
        entry_uid: str,
        user_uid: UserUID,
        pipeline: Pipeline,
        resolved: ResolvedAudience,
    ) -> Result[ShareOutcome]:
        """Write the links for a validated audience. Returns which targets landed.

        Each write re-checks its own authorisation in its statement (the
        group MERGEs' membership guard, the person MERGE's co-membership
        guard), so a change between validation and here is a collected
        failure, never an unauthorised edge. On any pipeline other than
        TEACHER_REVIEW a feedback target writes no link — it names a
        reviewer the pipeline never has — and is logged, never silently
        dropped; no feedback request (``SUBMITTED_TO_GROUP``,
        ``SUBMITTED_TO_TEACHER``) is ever written off-pipeline.
        """
        sharing = self.sharing_service
        if sharing is None:
            return Result.ok(ShareOutcome())

        submitted_groups: list[str] = []
        newly_submitted_groups: list[str] = []
        submitted_teachers: list[str] = []
        newly_submitted_teachers: list[str] = []
        shared_groups: list[str] = []
        shared_users: list[str] = []
        newly_shared_users: list[str] = []
        failed: list[tuple[str, str]] = []

        for group_uid in resolved.share_groups:
            result = await sharing.share_with_group(
                entity_uid=EntityUID(entry_uid),
                owner_uid=user_uid,
                group_uid=group_uid,
            )
            if result.is_error:
                reason = str(result.expect_error())
                self.logger.warning(
                    f"Failed to share UserEntry {entry_uid} with group {group_uid}: {reason}"
                )
                failed.append((group_uid, reason))
            else:
                shared_groups.append(group_uid)

        for username, recipient_uid in resolved.share_users:
            result = await sharing.share(
                entity_uid=EntityUID(entry_uid),
                owner_uid=user_uid,
                recipient_uid=recipient_uid,
            )
            if result.is_error:
                reason = str(result.expect_error())
                self.logger.warning(
                    f"Failed to share UserEntry {entry_uid} with user {recipient_uid}: {reason}"
                )
                failed.append((f"{USER_PREFIX}{username}", reason))
            else:
                shared_users.append(recipient_uid)
                if result.value:
                    newly_shared_users.append(recipient_uid)

        if pipeline != Pipeline.TEACHER_REVIEW and resolved.submit_teachers:
            self.logger.warning(
                f"UserEntry {entry_uid}: a direct feedback request to "
                f"{', '.join(t.teacher_uid for t in resolved.submit_teachers)} on "
                f"pipeline={pipeline.value} — no feedback request written."
            )

        if pipeline != Pipeline.TEACHER_REVIEW and resolved.submit_groups:
            self.logger.warning(
                f"UserEntry {entry_uid}: feedback target "
                f"{', '.join(TEACHER_PREFIX + g for g in resolved.submit_groups)} on "
                f"pipeline={pipeline.value} asks for feedback a pipeline without a reviewer "
                "cannot give — no feedback request written. Use group:<uid> to share with "
                "a group, or pipeline: teacher_review to ask its teacher for feedback."
            )

        if pipeline != Pipeline.TEACHER_REVIEW or not (
            resolved.submit_groups or resolved.submit_teachers
        ):
            return Result.ok(
                ShareOutcome(
                    shared_groups=tuple(shared_groups),
                    shared_users=tuple(shared_users),
                    newly_shared_users=tuple(newly_shared_users),
                    failed=tuple(failed),
                )
            )

        for group_uid in resolved.submit_groups:
            submit_result = await sharing.submit_to_group(
                entity_uid=EntityUID(entry_uid),
                owner_uid=user_uid,
                group_uid=group_uid,
            )
            if submit_result.is_error:
                reason = str(submit_result.expect_error())
                self.logger.warning(
                    f"Failed to submit UserEntry {entry_uid} to group {group_uid}: {reason}"
                )
                failed.append((group_uid, reason))
                continue
            submitted_groups.append(group_uid)
            if submit_result.value:
                newly_submitted_groups.append(group_uid)

        for target in resolved.submit_teachers:
            teacher_result = await sharing.submit_to_teacher(
                entity_uid=EntityUID(entry_uid),
                owner_uid=user_uid,
                teacher_uid=target.teacher_uid,
                exercise_uid=target.exercise_uid,
            )
            if teacher_result.is_error:
                reason = str(teacher_result.expect_error())
                self.logger.warning(
                    f"Failed to submit UserEntry {entry_uid} to teacher "
                    f"{target.teacher_uid}: {reason}"
                )
                failed.append((target.teacher_uid, reason))
                continue
            submitted_teachers.append(target.teacher_uid)
            if teacher_result.value:
                newly_submitted_teachers.append(target.teacher_uid)

        return Result.ok(
            ShareOutcome(
                submitted_groups=tuple(submitted_groups),
                newly_submitted_groups=tuple(newly_submitted_groups),
                submitted_teachers=tuple(submitted_teachers),
                newly_submitted_teachers=tuple(newly_submitted_teachers),
                shared_groups=tuple(shared_groups),
                shared_users=tuple(shared_users),
                newly_shared_users=tuple(newly_shared_users),
                failed=tuple(failed),
            )
        )


__all__ = [
    "FEEDBACK_TARGET_FIELD",
    "AudienceResolver",
    "ResolvedAudience",
    "ShareFailurePayload",
    "ShareOutcome",
    "ShareOutcomePayload",
    "TeacherTarget",
]
