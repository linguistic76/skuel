#!/usr/bin/env python3
"""
DeepgramAdapter per-call option merge
=====================================

``TranscriptionPort.transcribe`` takes a ``TranscriptionProcessOptions`` rather
than a ``**overrides`` bag. Every field on that model has a default, so the
adapter must dump it with ``exclude_unset=True`` — a plain ``model_dump()``
reasserts the model's defaults over ``config/deepgram.toml``, so a caller
passing only ``diarize=True`` would silently reset the configured model and
language.

These drive the real ``DeepgramAdapter.transcribe`` and read the
``PrerecordedOptions`` it actually hands the SDK; only the network call is
stubbed. The merge is invisible against the shipped config, where all five
overridable values happen to equal the model's defaults — so the fixture uses a
config that differs on every one of them, which is what makes it observable.
"""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from adapters.external.deepgram.adapter import DeepgramAdapter
from core.config.deepgram_config import DeepgramConfig
from core.models.transcription.transcription import TranscriptionProcessOptions

# Deliberately unlike TranscriptionProcessOptions' defaults on all five
# overridable fields, so any leaked default is visible.
_DIVERGENT = DeepgramConfig(
    model="nova-3",
    language="es",
    punctuate=False,
    paragraphs=False,
    diarize=True,
)


class _StubResponse:
    """Minimal stand-in for the SDK response — the extractors all fall through."""

    results = None


@pytest.fixture
def audio_file(tmp_path) -> str:
    path = tmp_path / "clip.wav"
    path.write_bytes(b"\x00\x01")
    return str(path)


async def _options_sent(audio_file: str, options: TranscriptionProcessOptions | None) -> Any:
    """Run the real transcribe() and return the PrerecordedOptions it built."""
    adapter = DeepgramAdapter(api_key="test-key", config=_DIVERGENT)
    with patch.object(
        adapter, "_transcribe_raw", new=AsyncMock(return_value=_StubResponse())
    ) as raw:
        result = await adapter.transcribe(audio_path=audio_file, options=options)
    assert result.is_ok, result.expect_error().message
    assert raw.await_args is not None, "transcribe() never reached the SDK call"
    # _transcribe_raw(audio_data, path, options)
    return raw.await_args.args[2]


@pytest.mark.asyncio
async def test_no_options_leaves_every_configured_value_intact(audio_file):
    sent = await _options_sent(audio_file, None)

    assert sent.model == "nova-3"
    assert sent.language == "es"
    assert sent.punctuate is False
    assert sent.paragraphs is False
    assert sent.diarize is True


@pytest.mark.asyncio
async def test_single_override_touches_only_that_field(audio_file):
    """The regression this file exists for: diarize must not drag defaults along."""
    sent = await _options_sent(audio_file, TranscriptionProcessOptions(diarize=False))

    assert sent.diarize is False  # the one field the caller set
    # …and nothing else moved off the config
    assert sent.model == "nova-3"
    assert sent.language == "es"
    assert sent.punctuate is False
    assert sent.paragraphs is False


@pytest.mark.asyncio
async def test_explicit_value_equal_to_the_model_default_still_overrides(audio_file):
    """exclude_unset keys off *set*, not off *differs from the model default*."""
    sent = await _options_sent(audio_file, TranscriptionProcessOptions(model="nova-2"))

    assert sent.model == "nova-2"  # explicitly set, even though it is the default
    assert sent.language == "es"  # untouched


@pytest.mark.asyncio
async def test_multiple_overrides_apply_together(audio_file):
    sent = await _options_sent(
        audio_file, TranscriptionProcessOptions(model="whisper-large", language="fr")
    )

    assert sent.model == "whisper-large"
    assert sent.language == "fr"
    assert sent.punctuate is False
    assert sent.diarize is True
