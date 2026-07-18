"""One-shot seed/cleanup for the teacher-review IDOR live route smoke test.

Mirrors tests/integration/test_teacher_review_idor_isolation.py's
two_classroom_fixture into the live dev Neo4j and gives each teacher a
bcrypt-hashed login password so we can exercise the actual /api/teaching/*
route plumbing (auth + role gate + orchestrator + service + backend) end-to-end.

Usage:
    uv run python tests/manual/seed_idor_smoke_fixture.py seed
    uv run python tests/manual/seed_idor_smoke_fixture.py cleanup
"""

import asyncio
import sys
from datetime import UTC, datetime

from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection
from core.auth.password import hash_password
from core.models.enums import UserRole
from core.models.user import create_user
from core.utils.neo4j_mapper import to_neo4j_node

PASSWORD = "TestPassword123!"
TEACHER_A = "idor_smoke_teacher_a"
TEACHER_B = "idor_smoke_teacher_b"
STUDENT_1 = "idor_smoke_student_1"
STUDENT_2 = "idor_smoke_student_2"
GROUP_X = "idor_smoke_group_x"
GROUP_Y = "idor_smoke_group_y"
SUBMISSION_1 = "ue_idor_smoke_s1"
SUBMISSION_2 = "ue_idor_smoke_s2"


def _build_user_props(username: str, role: UserRole, password_hash: str) -> dict:
    user = create_user(
        username=username,
        email=f"{username}@example.com",
        display_name=username.replace("_", " ").title(),
        role=role,
        password_hash=password_hash,
        is_active=True,
        is_verified=True,
    )
    return to_neo4j_node(user)


