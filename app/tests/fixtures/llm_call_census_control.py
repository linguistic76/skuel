"""The prompt-sources census's control: one call to each LLM port method.

``tests/unit/test_prompt_sources_census.py`` runs its detector over this module
and must find exactly the calls marked ``# census: <method>`` (the marker sits on
the line the call starts), and the marked methods must be every port method the
census derives from the port classes. A detector that misses one of these
shapes, or a port method nobody marked, fails the census, so it can't go quietly
blind.

The receivers take the shapes the call sites in ``core/`` take: an attribute of
``self``, a parameter, a local, the value of a ``Result``, and a call split over
lines. Nothing imports this module at runtime; mypy checks that each call is a
real port method with real arguments.
"""

from __future__ import annotations

from core.ports.llm_protocols import ChatCompletionPort, ToolSelectionPort
from core.services.askesis.query_tools import ToolSelector
from core.services.base_ai_service import BaseAIService
from core.services.llm_caller import LLMCallerProtocol
from core.services.llm_service import LLMService
from core.utils.result_simplified import Result


class _Holder:
    """Ports held as attributes, the way the services in ``core/`` hold them."""

    def __init__(self, llm: LLMService, port: ChatCompletionPort) -> None:
        self.llm = llm
        self.port = port

    async def through_attributes(self) -> None:
        await self.llm.generate("p")  # census: generate
        await self.llm.generate_context_aware_answer(  # census: generate_context_aware_answer
            "q", "ctx"
        )
        await self.port.complete(  # census: complete
            [{"role": "user", "content": "p"}], system_prompt="s"
        )


async def through_parameters(
    caller: LLMCallerProtocol, selector: ToolSelectionPort, ai: BaseAIService
) -> None:
    await caller.generate("p", system_prompt="s")  # census: generate
    await caller.complete([{"role": "user", "content": "p"}])  # census: complete
    await caller.select_tool("q", [])  # census: select_tool
    await selector.select_tool("q", [])  # census: select_tool
    await ai._generate_insight("tasks_ai_insight")  # census: _generate_insight


async def through_locals(
    holder: _Holder, ports: Result[ChatCompletionPort], tools: ToolSelector
) -> None:
    llm = holder.llm
    await llm.select_tool("q", [])  # census: select_tool
    await ports.value.complete([])  # census: complete
    await tools.select_tool("q", [])  # census: select_tool
