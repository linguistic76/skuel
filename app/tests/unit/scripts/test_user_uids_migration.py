"""The user-uid migration's pure parts — where a uid is found, how a value moves.

The graph half runs in ``tests/integration/migrations/test_user_uids_migration.py``.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "migrations" / "user_uids_2026_10.py"
_spec = importlib.util.spec_from_file_location("user_uids_2026_10", SCRIPT)
assert _spec is not None and _spec.loader is not None
migration = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = migration
_spec.loader.exec_module(migration)

OLD = "user_admin"
NEW = "user_819f725e53621059"
MOVES = {OLD: NEW}
NAMES = migration.uid_pattern(MOVES)


class TestWhereAUidIsFound:
    @pytest.mark.parametrize(
        "text",
        [
            OLD,
            f"REVIEWED_BY|outgoing|{OLD}",
            f"edge:{OLD}|SHARES_WITH|task_x",
            f"/app/data/reports/{OLD}/ue_x/feedback.md",
            f"Ask {OLD}.",
            f"Ask {OLD}, then",
            f'{{"admin_uid": "{OLD}"}}',
            f"teacher: '{OLD}'",
        ],
    )
    def test_every_context_a_uid_is_written_in(self, text: str) -> None:
        assert NAMES.search(text), text

    @pytest.mark.parametrize(
        "text", [f"{OLD}_backup", f"{OLD}.x", f"ku.{OLD}", f"x{OLD}", f"{OLD}-2", "user_adm"]
    )
    def test_a_longer_uid_holding_it_is_not_it(self, text: str) -> None:
        assert not NAMES.search(text), text


class TestHowAValueMoves:
    def test_a_whole_value(self) -> None:
        assert migration.rewrite_of(OLD, MOVES, NAMES, tracker=False) == ("rewrite", NEW)

    def test_a_list_element(self) -> None:
        assert migration.rewrite_of(["a", OLD], MOVES, NAMES, tracker=False) == (
            "rewrite",
            ["a", NEW],
        )

    def test_a_string_in_a_json_map(self) -> None:
        before = json.dumps({"admin_uid": OLD, "n": 1})
        assert migration.rewrite_of(before, MOVES, NAMES, tracker=False) == (
            "rewrite",
            json.dumps({"admin_uid": NEW, "n": 1}),
        )

    def test_a_tracker_rows_edge_key_moves_by_token(self) -> None:
        key = f"REVIEWED_BY|outgoing|{OLD}"
        assert migration.rewrite_of([key], MOVES, NAMES, tracker=True) == (
            "rewrite",
            [f"REVIEWED_BY|outgoing|{NEW}"],
        )

    def test_the_same_key_off_a_tracker_row_quotes_it(self) -> None:
        key = f"REVIEWED_BY|outgoing|{OLD}"
        assert migration.rewrite_of([key], MOVES, NAMES, tracker=False) == ("quotes", None)

    def test_prose_quotes_it(self) -> None:
        assert migration.rewrite_of(f"Ask {OLD}.", MOVES, NAMES, tracker=False) == (
            "quotes",
            None,
        )

    def test_json_that_does_not_read_back_to_its_text_quotes_it(self) -> None:
        assert migration.rewrite_of(f'{{"a":"{OLD}"}}', MOVES, NAMES, tracker=False) == (
            "quotes",
            None,
        )

    def test_a_value_naming_none_is_untouched(self) -> None:
        assert migration.rewrite_of("user_other", MOVES, NAMES, tracker=False) == (
            "untouched",
            None,
        )


class TestOwnerLines:
    @pytest.mark.parametrize(
        ("line", "key", "value"),
        [
            (f"teacher: {OLD}", "teacher", OLD),
            (f'user_uid: "{OLD}"', "user_uid", OLD),
            ("ownership: 'linguistic76'", "ownership", "linguistic76"),
            (f"teacher:{OLD}  \r", "teacher", OLD),
            ("ownership: admin # my account", "ownership", "admin"),
        ],
    )
    def test_an_owner_key_and_its_value(self, line: str, key: str, value: str) -> None:
        match = migration._owner_value(line)
        assert match is not None and (match["key"], match["value"]) == (key, value)

    @pytest.mark.parametrize(
        "line",
        [
            f"author: {OLD}",
            f"teacher: {OLD} and more",
            f"- {OLD}",
            f"teacher: [{OLD}]",
            "ownership: admin#x",  # YAML reads the value as `admin#x`
            "  ownership: admin",  # nested, not the file's owner
        ],
    )
    def test_anything_else(self, line: str) -> None:
        assert migration._owner_value(line) is None

    @pytest.mark.parametrize(
        ("key", "value", "uid"),
        [
            ("ownership", "linguistic76", "user_linguistic76"),
            ("user_uid", "linguistic76", "user_linguistic76"),
            ("ownership", "user_linguistic76", "user_linguistic76"),
            ("teacher", "admin", "admin"),
        ],
    )
    def test_a_bare_username_names_its_old_uid_only_where_ingestion_read_one(
        self, key: str, value: str, uid: str
    ) -> None:
        assert migration._named_uid(key, value) == uid


class TestDeclaredOwners:
    def test_a_markdown_file_declares_in_its_frontmatter_as_ingestion_reads_it(self) -> None:
        text = "---\nownership: >-\n  admin\nteacher: user_admin\n---\nownership: body\n"
        assert migration._declared_owners(Path("n.md"), text) == {
            "ownership": "admin",
            "teacher": "user_admin",
        }

    def test_a_yaml_file_declares_at_its_top_level(self) -> None:
        text = "ownership: 1234\nnested:\n  user_uid: user_x\n"
        assert migration._declared_owners(Path("e.yaml"), text) == {"ownership": "1234"}

    @pytest.mark.parametrize(
        ("name", "text"),
        [
            ("n.md", "no fence\nownership: admin\n"),
            ("n.md", "---\nownership: [admin]\n---\n"),
            ("e.yml", "ownership: [unclosed\n"),
        ],
    )
    def test_nothing_ingestion_refuses_anyway(self, name: str, text: str) -> None:
        assert migration._declared_owners(Path(name), text) == {}


class TestOwnerSettings:
    def test_a_setting_naming_a_renamed_user_is_printed(self) -> None:
        environ = {"SKUEL_DEFAULT_USER_UID": "user_linguistic76", "SKUEL_CONTENT_VAULT_OWNER": OLD}
        moves = {**MOVES, "user_linguistic76": "user_bf2a1c0e8d7f6a51"}
        assert migration.owner_settings(moves, environ) == [
            "SKUEL_DEFAULT_USER_UID=user_bf2a1c0e8d7f6a51",
            f"SKUEL_CONTENT_VAULT_OWNER={NEW}",
        ]

    def test_an_unset_content_owner_stood_for_the_admin(self) -> None:
        assert migration.owner_settings(MOVES, {}) == [f"SKUEL_CONTENT_VAULT_OWNER={NEW}"]

    def test_a_setting_already_on_a_user_uid_is_left(self) -> None:
        assert migration.owner_settings(MOVES, {"SKUEL_CONTENT_VAULT_OWNER": NEW}) == []
