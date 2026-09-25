"""The one audience vocabulary — ``AudienceSpec.parse`` (ADR-088).

The parser matrix every door shares: the web form, the JSON API and the
vault's ``audience:`` frontmatter all reach ``AudienceSpec.parse``, so this
file is the contract for what each of them accepts.
"""

import pytest

from core.models.user_entry.audience import VOCABULARY, AudienceSpec


class TestParseValues:
    def test_none_is_the_empty_spec(self):
        spec = AudienceSpec.parse(None).value
        assert spec == AudienceSpec()
        assert spec.is_empty
        assert not spec.private

    @pytest.mark.parametrize("raw", ["", "  ", [], [""]])
    def test_blank_is_the_empty_spec(self, raw):
        assert AudienceSpec.parse(raw).value.is_empty

    def test_teachers(self):
        assert AudienceSpec.parse("teachers").value == AudienceSpec(teachers=True)

    def test_teacher_group(self):
        assert AudienceSpec.parse("teacher:g_math").value == AudienceSpec(
            teacher_groups=("g_math",)
        )

    def test_group(self):
        assert AudienceSpec.parse("group:g_class").value == AudienceSpec(share_groups=("g_class",))

    def test_user(self):
        assert AudienceSpec.parse("user:alice").value == AudienceSpec(share_users=("alice",))

    def test_public(self):
        assert AudienceSpec.parse("public").value == AudienceSpec(public=True)

    def test_private(self):
        spec = AudienceSpec.parse("private").value
        assert spec == AudienceSpec(private=True)
        assert not spec.is_empty

    def test_a_list_combines_values(self):
        spec = AudienceSpec.parse(["teachers", "user:alice", "group:g1", "public"]).value
        assert spec == AudienceSpec(
            teachers=True, share_users=("alice",), share_groups=("g1",), public=True
        )

    def test_an_already_parsed_spec_passes_through(self):
        spec = AudienceSpec(teachers=True)
        assert AudienceSpec.parse(spec).value is spec


class TestCaseAndWhitespace:
    def test_keywords_are_case_insensitive(self):
        assert AudienceSpec.parse(["Teachers", "PUBLIC"]).value == AudienceSpec(
            teachers=True, public=True
        )

    def test_the_payload_keeps_its_case(self):
        """A username matches ``User.title`` exactly — never lowercased."""
        spec = AudienceSpec.parse(["User:Alice", "Group:G_Class", "TEACHER:G_Math"]).value
        assert spec.share_users == ("Alice",)
        assert spec.share_groups == ("G_Class",)
        assert spec.teacher_groups == ("G_Math",)

    def test_whitespace_is_stripped(self):
        spec = AudienceSpec.parse(["  teachers ", " user: alice "]).value
        assert spec == AudienceSpec(teachers=True, share_users=("alice",))

    def test_duplicates_collapse_in_order(self):
        spec = AudienceSpec.parse(["group:b", "group:a", "group:b"]).value
        assert spec.share_groups == ("b", "a")


class TestErrors:
    @pytest.mark.parametrize("raw", ["everyone", "peers", "teacher", "grp:x"])
    def test_unknown_value_names_the_vocabulary(self, raw):
        result = AudienceSpec.parse(raw)
        assert result.is_error
        message = result.expect_error().message
        assert raw in message
        for word in VOCABULARY:
            assert word in message

    @pytest.mark.parametrize("raw", ["teacher:", "group: ", "user:"])
    def test_an_empty_payload_is_an_error(self, raw):
        result = AudienceSpec.parse(raw)
        assert result.is_error
        assert "must name a target" in result.expect_error().message

    @pytest.mark.parametrize(
        "raw",
        [
            ["private", "teachers"],
            ["private", "user:bob"],
            ["group:g1", "private"],
            ["private", "public"],
        ],
    )
    def test_private_combines_with_nothing(self, raw):
        """Never a silent choice of which wins (ADR-088 § The one audience vocabulary)."""
        result = AudienceSpec.parse(raw)
        assert result.is_error
        assert "combines with no other value" in result.expect_error().message

    def test_private_twice_is_still_private(self):
        assert AudienceSpec.parse(["private", "private"]).value == AudienceSpec(private=True)

    @pytest.mark.parametrize("raw", [7, {"a": 1}, [1], ["teachers", None]])
    def test_non_strings_are_errors(self, raw):
        assert AudienceSpec.parse(raw).is_error

    def test_every_error_is_on_the_audience_field(self):
        for raw in ("bogus", ["private", "teachers"], 7, "user:"):
            error = AudienceSpec.parse(raw).expect_error()
            assert error.details.get("field") == "audience"


class TestDerivedViews:
    def test_names_feedback_target(self):
        assert AudienceSpec(teachers=True).names_feedback_target
        assert AudienceSpec(teacher_groups=("g",)).names_feedback_target
        assert not AudienceSpec(share_groups=("g",)).names_feedback_target
        assert not AudienceSpec(private=True).names_feedback_target

    def test_names_share(self):
        assert AudienceSpec(share_groups=("g",)).names_share
        assert AudienceSpec(share_users=("u",)).names_share
        assert AudienceSpec(public=True).names_share
        assert not AudienceSpec(teachers=True).names_share
        assert not AudienceSpec(teacher_groups=("g",)).names_share

    def test_group_targets_span_both_verbs_without_repeats(self):
        spec = AudienceSpec(teacher_groups=("g1", "g2"), share_groups=("g2", "g3"))
        assert spec.group_targets == ("g1", "g2", "g3")

    def test_values_round_trip_through_parse(self):
        spec = AudienceSpec.parse(
            ["teachers", "teacher:g1", "group:g2", "user:Alice", "public"]
        ).value
        assert AudienceSpec.parse(list(spec.values())).value == spec
        assert AudienceSpec(private=True).values() == ("private",)
