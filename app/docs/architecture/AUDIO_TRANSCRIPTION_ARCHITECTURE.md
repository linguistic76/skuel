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
          (individual uploads)    (directory batch — audio → txt)
```

> Batch txt → md LLM enrichment (formerly "Tier 2", `BatchProcessingService`)
> was retired with ADR-054. Per-entry enrichment now lives in
> `UserEntryProcessingService`.

> **Journal uploads are zero-persistence (ADR-073).** The interactive
> `/journals/upload` path transcribes via `BatchTranscriptionService.transcribe_one`
> (single file) or `transcribe_batch` (multi-file/folder) and writes the result to
> the user's own `je_out/` folder — it does **not** create a `UserEntry` or route
> through `UserEntryProcessingService`. The entry-backed flow diagrammed below is the
> REST-API transcription path, not the journals UI.

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
2. **Per-call overrides** — a `TranscriptionProcessOptions` passed as `transcribe(audio_path, options=...)`
3. **Conditional inclusion** — intelligence/vocabulary options are only sent to the API when enabled (avoids unnecessary Deepgram credit charges)

Layer 2 covers exactly the five fields on `TranscriptionProcessOptions`
(`language`, `model`, `punctuate`, `paragraphs`, `diarize`), and covers them as
a set — the model has a default for each, so passing one field still sends all
five. Every other Deepgram knob is config-only. That is deliberate: the port is
provider-agnostic (ADR-063), so it cannot take a bag of `DeepgramConfig` field
names, which is what the previous `transcribe(**overrides)` did.

```python
# Uses config/deepgram.toml defaults
result = await adapter.transcribe(audio_path="recording.mp3")

# Override the five option fields for this call only
result = await adapter.transcribe(
    audio_path="recording.mp3",
    options=TranscriptionProcessOptions(model="nova-3", diarize=True),
)
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
DeepgramAdapter.transcribe(audio_path, options=opts)
       |
       v
TranscriptionResult stored in Neo4j
       |
       v
TranscriptionCompleted event published
       |
       v
UserEntryProcessingService processes transcribed text into UserEntry
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

### Path 2: Batch Transcription

```
Audio files placed in an input directory
       |
       v
BatchTranscriptionService.transcribe_batch()
       |  (concurrent with semaphore, skip existing)
       |  (uses DeepgramAdapter with config defaults — no per-call overrides)
       v
.txt files written to the output directory
```

**Access points:**
- **Admin console UI:** `/admin/batch-transcribe` — any server-side path, admin-only
- **User journals UI:** `/journals` → "Upload Folder" tab — fixed server-side to
  the personal vault's `je_in` → `je_out` (`JournalBatchService.je_in_dir/je_out_dir`,
  the canonical je_* staging-folder layout), authenticated users
- **CLI:** `uv run python scripts/batch_transcribe.py`
- **API (admin):** `POST /api/journals/batch-transcribe`
- **API (user):** `POST /api/journals/folder-transcribe`

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
| `core/services/transcription/batch_transcription_service.py` | Batch transcription: audio -> txt |
| `core/models/transcription/transcription.py` | Domain model + `TranscriptionProcessOptions` |
| `adapters/inbound/batch_transcription_api.py` | Batch API routes: `POST /api/journals/batch-transcribe` (admin) + `POST /api/journals/folder-transcribe` (user) |
| `adapters/inbound/journals_routes.py` | Journal upload UI (`/journals` file + folder modes, `/journals/browse`, DNWF stage fragments) |
| `adapters/inbound/admin_dashboard_ui.py` | Admin batch transcription page (`/admin/batch-transcribe`) |
| `scripts/batch_transcribe.py` | CLI for batch transcription |
| `docs/configuration/DEEPGRAM_CONFIG.md` | Configuration guide |

## See Also

- [Deepgram Configuration Guide](/docs/configuration/DEEPGRAM_CONFIG.md) — option reference
- [Journals Domain](/docs/domains/journals.md) — full journals architecture
- [Report Architecture](/docs/architecture/REPORT_ARCHITECTURE.md) — report generation pipeline
