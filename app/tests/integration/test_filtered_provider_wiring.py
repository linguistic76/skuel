"""
The composed app hands the daily plan only facades that can serve a filtered context.

``compose_services`` registers a facade per domain name as a
``FilteredContextProvider``; the intelligence factory passes that registry to every
``UserContextIntelligence`` it creates. This reads the registry off the bootstrapped
app — the real facades, as wired — and holds each one to the protocol. The unit
counterpart (``tests/unit/test_filtered_context_provider_wiring.py``) covers the
check itself; this one covers what composition actually registered.
"""

from types import SimpleNamespace
from typing import cast

import pytest

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.ports.filtered_context_protocols import FilteredContextProvider
from core.services.user.unified_user_context import RichUserContext

pytestmark = pytest.mark.skipif(
    IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
    reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
)

_ACTIVITY_DOMAINS = {"tasks", "goals", "habits", "events", "choices", "principles"}


@pytest.mark.asyncio
async def test_every_composed_provider_serves_a_filtered_context(skuel_app) -> None:
    factory = skuel_app.state.services.context_intelligence
    assert factory is not None
    # The registry reaches a consumer through create(); the context is not read here.
    context = cast("RichUserContext", SimpleNamespace(user_uid="user_wiring_probe"))
    providers = factory.create(context).filtered_providers

    assert set(providers) >= _ACTIVITY_DOMAINS, "the daily plan asks for each Activity domain"
    not_providers = {
        domain: type(facade).__name__
        for domain, facade in providers.items()
        if not isinstance(facade, FilteredContextProvider)
    }
    assert not_providers == {}
