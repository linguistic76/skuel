# Deepgram Configuration Guide

**Config file:** `config/deepgram.toml`
**Loader:** `core/config/deepgram_config.py`
**Adapter:** `adapters/external/deepgram/adapter.py`

## How It Works

All Deepgram transcription options are controlled via a single TOML file: `config/deepgram.toml`. The file is loaded once at app startup and applied to every transcription request. No UI is needed — edit the file and restart the app.

```
config/deepgram.toml  -->  DeepgramConfig (frozen dataclass)  -->  DeepgramAdapter  -->  PrerecordedOptions  -->  Deepgram API
```

If the config file is missing or has a parse error, the adapter falls back to sensible defaults (nova-2, English, smart formatting, 1.7s utterance splits).

## Quick Start

The default `config/deepgram.toml` shipped with SKUEL works out of the box. To customize:

1. Open `config/deepgram.toml`
2. Change the settings you want
3. Restart the app (`uv run python main.py`)

## Configuration Sections

### Model & Language

```toml
[model]
name = "nova-2"          # AI model (nova-2, nova-3, whisper-large, etc.)
language = "en"          # BCP-47 language code
detect_language = false  # Auto-detect language (overrides language setting)
```

**Available models:**

| Model | Best For | Languages |
|-------|----------|-----------|
| `nova-3` | Latest accuracy | 50+ |
| `nova-2` | Stable, reliable (SKUEL default) | 36+ |
| `nova-2-medical` | Medical terminology | English |
| `nova-2-meeting` | Meeting transcription | English |
| `whisper-large` | OpenAI Whisper (rate-limited) | 50+ |

**Common language codes:** `en`, `en-US`, `en-GB`, `es`, `fr`, `de`, `pt-BR`, `ja`, `ko`, `zh`, `multi` (multilingual)

### Formatting

```toml
[formatting]
smart_format = true       # Master switch: dates, times, currency, URLs
punctuate = true          # Punctuation and capitalization
paragraphs = true         # Split into paragraphs
numerals = false          # "twenty three" --> "23"
measurements = false      # "five kilograms" --> "5 kg"
filler_words = false      # Include "uh", "um"
profanity_filter = false  # Replace profanity with ***
dictation = false         # Spoken commands: "period", "new paragraph"
```

### Utterances (Paragraph Breaks)

```toml
[utterances]
enabled = true            # Split speech into utterances
split_threshold = 1.7     # Seconds of silence to trigger a paragraph break
```

The `split_threshold` controls how SKUEL formats your transcript output. Each silence gap >= this duration creates a new paragraph (`\n\n`) in the `.txt` file.

| Value | Effect |
|-------|--------|
| `0.8` | Deepgram default — many short paragraphs |
| `1.7` | SKUEL default — natural thought breaks |
| `3.0` | Fewer, larger paragraphs (topic-level breaks) |

### Speaker Detection

```toml
[speakers]
diarize = false           # Label speakers (Speaker 0, Speaker 1, etc.)
```

### Intelligence Features

```toml
[intelligence]
summarize = false         # Generate a short summary
topics = false            # Detect topics discussed
intents = false           # Recognize speaker intents
sentiment = false         # Sentiment per sentence (-1.0 to +1.0)
detect_entities = false   # Extract named entities (people, places, etc.)
```

**Important notes:**
- Intelligence features are **English-only**
- They require **50+ words** of transcript input
- They consume **additional Deepgram credits** (cost)
- Results are captured in `TranscriptionResult.raw_response` for downstream use
- Structured extraction into SKUEL domain models is planned for a future release

**Current status:** When you enable an intelligence feature, the raw Deepgram JSON response is stored in `raw_response`. The data is there and accessible, but SKUEL does not yet parse it into structured fields or display it in the UI. This is the "prepare the way" step.

### Vocabulary & Redaction

```toml
[vocabulary]
keywords = []             # Boost terms: ["SKUEL:5", "Neo4j:3"]
replace = []              # Find/replace: ["colour:color"]
redact = false            # Redact sensitive info: false, "pci", "pii", "numbers", true
```

**Keyword boosting** helps Deepgram recognize domain-specific terms. Weight range: -10 (suppress) to 10 (boost). Useful for:
- Brand names and product names
- Technical jargon
- Proper nouns Deepgram might mishear

**Redaction** masks sensitive info in the transcript output:
- `"pci"` — payment card numbers
- `"pii"` — personal info (names, emails, phone numbers)
- `"numbers"` — all numbers
- `true` — redact everything

### Request Settings

```toml
[request]
timeout = 120.0           # API timeout in seconds
alternatives = 1          # Number of transcript alternatives (1 = best only)
tags = []                 # Tags for Deepgram billing dashboard
```

Increase `timeout` for very long audio files (> 10 minutes).

## Per-Call Overrides

The config file sets defaults. Individual transcription calls can override the
five fields on `TranscriptionProcessOptions` — `language`, `model`,
`punctuate`, `paragraphs`, `diarize`:

```python
from core.models.transcription.transcription import TranscriptionProcessOptions

# Uses config/deepgram.toml defaults
result = await adapter.transcribe(audio_path="file.mp3")

# Override model for this one call
result = await adapter.transcribe(
    audio_path="file.mp3", options=TranscriptionProcessOptions(model="nova-3")
)

# Enable diarize for this call only
result = await adapter.transcribe(
    audio_path="file.mp3", options=TranscriptionProcessOptions(diarize=True)
)
```

`TranscriptionProcessOptions` is the same model the REST API's
`/api/transcriptions/{uid}/process` endpoint accepts. Overrides apply **field
by field**: the adapter dumps with `exclude_unset=True`, so the two calls above
change only `model` and only `diarize` respectively, and everything else on
this page still comes from `config/deepgram.toml`. (A plain dump would not —
every field on that model has a default, so it would reassert `nova-2`/`en`
over whatever the config says.) **Every setting on this page not among those
five is config-only:**
`TranscriptionPort` is provider-agnostic (ADR-063), so it deliberately does not
take `DeepgramConfig` field names per call. Change them in
`config/deepgram.toml`.

## Accessing Intelligence Data

When intelligence features are enabled, the raw response is in `TranscriptionResult.raw_response`:

```python
result = await adapter.transcribe("file.mp3")
raw = result.value.raw_response

# Topics (when intelligence.topics = true)
topics = raw["results"]["topics"]["segments"]

# Sentiment (when intelligence.sentiment = true)
sentiment = raw["results"]["sentiments"]["segments"]

# Summary (when intelligence.summarize = true)
summary = raw["results"]["summary"]["short"]
```

## File Layout

| File | Purpose |
|------|---------|
| `config/deepgram.toml` | Configuration (edit this) |
| `core/config/deepgram_config.py` | Config loader + `DeepgramConfig` dataclass |
| `adapters/external/deepgram/adapter.py` | API adapter (reads config) |
| `core/models/transcription/transcription.py` | `TranscriptionProcessOptions` (per-call overrides) |

## Future Roadmap

| Feature | Status | Notes |
|---------|--------|-------|
| Config file (`deepgram.toml`) | Done | All Deepgram options exposed |
| Utterance paragraph breaks | Done | `utt_split = 1.7` |
| Intelligence raw capture | Done | `raw_response` stores full API response |
| Structured intelligence extraction | Planned | Parse topics/sentiment/entities into typed fields |
| Intelligence display in UI | Planned | Show summaries, sentiment, topics in journal view |
| Per-journal config profiles | Planned | Different settings for different use cases |
| UI settings page | Planned | Edit config from the browser |
