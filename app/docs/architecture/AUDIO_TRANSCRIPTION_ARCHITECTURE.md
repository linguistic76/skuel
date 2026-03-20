---
title: Audio Transcription Architecture
created: 2026-03-20
status: current
category: architecture
tags: [deepgram, transcription, audio, batch, configuration]
---

# Audio Transcription Architecture

SKUEL's audio transcription converts spoken audio into formatted text via Deepgram's API. The system serves two paths: individual journal uploads (interactive) and batch directory processing (admin CLI/UI). Both paths share a single DeepgramAdapter configured from one TOML file.

## System Overview

```
                          config/deepgram.toml
                                 |
                                 v
                      DeepgramConfig (frozen dataclass)
                                 |
                                 v
                          DeepgramAdapter
                         /              \
                        v                v
          TranscriptionService    BatchTranscriptionService
          (individual uploads)    (directory batch — Tier 1)
                                         |
                                         v
                                 BatchProcessingService
                                 (LLM enrichment — Tier 2)
```

## Configuration Layer

All Deepgram API options are controlled via `config/deepgram.toml` — a single file that is loaded once at app startup and applied to every transcription request.

**See:** [Deepgram Configuration Guide](/docs/configuration/DEEPGRAM_CONFIG.md) for the full reference.

### Config Flow

```
config/deepgram.toml
       |  (parsed by tomllib at startup)
       v
DeepgramConfig  ──────────────────────────────  core/config/deepgram_config.py
       |  (injected at bootstrap)
       v
DeepgramAdapter._build_options()  ───────────  adapters/external/deepgram/adapter.py
       |  (merges config defaults + per-call overrides)
       v
PrerecordedOptions  ─────────────────────────  deepgram SDK
       |
       v
Deepgram API
```

### Why TOML, Not .env

`.env` is for secrets and environment-specific values (API keys, database URLs). Deepgram transcription options are operational settings that:
- Have structured nesting (model, formatting, intelligence, vocabulary)
- Need comments explaining each option
- Are the same across environments
- Should be version-controlled

TOML handles all of this cleanly. The API key stays in `.env` where it belongs.

### Fallback Behavior

If `config/deepgram.toml` is missing or has a parse error, the adapter falls back to hardcoded defaults: nova-2, English, smart formatting, 1.7s utterance splits, no intelligence features. The app will not crash.

## DeepgramAdapter

**Location:** `adapters/external/deepgram/adapter.py`

Thin adapter — no business logic, no persistence. One method: `transcribe()`.

### Option Resolution

Options are resolved in three layers (later layers override earlier):

1. **Config defaults** — `DeepgramConfig` loaded from `config/deepgram.toml`
2. **Per-call overrides** — keyword arguments to `transcribe(**overrides)`
3. **Conditional inclusion** — intelligence/vocabulary options are only sent to the API when enabled (avoids unnecessary Deepgram credit charges)

```python
# Uses config/deepgram.toml defaults
result = await adapter.transcribe(audio_path="recording.mp3")

# Override for this call only
result = await adapter.transcribe(audio_path="recording.mp3", model="nova-3", diarize=True)
```

### Utterance-Based Paragraph Breaks

Deepgram's utterance feature segments speech by silence gaps. SKUEL uses this to create paragraph breaks in transcript output:

```
Audio:  "I went to the store... [1.7s silence] ...then I came home"
                                      |
                              utt_split threshold
                                      |
                                      v
Output: "I went to the store.\n\nThen I came home."
```

The `_extract_transcript()` method joins utterances with `\n\n`. If utterances are unavailable (e.g., disabled in config), it falls back to the flat channel transcript.

### TranscriptionResult

```python
@dataclass
class TranscriptionResult:
    transcript_text: str                    # Formatted text (utterance paragraphs)
    confidence_score: float                 # 0.0-1.0
    duration_seconds: float                 # Audio duration
    word_count: int                         # Word count
    raw_response: dict[str, Any] | None     # Full Deepgram JSON (intelligence data lives here)
```

