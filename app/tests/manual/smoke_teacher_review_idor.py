"""Live route smoke for the teacher-review IDOR fix (PR #99).

Exercises the actual HTTP plumbing — auth gate, role gate, orchestrator,
service, backend — for the three /api/teaching/* endpoints the
IDOR fix moved onto group-scoped Cypher. Complements the 9 integration
tests in tests/integration/test_teacher_review_idor_isolation.py, which
hit the backend directly and skip the route layer.

Prerequisite: ``uv run python tests/manual/seed_idor_smoke_fixture.py seed``
and the app running on http://localhost:8000.

To run: ``uv run python tests/manual/smoke_teacher_review_idor.py``
Cleanup: ``uv run python tests/manual/seed_idor_smoke_fixture.py cleanup``

Assertions:
 - Teacher A sees only their own classroom; cross-classroom probes
   (review queue, submission detail, student history) return disjoint.
 - Cross-classroom GET /api/teaching/review/{uid} → 404 (not 403),
   so a teacher outside the group can't distinguish "missing" from
   "exists in someone else's classroom".
 - Cross-classroom GET /api/teaching/students/{uid}/submissions → []
   (empty, not error).

Exits non-zero on the first failing assertion.
"""

import re
import sys

import httpx

BASE_URL = "http://localhost:8000"
PASSWORD = "TestPassword123!"

TEACHER_A_USER = "idor_smoke_teacher_a"
TEACHER_B_USER = "idor_smoke_teacher_b"
# Login via email — most seeded/historical users in the dev DB have
# u.username == None (only set during sign_up via the "/register" flow);
# the email branch of /login/submit takes the value as-is.
TEACHER_A_EMAIL = f"{TEACHER_A_USER}@example.com"
TEACHER_B_EMAIL = f"{TEACHER_B_USER}@example.com"
STUDENT_1_UID = "user_idor_smoke_student_1"
STUDENT_2_UID = "user_idor_smoke_student_2"
SUBMISSION_1_UID = "ue_idor_smoke_s1"
SUBMISSION_2_UID = "ue_idor_smoke_s2"

CSRF_FORM_RE = re.compile(r'name="csrf_token"\s+value="([^"]+)"')


def login(client: httpx.Client, email: str, expected_uid: str) -> None:
    """GET /login to seed the csrf_token cookie, then POST /login/submit."""
    login_page = client.get(f"{BASE_URL}/login")
    assert login_page.status_code == 200, f"GET /login → {login_page.status_code}"
    cookie_token = client.cookies.get("csrf_token")
    assert cookie_token, "no csrf_token cookie set by GET /login"

    form_match = CSRF_FORM_RE.search(login_page.text)
    assert form_match, "no csrf_token hidden field in /login HTML"
    form_token = form_match.group(1)
    assert form_token == cookie_token, "form/cookie csrf mismatch on page render"

    resp = client.post(
        f"{BASE_URL}/login/submit",
        data={"username": email, "password": PASSWORD, "csrf_token": form_token},
        follow_redirects=False,
    )
    assert resp.status_code == 303, (
        f"login POST → {resp.status_code}, expected 303 redirect. Body: {resp.text[:300]}"
    )
    # Session validation happens implicitly via the first /api/teaching/* call
    # below (401 if the cookie isn't set, 403 if not TEACHER role).
    print(f"  ✓ logged in as {email} (expected_uid={expected_uid})")


def get_json(client: httpx.Client, path: str) -> tuple[int, object]:
    resp = client.get(f"{BASE_URL}{path}", follow_redirects=False)
    try:
        return resp.status_code, resp.json()
    except Exception:
        return resp.status_code, resp.text


def check(label: str, condition: bool, detail: str = "") -> None:
    mark = "✓" if condition else "✗"
    print(f"  {mark} {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        print(f"FAIL: {label} ({detail})", file=sys.stderr)
        sys.exit(1)


def smoke_teacher(
    client: httpx.Client, who: str, *, expected_own_sub: str, foreign_sub: str, foreign_student: str
) -> None:
    print(f"\n[{who}] review queue")
    status, body = get_json(client, "/api/teaching/review-queue")
    check("HTTP 200", status == 200, f"got {status}: {str(body)[:200]}")
    assert isinstance(body, list)
    uids = {row.get("submission_uid") for row in body}
    check(
        f"own submission {expected_own_sub} in queue",
        expected_own_sub in uids,
        f"queue uids = {uids}",
    )
    check(
        f"foreign submission {foreign_sub} NOT in queue",
        foreign_sub not in uids,
        f"queue uids = {uids}",
    )

    print(f"[{who}] cross-classroom submission detail probe")
    status, body = get_json(client, f"/api/teaching/review/{foreign_sub}")
    check(
        f"GET /review/{foreign_sub} returns 404 (not 200/403)",
        status == 404,
        f"got {status}: {str(body)[:200]}",
    )

    print(f"[{who}] cross-classroom student history probe")
    status, body = get_json(client, f"/api/teaching/students/{foreign_student}/submissions")
    check(
        f"GET /students/{foreign_student}/submissions HTTP 200",
        status == 200,
        f"got {status}: {str(body)[:200]}",
    )
    check("foreign student history is empty", body == [], f"got {body}")

    print(f"[{who}] own submission detail (positive control)")
    status, body = get_json(client, f"/api/teaching/review/{expected_own_sub}")
    check(
        f"GET /review/{expected_own_sub} returns 200",
        status == 200,
        f"got {status}: {str(body)[:200]}",
    )
    check(
        "own submission detail uid matches",
        isinstance(body, dict) and body.get("uid") == expected_own_sub,
        f"got {body}",
    )


def main() -> None:
    print("=" * 70)
    print("Teacher-review IDOR live route smoke (PR #99)")
    print("=" * 70)

    # Teacher A
    with httpx.Client(timeout=10.0) as client:
        login(client, TEACHER_A_EMAIL, expected_uid=f"user_{TEACHER_A_USER}")
        smoke_teacher(
            client,
            "Teacher A",
            expected_own_sub=SUBMISSION_1_UID,
            foreign_sub=SUBMISSION_2_UID,
            foreign_student=STUDENT_2_UID,
        )

    # Teacher B — fresh client/cookies
    with httpx.Client(timeout=10.0) as client:
        login(client, TEACHER_B_EMAIL, expected_uid=f"user_{TEACHER_B_USER}")
        smoke_teacher(
            client,
            "Teacher B",
            expected_own_sub=SUBMISSION_2_UID,
            foreign_sub=SUBMISSION_1_UID,
            foreign_student=STUDENT_1_UID,
        )

    print("\n" + "=" * 70)
    print("✓ All route-layer IDOR isolation checks passed.")
    print("=" * 70)


if __name__ == "__main__":
    main()
