"""
Deepgram Configuration Loader
===============================

Loads transcription options from config/deepgram.toml.
Provides a typed DeepgramConfig dataclass consumed by DeepgramAdapter.

See: config/deepgram.toml for all available options.
See: docs/configuration/DEEPGRAM_CONFIG.md for usage guide.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from core.utils.logging import get_logger

logger = get_logger("skuel.config.deepgram")

# Default config file path (relative to app root)
DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "deepgram.toml"


@dataclass(frozen=True)
class DeepgramConfig:
    """Typed Deepgram configuration loaded from config/deepgram.toml."""

    # Model & Language
    model: str = "nova-2"
    language: str = "en"
    detect_language: bool = False

    # Formatting
    smart_format: bool = True
    punctuate: bool = True
    paragraphs: bool = True
    numerals: bool = False
    measurements: bool = False
    filler_words: bool = False
    profanity_filter: bool = False
    dictation: bool = False

    # Utterances
    utterances: bool = True
    utt_split: float = 1.7

    # Speakers
    diarize: bool = False

    # Intelligence
    summarize: bool = False
    topics: bool = False
    intents: bool = False
    sentiment: bool = False
    detect_entities: bool = False

    # Vocabulary
    keywords: list[str] = field(default_factory=list)
    replace: list[str] = field(default_factory=list)
    redact: bool | str = False

    # Request
    timeout: float = 120.0
    alternatives: int = 1
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_toml(cls, path: Path | None = None) -> DeepgramConfig:
        """Load config from TOML file. Falls back to defaults if file is missing."""
        config_path = path or DEFAULT_CONFIG_PATH

        if not config_path.exists():
            logger.info(f"No Deepgram config at {config_path}, using defaults")
            return cls()

        try:
            with open(config_path, "rb") as f:
                raw = tomllib.load(f)
        except Exception as e:  # safety-net: bad TOML should not crash the app
            logger.warning(f"Failed to parse {config_path}: {e} — using defaults")
            return cls()

        # Flatten nested TOML sections into flat kwargs
        model_section = raw.get("model", {})
        fmt = raw.get("formatting", {})
        utt = raw.get("utterances", {})
        spk = raw.get("speakers", {})
        intel = raw.get("intelligence", {})
        vocab = raw.get("vocabulary", {})
        req = raw.get("request", {})

        config = cls(
            # Model
            model=model_section.get("name", cls.model),
            language=model_section.get("language", cls.language),
            detect_language=model_section.get("detect_language", cls.detect_language),
            # Formatting
            smart_format=fmt.get("smart_format", cls.smart_format),
            punctuate=fmt.get("punctuate", cls.punctuate),
            paragraphs=fmt.get("paragraphs", cls.paragraphs),
            numerals=fmt.get("numerals", cls.numerals),
            measurements=fmt.get("measurements", cls.measurements),
            filler_words=fmt.get("filler_words", cls.filler_words),
            profanity_filter=fmt.get("profanity_filter", cls.profanity_filter),
            dictation=fmt.get("dictation", cls.dictation),
            # Utterances
            utterances=utt.get("enabled", cls.utterances),
            utt_split=utt.get("split_threshold", cls.utt_split),
            # Speakers
            diarize=spk.get("diarize", cls.diarize),
            # Intelligence
            summarize=intel.get("summarize", cls.summarize),
            topics=intel.get("topics", cls.topics),
            intents=intel.get("intents", cls.intents),
            sentiment=intel.get("sentiment", cls.sentiment),
            detect_entities=intel.get("detect_entities", cls.detect_entities),
            # Vocabulary
            keywords=vocab.get("keywords", []),
            replace=vocab.get("replace", []),
            redact=vocab.get("redact", cls.redact),
            # Request
            timeout=req.get("timeout", cls.timeout),
            alternatives=req.get("alternatives", cls.alternatives),
            tags=req.get("tags", []),
        )

        logger.info(
            f"Loaded Deepgram config: model={config.model}, language={config.language}, "
            f"utt_split={config.utt_split}s, intelligence="
            f"{'on' if any([config.summarize, config.topics, config.sentiment, config.intents, config.detect_entities]) else 'off'}"
        )

        return config

    def to_transcribe_kwargs(self) -> dict:
        """Convert to kwargs dict for DeepgramAdapter.transcribe()."""
        return {
            "model": self.model,
            "language": self.language,
            "detect_language": self.detect_language,
            "smart_format": self.smart_format,
            "punctuate": self.punctuate,
            "paragraphs": self.paragraphs,
            "numerals": self.numerals,
            "measurements": self.measurements,
            "filler_words": self.filler_words,
            "profanity_filter": self.profanity_filter,
            "dictation": self.dictation,
            "utterances": self.utterances,
            "utt_split": self.utt_split,
            "diarize": self.diarize,
            "summarize": self.summarize,
            "topics": self.topics,
            "intents": self.intents,
            "sentiment": self.sentiment,
            "detect_entities": self.detect_entities,
            "keywords": self.keywords,
            "replace": self.replace,
            "redact": self.redact,
            "alternatives": self.alternatives,
            "tags": self.tags,
        }


def load_deepgram_config(path: Path | None = None) -> DeepgramConfig:
    """Convenience function to load Deepgram config."""
    return DeepgramConfig.from_toml(path)


__all__ = ["DeepgramConfig", "load_deepgram_config"]