async def seed() -> None:
    pw_hash = hash_password(PASSWORD)
    teacher_a_props = _build_user_props(TEACHER_A, UserRole.TEACHER, pw_hash)
    teacher_b_props = _build_user_props(TEACHER_B, UserRole.TEACHER, pw_hash)
    student_1_props = _build_user_props(STUDENT_1, UserRole.MEMBER, pw_hash)
    student_2_props = _build_user_props(STUDENT_2, UserRole.MEMBER, pw_hash)
    # Real ingested entries store timestamps as ISO strings (via
    # core/utils/neo4j_mapper.py:to_node which calls .isoformat()), NOT as
    # Cypher datetime() values. Using datetime($now) here would create
    # neo4j.time.DateTime objects that the JSON boundary can't serialize,
    # surfacing a fixture artifact rather than the real route plumbing.
    now = datetime.now(UTC).isoformat().replace("+00:00", "")

    async with Neo4jConnection() as conn:
        driver = conn.connect()

        # MERGE so re-running is idempotent. Stamp properties via SET.
        for props in (teacher_a_props, teacher_b_props, student_1_props, student_2_props):
            await driver.execute_query(
                "MERGE (u:User {uid: $uid}) SET u = $props",
                uid=props["uid"],
                props=props,
            )

        await driver.execute_query(
            """
            MERGE (gx:Group {uid: $group_x})
              SET gx.name = 'IDOR Group X', gx.is_active = true,
                  gx.entity_type = 'group', gx.title = 'IDOR Group X',
                  gx.created_at = $now, gx.updated_at = $now
            MERGE (gy:Group {uid: $group_y})
              SET gy.name = 'IDOR Group Y', gy.is_active = true,
                  gy.entity_type = 'group', gy.title = 'IDOR Group Y',
                  gy.created_at = $now, gy.updated_at = $now
            WITH gx, gy
            MATCH (ta:User {uid: $teacher_a})
            MATCH (tb:User {uid: $teacher_b})
            MATCH (s1:User {uid: $student_1})
            MATCH (s2:User {uid: $student_2})
            MERGE (ta)-[:OWNS]->(gx)
            MERGE (tb)-[:OWNS]->(gy)
            MERGE (s1)-[:MEMBER_OF {role: 'student'}]->(gx)
            MERGE (s2)-[:MEMBER_OF {role: 'student'}]->(gy)
            """,
            group_x=GROUP_X,
            group_y=GROUP_Y,
            now=now,
            teacher_a=f"user_{TEACHER_A}",
            teacher_b=f"user_{TEACHER_B}",
            student_1=f"user_{STUDENT_1}",
            student_2=f"user_{STUDENT_2}",
        )

        await driver.execute_query(
            """
            MERGE (sub1:Entity:UserEntry {uid: $sub1})
              SET sub1.entity_type = 'user_entry',
                  sub1.title = 'IDOR S1 submission',
                  sub1.status = 'submitted',
                  sub1.pipeline = 'teacher_review',
                  sub1.created_at = $now,
                  sub1.updated_at = $now,
                  sub1.user_uid = $student_1
            MERGE (sub2:Entity:UserEntry {uid: $sub2})
              SET sub2.entity_type = 'user_entry',
                  sub2.title = 'IDOR S2 submission',
                  sub2.status = 'submitted',
                  sub2.pipeline = 'teacher_review',
                  sub2.created_at = $now,
                  sub2.updated_at = $now,
                  sub2.user_uid = $student_2
            WITH sub1, sub2
            MATCH (s1:User {uid: $student_1})
            MATCH (s2:User {uid: $student_2})
            MATCH (gx:Group {uid: $group_x})
            MATCH (gy:Group {uid: $group_y})
            MERGE (s1)-[:OWNS]->(sub1)
            MERGE (s2)-[:OWNS]->(sub2)
            MERGE (sub1)-[:SHARED_WITH_GROUP]->(gx)
            MERGE (sub2)-[:SHARED_WITH_GROUP]->(gy)
            """,
            sub1=SUBMISSION_1,
            sub2=SUBMISSION_2,
            now=now,
            student_1=f"user_{STUDENT_1}",
            student_2=f"user_{STUDENT_2}",
            group_x=GROUP_X,
            group_y=GROUP_Y,
        )

        print("Seeded IDOR smoke fixture.")
        print(f"  Teacher A: username={TEACHER_A}, uid=user_{TEACHER_A}, password={PASSWORD}")
        print(f"  Teacher B: username={TEACHER_B}, uid=user_{TEACHER_B}, password={PASSWORD}")
        print(f"  Sub 1 (in classroom A): {SUBMISSION_1}")
        print(f"  Sub 2 (in classroom B): {SUBMISSION_2}")


async def cleanup() -> None:
    user_uids = [f"user_{u}" for u in (TEACHER_A, TEACHER_B, STUDENT_1, STUDENT_2)]
    async with Neo4jConnection() as conn:
        driver = conn.connect()
        await driver.execute_query(
            "UNWIND $uids AS uid MATCH (u:User {uid: uid}) DETACH DELETE u",
            uids=user_uids,
        )
        await driver.execute_query(
            "UNWIND $uids AS uid MATCH (g:Group {uid: uid}) DETACH DELETE g",
            uids=[GROUP_X, GROUP_Y],
        )
        await driver.execute_query(
            "UNWIND $uids AS uid MATCH (e:Entity {uid: uid}) DETACH DELETE e",
            uids=[SUBMISSION_1, SUBMISSION_2],
        )
        # Sessions + AuthEvents created by the live login flow:
        await driver.execute_query(
            "MATCH (u:User)-[:HAS_SESSION]->(s:Session) WHERE u.uid IN $uids DETACH DELETE s",
            uids=user_uids,
        )
        await driver.execute_query(
            "MATCH (e:AuthEvent) WHERE e.user_uid IN $uids DETACH DELETE e",
            uids=user_uids,
        )
        print(f"Cleaned up IDOR smoke fixture ({len(user_uids)} users + 2 groups + 2 entries).")


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in {"seed", "cleanup"}:
        print(__doc__)
        sys.exit(2)
    asyncio.run(seed() if sys.argv[1] == "seed" else cleanup())


if __name__ == "__main__":
    main()
