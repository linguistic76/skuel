"""The JSON an LLM reply holds, fenced or bare (core/utils/llm_json.py)."""

import json

import pytest

from core.utils.llm_json import parse_json_reply


@pytest.mark.parametrize(
    "reply",
    [
        '[{"theme": "leadership"}]',
        '  [{"theme": "leadership"}]\n',
        '```json\n[{"theme": "leadership"}]\n```',
        '```\n[{"theme": "leadership"}]\n```',
        'Here are the themes:\n```json\n[{"theme": "leadership"}]\n```\nHope this helps.',
        # A reply cut off at its token limit loses the closing fence, not the value.
        '```json\n[{"theme": "leadership"}]',
    ],
)
def test_the_value_is_read_fenced_or_bare(reply: str) -> None:
    assert parse_json_reply(reply) == [{"theme": "leadership"}]


def test_the_shape_is_the_callers_to_check() -> None:
    assert parse_json_reply('{"themes": []}') == {"themes": []}
    assert parse_json_reply("42") == 42


@pytest.mark.parametrize(
    "reply",
    ["Here are the themes: leadership, mindfulness", "", "```json\n```", "```json\nnot json\n```"],
)
def test_a_reply_that_holds_no_json_raises(reply: str) -> None:
    with pytest.raises(json.JSONDecodeError):
        parse_json_reply(reply)
