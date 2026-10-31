"""Reading the JSON an LLM reply holds.

A model asked for JSON often wraps it in a Markdown code fence (```` ```json …
``` ````), sometimes after a line of prose. ``parse_json_reply`` reads the first
fenced block when the reply has one and the whole reply when it has none. What
shape the value should have is the caller's to check: a judge wants an array, a
suggestion an object.
"""

import json

_FENCE = "```"


def parse_json_reply(text: str) -> object:
    """The JSON value in an LLM reply, read from its code fence when it has one.

    Raises:
        json.JSONDecodeError: the reply (or its fenced block) is not JSON.
    """
    if _FENCE in text:
        text = text.split(_FENCE)[1].removeprefix("json")
    return json.loads(text.strip())