When intelligence features are enabled (topics, sentiment, etc.), the raw API response is preserved in `raw_response` for future structured extraction.

## Two Consumer Paths

### Path 1: Individual Transcription (Interactive)

```
User uploads audio file
       |
       v
TranscriptionService.process(uid, options)
       |  (options override config defaults)
       v
DeepgramAdapter.transcribe(audio_path, **overrides)
       |
       v
TranscriptionResult stored in Neo4j
       |
       v
TranscriptionCompleted event published
       |
       v
JournalsCoreService creates journal report (via SubmissionsCoreService delegation)
```

**TranscriptionProcessOptions** (Pydantic model) provides per-call overrides via the REST API:

```python
class TranscriptionProcessOptions(BaseModel):
    language: str = "en"
    model: str = "nova-2"
    punctuate: bool = True
    paragraphs: bool = True
    diarize: bool = False
```

### Path 2: Batch Transcription (Admin)

```
Admin places audio files in data/je_inputs/
       |
       v
BatchTranscriptionService.transcribe_batch()  ── Tier 1
       |  (concurrent with semaphore, skip existing)
       |  (uses DeepgramAdapter with config defaults — no per-call overrides)
       v
.txt files written to data/je_outputs/
       |
       v
BatchProcessingService.process_batch()  ── Tier 2
       |  (LLM enrichment: activity_tracking / articulation / exploration)
       v
.md files written to data/je_outputs/
```

**Access points:**
- **UI:** `/journals/batch` (admin-only page with preview/transcribe/process buttons)
- **CLI:** `uv run python scripts/batch_transcribe.py`
- **API:** `POST /api/journals/batch-transcribe`, `POST /api/journals/batch-process`

## Intelligence Features (Prepared, Not Yet Extracted)

The config file exposes five Deepgram intelligence features:

| Feature | Config Key | API Response Path |
|---------|-----------|-------------------|
| Summarize | `intelligence.summarize` | `results.summary.short` |
| Topics | `intelligence.topics` | `results.topics.segments[]` |
| Intents | `intelligence.intents` | `results.intents.segments[]` |
| Sentiment | `intelligence.sentiment` | `results.sentiments.segments[]` |
| Entity Detection | `intelligence.detect_entities` | `results.entities.segments[]` |

**Current state:** When enabled in `deepgram.toml`, the raw JSON is captured in `TranscriptionResult.raw_response`. SKUEL does not yet parse this data into typed domain models or display it in the UI.

**Constraints:**
- English-only
- Require 50+ words of transcript input
- Consume additional Deepgram API credits

**Future work:** Structured extraction into typed fields, display in journal detail views, feeding intelligence data into UserContext for the learning loop.

## File Map

| File | Role |
|------|------|
| `config/deepgram.toml` | All Deepgram options (edit this) |
| `core/config/deepgram_config.py` | TOML loader + `DeepgramConfig` frozen dataclass |
| `adapters/external/deepgram/adapter.py` | API adapter — `transcribe()` + `_build_options()` |
| `core/services/transcription/transcription_service.py` | Individual transcription lifecycle |
| `core/services/transcription/batch_transcription_service.py` | Batch Tier 1: audio -> txt |
| `core/services/transcription/batch_processing_service.py` | Batch Tier 2: txt -> md via LLM |
| `core/models/transcription/transcription.py` | Domain model + `TranscriptionProcessOptions` |
| `adapters/inbound/batch_transcription_api.py` | Batch API routes (admin-only) |
| `adapters/inbound/journals_ui.py` | Batch UI page + journal upload UI |
| `scripts/batch_transcribe.py` | CLI for batch operations |
| `docs/configuration/DEEPGRAM_CONFIG.md` | Configuration guide |

## See Also

- [Deepgram Configuration Guide](/docs/configuration/DEEPGRAM_CONFIG.md) — option reference
- [Journals Domain](/docs/domains/journals.md) — full journals architecture
- [Report Architecture](/docs/architecture/REPORT_ARCHITECTURE.md) — report generation pipeline
