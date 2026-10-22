"""Tests for UID generation utilities (core/utils/uid_generator.py).

The generator mints the uid grammar's generated shape (``core/utils/uid_grammar.py``);
the slug it joins in is ``uid_grammar.slugify``.
"""

from __future__ import annotations

import pytest

from core.utils.uid_generator import UIDGenerator
from core.utils.uid_grammar import UidVerdict, classify


class TestGenerateUid:
    def test_semantic_uid_uses_slug(self):
        uid = UIDGenerator.generate_uid("task", "Implement Auth!")
        assert uid.startswith("task_implement-auth_")
        assert len(uid.rsplit("_", 1)[1]) == 8

    def test_semantic_uid_slug_is_ascii(self):
        assert UIDGenerator.generate_uid("task", "Café plan").startswith("task_cafe-plan_")

    def test_a_name_with_no_ascii_slug_mints_the_plain_shape(self):
        uid = UIDGenerator.generate_uid("task", "日本語")
        assert classify(uid) is UidVerdict.FITS, uid

    def test_random_uid_without_name(self):
        uid = UIDGenerator.generate_uid("er")
        prefix, suffix = uid.split("_", 1)
        assert prefix == "er"
        assert len(suffix) == 8
        assert classify(uid) is UidVerdict.FITS


class TestGenerateRandomUid:
    def test_fits_the_grammar(self):
        assert classify(UIDGenerator.generate_random_uid("task")) is UidVerdict.FITS

    @pytest.mark.parametrize("prefix", ["review_request", "Task", ""])
    def test_refuses_a_prefix_outside_the_grammar(self, prefix: str):
        with pytest.raises(ValueError, match="uid prefix"):
            UIDGenerator.generate_random_uid(prefix)
        with pytest.raises(ValueError, match="uid prefix"):
            UIDGenerator.generate_uid(prefix)
