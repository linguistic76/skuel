"""SharingBackend — cross-entity sharing relationships."""

from __future__ import annotations

from typing import TYPE_CHECKING

from adapters.persistence.neo4j.query.cypher.crud_queries import build_audience_fragment
from adapters.persistence.neo4j.query.cypher.learning_loop_fragments import (
    build_review_standing_subquery,
)
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.entity import Entity
from core.models.enums.entity_enums import EntityType
from core.models.enums.user_entry_enums import ExerciseScope
from core.models.group.group import DEFAULT_GROUP_UID_PREFIX
from core.models.relationship_names import RelationshipName
from core.models.type_hints import EntityUID, Neo4jProperties, UserUID
from core.ports.query_types import VIA_DIRECT
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.exercises.revised_exercise import RevisedExercise  # noqa: F401
    from core.models.forms.form_template import FormTemplate  # noqa: F401
    from core.models.group.group import Group  # noqa: F401
    from core.models.interaction.interaction import Interaction  # noqa: F401
    from core.models.resource.resource import Resource  # noqa: F401


def build_co_membership_fragment(owner_alias: str, recipient_alias: str) -> str:
    """The one R8 co-membership predicate (ADR-088 §7), as a Cypher boolean.

    Two users share a group when both reach one **active** group through
    ``MEMBER_OF`` or ``OWNS`` — except through a default group, where only a
    pair that includes the group's owner counts: its roster is the whole
    enrolled platform, its owner is the student's teacher. The default group
    is recognised by its uid prefix, bound as ``$default_group_prefix``
    (``DEFAULT_GROUP_UID_PREFIX``); the owner by the ``OWNS`` edge. Every
    caller binds that parameter; ``SharingBackend`` composes this fragment in
    the co-member reads and in the guarded person-share MERGE.
    """
    reach = f"[:{RelationshipName.MEMBER_OF.value}|{RelationshipName.OWNS.value}]"
    owns = f"[:{RelationshipName.OWNS.value}]"
    return (
        f"EXISTS {{ MATCH ({owner_alias})-{reach}->(cg:Group)<-{reach}-({recipient_alias}) "
        f"WHERE cg.is_active = true AND (NOT cg.uid STARTS WITH $default_group_prefix "
        f"OR ({owner_alias})-{owns}->(cg) OR ({recipient_alias})-{owns}->(cg)) }}"
    )


#: What the Shared page lists (R3): user-authored work only. Feedback types
#: (EntryReport, RevisedExercise) are GradeBook reads; a form submission is
#: kept as today.
SHARED_PAGE_ENTITY_TYPES: tuple[str, ...] = (
    EntityType.USER_ENTRY.value,
    EntityType.FORM_SUBMISSION.value,
)


