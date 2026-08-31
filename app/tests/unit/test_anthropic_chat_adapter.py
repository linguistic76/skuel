"""
Unit tests for AnthropicChatAdapter (W1 chat-completion boundary).

Covers system-as-parameter placement, model override, TextBlock extraction,
non-text first block → empty text, exception → Result.fail, and the empty-key
fail-fast. The Anthropic SDK call is mocked — no network. TextBlock is patched
to a simple stand-in so the isinstance check is exercised without depending on
the real (versioned) pydantic model constructor.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

import adapters.external.llm.anthropic_adapter as anthropic_mod
from adapters.external.llm import AnthropicChatAdapter


class _FakeTextBlock:
    def __init__(self, text: str) -> None:
        self.text = text


@pytest.fixture(autouse=True)
def patch_textblock(monkeypatch):
    """Patch TextBlock so isinstance(block, TextBlock) is testable."""
    monkeypatch.setattr(anthropic_mod, "TextBlock", _FakeTextBlock)


def _adapter() -> AnthropicChatAdapter:
    adapter = AnthropicChatAdapter(api_key="test-key")
    adapter._client = MagicMock()
    return adapter


def _message(first_block):
    msg = MagicMock()
    msg.content = [first_block]
    return msg


def test_fail_fast_without_api_key():
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        AnthropicChatAdapter(api_key="")


@pytest.mark.asyncio
async def test_complete_extracts_textblock():
    adapter = _adapter()
    adapter._client.messages.create = AsyncMock(return_value=_message(_FakeTextBlock("hello")))

    result = await adapter.complete([{"role": "user", "content": "hi"}])

    assert result.is_ok
    assert result.value.text == "hello"
    assert result.value.model == "claude-sonnet-4-6"  # default
    assert result.value.usage is None


@pytest.mark.asyncio
async def test_system_passed_as_parameter_and_model_override():
    adapter = _adapter()
    adapter._client.messages.create = AsyncMock(return_value=_message(_FakeTextBlock("ok")))

    await adapter.complete(
        [{"role": "user", "content": "hi"}],
        system_prompt="Be terse.",
        model="claude-opus-4-7",
    )

    kwargs = adapter._client.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-opus-4-7"
    assert kwargs["system"] == "Be terse."
    assert kwargs["messages"] == [{"role": "user", "content": "hi"}]


@pytest.mark.asyncio
async def test_non_text_block_yields_empty_text():
    adapter = _adapter()
    adapter._client.messages.create = AsyncMock(return_value=_message(MagicMock()))

    result = await adapter.complete([{"role": "user", "content": "hi"}])

    assert result.is_ok
    assert result.value.text == ""


@pytest.mark.asyncio
async def test_exception_mapped_to_integration_error():
    adapter = _adapter()
    adapter._client.messages.create = AsyncMock(side_effect=RuntimeError("boom"))

    result = await adapter.complete([{"role": "user", "content": "hi"}])

    assert result.is_error
    assert "anthropic" in str(result.expect_error()).lower()


# ============================================================================
# select_tool — native tool selection (Askesis tool-selection first slice)
# ============================================================================


class _FakeToolUseBlock:
    def __init__(self, name: str, input_: dict) -> None:
        self.name = name
        self.input = input_


@pytest.fixture
def patch_tooluseblock(monkeypatch):
    """Patch ToolUseBlock so isinstance(block, ToolUseBlock) is testable."""
    monkeypatch.setattr(anthropic_mod, "ToolUseBlock", _FakeToolUseBlock)


def _tool_spec():
    from core.ports.llm_protocols import ToolSpec

    return ToolSpec(
        name="count_goals_achieved",
        description="count achieved goals",
        input_schema={"type": "object", "properties": {"period": {"type": "string"}}},
    )


@pytest.mark.asyncio
async def test_select_tool_passes_flat_tool_specs_and_auto_choice(patch_tooluseblock):
    """The provider request carries the flat Anthropic tool shape and
    tool_choice=auto — auto is what keeps "no tool fits" expressible, the only
    decline the model can make. No sampling params: the 1.x SDK removed
    temperature from messages.create()."""
    adapter = _adapter()
    adapter._client.messages.create = AsyncMock(
        return_value=_message(_FakeToolUseBlock("count_goals_achieved", {"period": "last_quarter"}))
    )

    result = await adapter.select_tool(
        "how many goals last quarter?", [_tool_spec()], system_prompt="pick carefully"
    )

    assert result.is_ok
    assert result.value.tool_name == "count_goals_achieved"
    assert result.value.arguments == {"period": "last_quarter"}
    _, kwargs = adapter._client.messages.create.call_args
    assert kwargs["tools"] == [
        {
            "name": "count_goals_achieved",
            "description": "count achieved goals",
            "input_schema": {"type": "object", "properties": {"period": {"type": "string"}}},
        }
    ]
    assert kwargs["tool_choice"] == {"type": "auto"}
    assert kwargs["system"] == "pick carefully"
    assert "temperature" not in kwargs


@pytest.mark.asyncio
async def test_select_tool_no_tool_use_block_is_a_none_selection(patch_tooluseblock):
    """A text-only response = the model declined every tool — a NORMAL outcome
    (ToolSelection(tool_name=None)), never an error."""
    adapter = _adapter()
    adapter._client.messages.create = AsyncMock(return_value=_message(_FakeTextBlock("no tool")))

    result = await adapter.select_tool("what is stoicism?", [_tool_spec()])

    assert result.is_ok
    assert result.value.tool_name is None
    assert result.value.arguments == {}


@pytest.mark.asyncio
async def test_select_tool_sdk_error_is_a_typed_failure(patch_tooluseblock):
    adapter = _adapter()
    adapter._client.messages.create = AsyncMock(side_effect=RuntimeError("api down"))

    result = await adapter.select_tool("how many?", [_tool_spec()])

    assert result.is_error