class SharingBackend(UniversalNeo4jBackend[Entity]):
    """
    Domain backend for cross-domain sharing operations.

    All sharing queries target :Entity nodes by UID — there are no domain-specific
    predicates. Typed to Entity (the base class) since sharing spans all entity types.

    Moves sharing Cypher from the service layer into the persistence boundary,
    following the same pattern as PsBackend (ORGANIZES), LpBackend (progress),
    and ExerciseBackend (curriculum linking).

    See: /docs/patterns/SHARING_PATTERNS.md
    """

    async def create_share(
        self,
        entity_uid: EntityUID,
        owner_uid: UserUID,
        recipient_uid: str,
        role: str,
        share_version: str,
        shared_at: str,
        require_co_membership: bool,
    ) -> Result[list[Neo4jProperties]]:
        """Grant a person share: an idempotent ``SHARES_WITH`` MERGE from recipient to entity.

        The statement never shares an entity with its owner. With
        ``require_co_membership`` it also re-checks R8 in the write itself
        (``build_co_membership_fragment``): a membership change between
        validation and this write refuses here, never after. Without it (the
        forms' ``share_with_admin``, ADR-088 §7's one exemption) only the
        owner rule stands. A row is the success and carries ``created`` — ``true``
        when this call wrote the edge, ``false`` when the share already
        stood; no row is the refusal.
        """
        co_member = build_co_membership_fragment("owner", "recipient")
        result = await self.execute_query(
            f"""
            MATCH (owner:User {{uid: $owner_uid}})
            MATCH (recipient:User {{uid: $recipient_uid}})
            MATCH (entity:Entity {{uid: $entity_uid}})
            WHERE recipient.uid <> owner.uid
              AND (NOT $require_co_membership OR {co_member})
            MERGE (recipient)-[r:{RelationshipName.SHARES_WITH.value}]->(entity)
            WITH r, r.shared_at IS NULL AS created
            SET r.shared_at = coalesce(r.shared_at, datetime($shared_at)),
                r.role = $role,
                r.share_version = $share_version
            RETURN created
            """,
            {
                "owner_uid": owner_uid,
                "recipient_uid": recipient_uid,
                "entity_uid": entity_uid,
                "shared_at": shared_at,
                "role": role,
                "share_version": share_version,
                "require_co_membership": require_co_membership,
                "default_group_prefix": DEFAULT_GROUP_UID_PREFIX,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def query_co_member_uid(
        self,
        owner_uid: UserUID,
        username: str | None = None,
        recipient_uid: str | None = None,
    ) -> Result[list[Neo4jProperties]]:
        """The uid of one user, by exact ``username`` (``User.title``) or by uid, iff they share a group with ``owner_uid`` (R8).

        One row ``{uid}`` when the user exists and is a co-member under
        ``build_co_membership_fragment``; no row when they do not exist or
        are not — one answer for both, so a caller discloses nothing about
        who exists. The owner is their own co-member here (a group is shared
        with oneself trivially); the caller refuses that case.
        """
        if (username is None) == (recipient_uid is None):
            raise ValueError("query_co_member_uid takes exactly one of username / recipient_uid")
        key = "title" if username is not None else "uid"
        co_member = build_co_membership_fragment("owner", "recipient")
        result = await self.execute_query(
            f"""
            MATCH (owner:User {{uid: $owner_uid}})
            MATCH (recipient:User {{{key}: $recipient_key}})
            WHERE recipient.uid = owner.uid OR {co_member}
            RETURN recipient.uid AS uid
            LIMIT 1
            """,
            {
                "owner_uid": owner_uid,
                "recipient_key": username if username is not None else recipient_uid,
                "default_group_prefix": DEFAULT_GROUP_UID_PREFIX,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def query_reachable_groups(
        self,
        user_uid: UserUID,
        group_uids: list[str],
    ) -> Result[list[Neo4jProperties]]:
        """The subset of ``group_uids`` that exist, are active (strict) and the user is ``MEMBER_OF`` or ``OWNS``.

        The pre-write check for every ``group:`` / ``teacher:`` target: the
        group writers' own guards (``create_group_share``,
        ``create_group_submission``) apply the same condition in the write,
        so a target listed here is one they will accept unless membership
        changes in between. Rows ``{group_uid}``.
        """
        result = await self.execute_query(
            f"""
            MATCH (u:User {{uid: $user_uid}})-[:{RelationshipName.MEMBER_OF.value}|{RelationshipName.OWNS.value}]->(g:Group)
            WHERE g.uid IN $group_uids AND g.is_active = true
            RETURN DISTINCT g.uid AS group_uid
            """,
            {"user_uid": user_uid, "group_uids": list(group_uids)},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def delete_share(
        self,
        entity_uid: EntityUID,
        recipient_username: str,
    ) -> Result[list[Neo4jProperties]]:
        """Retract one person share: delete the ``SHARES_WITH`` edge from the user named ``recipient_username`` (exact ``User.title``) to the entity.

        No co-membership check: an owner may always take back what they gave,
        even after the recipient left every shared group. ``deleted_count``
        is 0 when no such edge stood.
        """
        result = await self.execute_query(
            f"""
            MATCH (recipient:User {{title: $username}})-[r:{RelationshipName.SHARES_WITH.value}]->(entity:Entity {{uid: $entity_uid}})
            DELETE r
            RETURN count(r) as deleted_count
            """,
            {"username": recipient_username, "entity_uid": entity_uid},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def update_visibility(
        self,
        entity_uid: EntityUID,
        owner_uid: str,
        visibility: str,
    ) -> Result[list[Neo4jProperties]]:
        """Set visibility property on an owned entity."""
        result = await self.execute_query(
            """
            MATCH (ku:Entity {uid: $entity_uid})
            WHERE ku.user_uid = $owner_uid
            SET ku.visibility = $visibility,
                ku.updated_at = datetime()
            RETURN ku.uid as uid
            """,
            {
                "entity_uid": entity_uid,
                "owner_uid": owner_uid,
                "visibility": visibility,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def query_ownership_and_status(
        self,
        entity_uid: EntityUID,
    ) -> Result[list[Neo4jProperties]]:
        """Query ownership, status and the two privacy fields for the combined ownership + shareable check.

        ``private`` and ``pipeline`` are the UserEntry fields the lifetime
        share rule reads (ADR-088 §1); null on every other label.

        Ownership lives in two shapes: user-owned domains stamp a ``user_uid``
        property; curriculum entities (e.g. Exercise) stamp ``owner_uid`` and
        dual-write the canonical ``:OWNS`` edge (a failed edge write now fails
        the create — ADR-086 — but property-without-edge nodes predate that).
        Resolve user_uid → owner_uid → edge,
        mirroring ``verify_ownership`` in crud_operations_mixin — the two
        layers must agree on who owns a node. Neither → unowned, unshareable.
        """
        result = await self.execute_query(
            """
            MATCH (entity:Entity {uid: $entity_uid})
            OPTIONAL MATCH (owner:User)-[:OWNS]->(entity)
            RETURN coalesce(entity.user_uid, entity.owner_uid, owner.uid) as actual_owner,
                   entity.status as status,
                   entity.entity_type as entity_type,
                   entity.private as private,
                   entity.pipeline as pipeline
            """,
            {"entity_uid": entity_uid},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def query_shared_with_me(
        self,
        user_uid: UserUID,
        limit: int,
        entity_type: str | None = None,
        sharer_uid: UserUID | None = None,
        via: str | None = None,
    ) -> Result[list[Neo4jProperties]]:
        """The *Shared with you* read: every UserEntry or FormSubmission the share links name the viewer for, one row per entity.

        Candidates are enumerated from the viewer's two reach patterns — a
        direct ``SHARES_WITH``, and ``MEMBER_OF`` / ``OWNS`` of an active
        group the entity is ``SHARED_WITH_GROUP`` to — and every row is then
        gated by ``build_audience_fragment`` (ADR-088 §5): whatever this
        lists, ``/gradebook/{uid}`` opens. The viewer's own entries are
        excluded through their ``:OWNS`` edge (the self-share guard's read
        half). A feedback request (``SUBMITTED_TO_GROUP``) is never a share
        and never appears; feedback types (EntryReport, RevisedExercise) live
        in the GradeBook, never here (R3).

        Columns: ``entity``, ``shared_by`` (the owner's display name),
        ``sharer_uid`` (the owner), ``shared_at`` (the newest share, as an
        ISO string), ``via_direct`` and ``via_groups`` (``[{uid, name}]``) —
        the via-list — and the derived review standing, ``reviewed_by`` /
        ``revised_after_feedback`` (``build_review_standing_subquery``, the
        badges' one derivation; a FormSubmission has no reports and reads
        unreviewed). ``entity_type`` / ``sharer_uid`` / ``via`` narrow the
        rows (``None`` = no filter); ``via`` is ``direct`` or a group uid, so
        the ``/groups`` list is this reader narrowed to one group.
        """
        shares = RelationshipName.SHARES_WITH.value
        shared_with_group = RelationshipName.SHARED_WITH_GROUP.value
        reach = f"{RelationshipName.MEMBER_OF.value}|{RelationshipName.OWNS.value}"
        owns = RelationshipName.OWNS.value
        audience = build_audience_fragment("entity")
        review_standing = build_review_standing_subquery("entity")
        result = await self.execute_query(
            f"""
            MATCH (viewer:User {{uid: $user_uid}})
            CALL (viewer) {{
                MATCH (viewer)-[r:{shares}]->(entity:Entity)
                RETURN entity, true AS direct, null AS group, r.shared_at AS at
                UNION
                MATCH (viewer)-[:{reach}]->(g:Group)<-[r:{shared_with_group}]-(entity:Entity)
                WHERE g.is_active = true
                RETURN entity, false AS direct, g AS group, r.shared_at AS at
            }}
            WITH viewer, entity,
                 max(CASE WHEN direct THEN 1 ELSE 0 END) = 1 AS via_direct,
                 collect(DISTINCT CASE WHEN group IS NULL THEN null
                                       ELSE {{uid: group.uid, name: group.name}} END) AS via_groups_raw,
                 max(at) AS shared_at
            WHERE entity.entity_type IN $entity_types
              AND NOT (viewer)-[:{owns}]->(entity)
              AND {audience}
              AND ($entity_type IS NULL OR entity.entity_type = $entity_type)
              AND ($sharer_uid IS NULL OR entity.user_uid = $sharer_uid)
            WITH entity, via_direct, shared_at,
                 [x IN via_groups_raw WHERE x IS NOT NULL] AS via_groups
            WHERE $via IS NULL
               OR ($via = $direct_token AND via_direct)
               OR $via IN [x IN via_groups | x.uid]
            {review_standing}
            OPTIONAL MATCH (owner:User {{uid: entity.user_uid}})
            RETURN entity,
                   toString(shared_at) AS shared_at,
                   coalesce(owner.display_name, owner.title, entity.user_uid) AS shared_by,
                   entity.user_uid AS sharer_uid,
                   via_direct,
                   via_groups,
                   reviewed_by,
                   revised_after_feedback
            ORDER BY shared_at DESC
            LIMIT $limit
            """,
            {
                "user_uid": user_uid,
                "limit": limit,
                "entity_type": entity_type,
                "sharer_uid": sharer_uid,
                "via": via,
                "direct_token": VIA_DIRECT,
                "entity_types": list(SHARED_PAGE_ENTITY_TYPES),
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def query_shared_by_me(
        self,
        user_uid: UserUID,
        limit: int,
        entity_uid: EntityUID | None = None,
    ) -> Result[list[Neo4jProperties]]:
        """*Your wall*: the viewer's own UserEntries that carry at least one share link, with their audience.

        One row per entry: ``entity``, ``users`` (``[{uid, username,
        display_name, shared_at}]`` — every ``SHARES_WITH`` recipient),
        ``groups`` (``[{uid, name, shared_at}]`` — every ``SHARED_WITH_GROUP``
        target), ``last_shared_at`` (the newest of them, ISO), and the derived
        review standing ``reviewed_by`` / ``revised_after_feedback`` (the
        badges' one derivation, ``build_review_standing_subquery``). A feedback
        request is not a share and is not listed. With ``entity_uid`` the
        read narrows to one entry — the Share panel's "already shared with"
        state and the owner's access list are this one query, never a second.
        """
        shares = RelationshipName.SHARES_WITH.value
        shared_with_group = RelationshipName.SHARED_WITH_GROUP.value
        owns = RelationshipName.OWNS.value
        review_standing = build_review_standing_subquery("entity")
        result = await self.execute_query(
            f"""
            MATCH (owner:User {{uid: $user_uid}})-[:{owns}]->(entity:Entity {{entity_type: $user_entry}})
            WHERE $entity_uid IS NULL OR entity.uid = $entity_uid
            WITH entity,
                 [(recipient:User)-[r:{shares}]->(entity) |
                    {{uid: recipient.uid, username: recipient.title,
                      display_name: coalesce(recipient.display_name, recipient.title),
                      shared_at: toString(r.shared_at)}}] AS users,
                 [(entity)-[r:{shared_with_group}]->(g:Group) |
                    {{uid: g.uid, name: g.name, shared_at: toString(r.shared_at)}}] AS groups
            WHERE size(users) > 0 OR size(groups) > 0
            WITH entity, users, groups,
                 reduce(latest = null, s IN [x IN users | x.shared_at] + [x IN groups | x.shared_at] |
                        CASE WHEN latest IS NULL OR s > latest THEN s ELSE latest END) AS last_shared_at
            {review_standing}
            RETURN entity, users, groups, last_shared_at, reviewed_by, revised_after_feedback
            ORDER BY last_shared_at DESC
            LIMIT $limit
            """,
            {
                "user_uid": user_uid,
                "limit": limit,
                "entity_uid": entity_uid,
                "user_entry": EntityType.USER_ENTRY.value,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def query_feedback_request_groups(
        self, entity_uid: EntityUID
    ) -> Result[list[Neo4jProperties]]:
        """The groups an entry was submitted to for feedback (``SUBMITTED_TO_GROUP``), one ``{uid}`` row each.

        What the GradeBook nudge preselects in the Share panel — read for
        the panel only, and applied only to groups the panel already offers.
        """
        submitted = RelationshipName.SUBMITTED_TO_GROUP.value
        result = await self.execute_query(
            f"""
            MATCH (:Entity {{uid: $entity_uid}})-[:{submitted}]->(g:Group)
            RETURN g.uid AS uid
            """,
            {"entity_uid": entity_uid},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def query_co_members(self, owner_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Every user the owner may share with (R8, ADR-088 §7): the people under ``build_co_membership_fragment``.

        The default group's roster is excluded and its owner kept, exactly as
        the person-share MERGE decides. Rows ``{uid, username, display_name}``,
        ordered by display name; never the owner.
        """
        co_member = build_co_membership_fragment("owner", "recipient")
        result = await self.execute_query(
            f"""
            MATCH (owner:User {{uid: $owner_uid}})
            MATCH (recipient:User)
            WHERE recipient.uid <> owner.uid AND {co_member}
            RETURN recipient.uid AS uid,
                   recipient.title AS username,
                   coalesce(recipient.display_name, recipient.title) AS display_name
            ORDER BY toLower(display_name)
            """,
            {"owner_uid": owner_uid, "default_group_prefix": DEFAULT_GROUP_UID_PREFIX},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def create_group_share(
        self,
        entity_uid: EntityUID,
        owner_uid: UserUID,
        group_uid: str,
        share_version: str,
        shared_at: str,
    ) -> Result[list[Neo4jProperties]]:
        """Create SHARED_WITH_GROUP relationship, guarded by owner relationship.

        The sharer must either OWN the target group (teacher sharing curriculum
        with their own class) or be MEMBER_OF it (student sharing a
        UserEntry with a group they belong to). Without either edge the
        ``OPTIONAL MATCH`` collapses and the ``WHERE`` predicate rejects the
        row — callers translate the empty result into a forbidden error,
        preventing users from sharing to groups they have no relationship to.
        """
        result = await self.execute_query(
            """
            MATCH (entity:Entity {uid: $entity_uid})
            MATCH (group:Group {uid: $group_uid})
            WHERE coalesce(group.is_active, true) = true
            OPTIONAL MATCH (owner:User {uid: $owner_uid})-[:MEMBER_OF]->(group)
              WHERE coalesce(owner.is_active, true) = true
            OPTIONAL MATCH (owner2:User {uid: $owner_uid})-[:OWNS]->(group)
              WHERE coalesce(owner2.is_active, true) = true
            WITH entity, group, owner, owner2
            WHERE owner IS NOT NULL OR owner2 IS NOT NULL
            MERGE (entity)-[r:SHARED_WITH_GROUP]->(group)
              ON CREATE SET r.shared_at = datetime($shared_at),
                            r.share_version = $share_version
            RETURN true as success
            """,
            {
                "entity_uid": entity_uid,
                "owner_uid": owner_uid,
                "group_uid": group_uid,
                "shared_at": shared_at,
                "share_version": share_version,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def create_group_submission(
        self,
        entity_uid: EntityUID,
        owner_uid: UserUID,
        group_uid: str,
        submitted_at: str,
    ) -> Result[list[Neo4jProperties]]:
        """File a feedback request: an idempotent ``SUBMITTED_TO_GROUP`` MERGE to an owned or joined active group.

        The same membership guard as ``create_group_share`` — the submitter
        must be ``MEMBER_OF`` or ``OWNS`` the group, and the group must be
        active (strict ``is_active = true``: a deactivated group grants
        nothing, ADR-088 §3). Without a qualifying edge the ``OPTIONAL MATCH``
        collapses and no row comes back — that empty result is the forbidden
        failure.

        A row is the success, and it carries ``created``: ``true`` when this
        call wrote the edge, ``false`` when the request already stood (the
        MERGE matched). Both are successes to the caller; ``created`` is what
        rings the teacher's bell once per new request, never on a re-sync.
        ``submitted_at`` is stamped only on create, so the stamp records the
        first filing.
        """
        result = await self.execute_query(
            f"""
            MATCH (entity:Entity {{uid: $entity_uid}})
            MATCH (group:Group {{uid: $group_uid}})
            WHERE group.is_active = true
            OPTIONAL MATCH (owner:User {{uid: $owner_uid}})-[:{RelationshipName.MEMBER_OF.value}]->(group)
              WHERE coalesce(owner.is_active, true) = true
            OPTIONAL MATCH (owner2:User {{uid: $owner_uid}})-[:{RelationshipName.OWNS.value}]->(group)
              WHERE coalesce(owner2.is_active, true) = true
            WITH entity, group, owner, owner2
            WHERE owner IS NOT NULL OR owner2 IS NOT NULL
            MERGE (entity)-[r:{RelationshipName.SUBMITTED_TO_GROUP.value}]->(group)
            WITH r, r.submitted_at IS NULL AS created
            SET r.submitted_at = coalesce(r.submitted_at, datetime($submitted_at))
            RETURN created
            """,
            {
                "entity_uid": entity_uid,
                "owner_uid": owner_uid,
                "group_uid": group_uid,
                "submitted_at": submitted_at,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def query_exercise_groups_for_member(
        self,
        exercise_uid: EntityUID,
        user_uid: UserUID,
    ) -> Result[list[Neo4jProperties]]:
        """Return the groups the exercise is shared with AND the user belongs to.

        Used for auto-share scoping: when a submission fulfills an exercise
        that was assigned to multiple groups, only fan out to the ones the
        submitter is actually in. A RevisedExercise target resolves to the
        exercise it revises — a revision is never assigned to a group itself,
        so a turn-in against it reaches the root exercise's reviewers.
        """
        result = await self.execute_query(
            f"""
            MATCH (target:Entity {{uid: $exercise_uid}})
            OPTIONAL MATCH (target)-[:{RelationshipName.REVISES_EXERCISE.value}]->(orig:Entity {{entity_type: $exercise_type}})
            WITH coalesce(orig, target) AS ex
            MATCH (ex)-[:{RelationshipName.SHARED_WITH_GROUP.value}]->(g:Group)
            WHERE coalesce(g.is_active, true) = true
            MATCH (u:User {{uid: $user_uid}})-[:{RelationshipName.MEMBER_OF.value}]->(g)
            WHERE coalesce(u.is_active, true) = true
            RETURN g.uid AS group_uid
            """,
            {
                "exercise_uid": exercise_uid,
                "user_uid": user_uid,
                "exercise_type": EntityType.EXERCISE.value,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def query_default_groups_for_curriculum_submission(
        self,
        exercise_uid: EntityUID,
        user_uid: UserUID,
    ) -> Result[list[Neo4jProperties]]:
        """Fallback review route for CURRICULUM exercises: the submitter's default group(s).

        Curriculum exercises are vault-authored and never ASSIGNED to a group,
        so the assignment-intersection auto-share resolves to nothing and a
        teacher_review submission would dissolve unseen. Ruled 2026-07-04:
        such submissions share with the submitter's default group (the group
        every enrolled student auto-joins, recognised by
        ``DEFAULT_GROUP_UID_PREFIX`` and owned by the default teacher). Scope-gated in Cypher: a non-curriculum
        exercise returns zero rows, so PERSONAL submissions can never leak to
        the default group through this path. A RevisedExercise target resolves
        to the exercise it revises, so a revision of a curriculum exercise
        takes the same route; a revision whose original is gone resolves to
        nothing.
        """
        result = await self.execute_query(
            f"""
            MATCH (target:Entity {{uid: $exercise_uid}})
            OPTIONAL MATCH (target)-[:{RelationshipName.REVISES_EXERCISE.value}]->(orig:Entity {{entity_type: $exercise_type}})
            WITH coalesce(orig, target) AS ex
            WHERE ex.entity_type = $exercise_type AND ex.scope = $curriculum_scope
            MATCH (u:User {{uid: $user_uid}})-[:{RelationshipName.MEMBER_OF.value}]->(g:Group)
            WHERE g.uid STARTS WITH $default_group_prefix
              AND coalesce(g.is_active, true) = true
            RETURN g.uid AS group_uid
            """,
            {
                "exercise_uid": exercise_uid,
                "user_uid": user_uid,
                "exercise_type": EntityType.EXERCISE.value,
                "curriculum_scope": ExerciseScope.CURRICULUM.value,
                "default_group_prefix": DEFAULT_GROUP_UID_PREFIX,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def query_user_can_use_exercise(
        self,
        exercise_uid: EntityUID,
        user_uid: UserUID,
    ) -> Result[bool]:
        """Verify the user has a legitimate relationship to an exercise.

        True if any hold:
          - user owns the exercise (teacher previewing their own)
          - exercise is SHARED_WITH_GROUP with a group the user is a member of
          - exercise is linked to a PathStep the user is currently in progress on
          - the target is a RevisedExercise addressed to the user (its
            ``student_uid``) — a revision is answered by the student it names

        Prevents YAML uploads from smuggling ``fulfills_exercise_uid`` values
        for exercises the uploader has no legitimate tie to.
        """
        result = await self.execute_query(
            f"""
            MATCH (ex:Entity {{uid: $exercise_uid}})
            OPTIONAL MATCH (ex)-[:{RelationshipName.SHARED_WITH_GROUP.value}]->(g:Group)<-[:{RelationshipName.MEMBER_OF.value}]-(:User {{uid: $user_uid}})
            OPTIONAL MATCH (:User {{uid: $user_uid}})-[:{RelationshipName.IN_PROGRESS.value}]->(ps:Entity)-[:{RelationshipName.HAS_EXERCISE.value}]->(ex)
            WITH ex.user_uid = $user_uid AS is_owner,
                 count(g) > 0 AS via_group,
                 count(ps) > 0 AS via_progress,
                 (ex.entity_type = $revised_exercise_type AND ex.student_uid = $user_uid) AS is_revision_target
            RETURN (is_owner OR via_group OR via_progress OR is_revision_target) AS allowed
            """,
            {
                "exercise_uid": exercise_uid,
                "user_uid": user_uid,
                "revised_exercise_type": EntityType.REVISED_EXERCISE.value,
            },
        )
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.ok(False)
        return Result.ok(bool(records[0].get("allowed")))

    async def query_entity_owner(
        self,
        entity_uid: EntityUID,
    ) -> Result[str | None]:
        """Return the ``user_uid`` of an entity's owner, or None if missing."""
        result = await self.execute_query(
            """
            MATCH (e:Entity {uid: $entity_uid})
            RETURN e.user_uid AS owner_uid
            """,
            {"entity_uid": entity_uid},
        )
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.ok(None)
        owner = records[0].get("owner_uid")
        return Result.ok(str(owner) if owner is not None else None)

    async def delete_group_share(
        self,
        entity_uid: EntityUID,
        group_uid: str,
    ) -> Result[list[Neo4jProperties]]:
        """Retract one group share: delete the ``SHARED_WITH_GROUP`` edge between the entity and the group.

        Touches ``SHARED_WITH_GROUP`` only — a feedback request
        (``SUBMITTED_TO_GROUP``) is a different kind and cannot be cancelled
        here (ADR-088 §2). ``deleted_count`` is 0 when no share stood.
        """
        result = await self.execute_query(
            f"""
            MATCH (entity:Entity {{uid: $entity_uid}})-[r:{RelationshipName.SHARED_WITH_GROUP.value}]->(group:Group {{uid: $group_uid}})
            DELETE r
            RETURN count(r) as deleted_count
            """,
            {"entity_uid": entity_uid, "group_uid": group_uid},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])
