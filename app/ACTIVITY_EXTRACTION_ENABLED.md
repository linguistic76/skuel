# Activity Extraction Feature Enabled

**Date:** 2026-02-09
**Status:** ✅ Complete (Multi-Modal Pipeline)

## What Was Implemented

The `ReportActivityExtractorService` (DSL integration) is now **fully wired and threshold-based**. This feature transforms passive journal entries into active task managers by automatically extracting Activity Lines when the journal's activity weight exceeds the threshold (default: 0.2).

**Key Update (Feb 9, 2026):** Extraction is now **conditional** based on multi-modal journal weights. Only journals with significant activity content (weight > 0.2) trigger entity creation.

## How It Works

### 1. User Submits Journal via `/journals/submit`

User uploads an audio file or text document containing natural language like:

```markdown
Had a productive day. Tomorrow I need to:

- [ ] Call the bank @context(task) @priority(1) @when(tomorrow)
- [ ] Morning meditation @context(habit) @duration(20m) @energy(spiritual)
- [ ] Start learning Python @context(goal) @deadline(2w)
```

### 2. Multi-Modal Processing Pipeline

```
Upload → Transcription (audio) → Raw Text → Mode Classification → je_output Generation
         OR Read Text (text)                                            ↓
                                                                Weight Analysis
                                                                         ↓
                                            IF activity weight > threshold (0.2):
                                                   Activity Extraction → Entities Created
```

**Step 1:** File is processed
- Audio: Deepgram transcription → raw transcript text
- Text: Direct file read → raw text content

**Step 2:** Mode classification (NEW - multi-modal)
- `JournalModeClassifier.infer_weights()` analyzes content
- Returns: `{activity: 0.7, articulation: 0.2, exploration: 0.1}`
- Determines primary mode (highest weight)

**Step 3:** je_output generation
- `JournalOutputGenerator.generate()` formats content
- Uses mode-specific formatter (activity/articulation/exploration)
- Saves to disk: `{STORAGE}/{YYYY-MM}/report_{uid}_output.md`

**Step 4:** Conditional activity extraction
- **IF** `weights.activity > threshold` (default: 0.2):
  - `ReportActivityExtractorService.extract_and_create()` is called
  - Parses `@context()` tags using DSL parser
  - Creates entities in all 13 SKUEL domains
- **ELSE:** Skip extraction (idea articulation / critical thinking journals)

### 3. Threshold-Based Extraction

**Three Journal Modes:**
- **Activity Tracking** (weight: activity) — Extract tasks, habits, goals via DSL
- **Idea Articulation** (weight: articulation) — Verbatim preservation, no extraction
- **Critical Thinking** (weight: exploration) — Question-organized, no extraction

**Extraction Logic:**
```python
if weights.activity > threshold:  # Default threshold: 0.2
    extract_and_create()  # Create entities
else:
    skip_extraction()     # Just format je_output
```

**Examples:**
- Journal with `{activity: 0.8, articulation: 0.1, exploration: 0.1}` → **Extracts entities** ✅
- Journal with `{activity: 0.1, articulation: 0.7, exploration: 0.2}` → **Skips extraction** ❌
- Journal with `{activity: 0.25, articulation: 0.45, exploration: 0.3}` → **Extracts entities** ✅

### 4. Entities Auto-Created (When Threshold Met)

From the example above, SKUEL automatically creates:
- **Task**: "Call the bank" (priority 1, due tomorrow)
- **Habit**: "Morning meditation" (20min, spiritual energy)
- **Goal**: "Start learning Python" (2 week deadline)

All entities are linked back to the source report via `EXTRACTED_FROM` relationships.

## Supported Entity Types (13 Domains + 1)

**Activity Domains (7):**
- `@context(task)` → Tasks
- `@context(habit)` → Habits
- `@context(goal)` → Goals
- `@context(event)` → Events
- `@context(principle)` → Principles
- `@context(choice)` → Choices
- `@context(finance)` → Finance entries

**Curriculum Domains (3):**
- `@context(ku)` → Knowledge Units
- `@context(ls)` → Learning Steps
- `@context(lp)` → Learning Paths

**Meta Domains (3):**
- `@context(report)` → Sub-reports (recursive)
- `@context(analytics)` → Analytics triggers
- `@context(calendar)` → Calendar items

**The Destination (+1):**
- `@context(lifepath)` → Life path alignment

## Implementation Details

### Files Changed (3)

1. **`core/utils/services_bootstrap.py`** (lines 1718-1747)
   - Created `ReportActivityExtractorService` with all 13 domain services
   - Wired into `ReportsProcessingService` constructor

2. **`core/services/reports/reports_processing_service.py`** (lines 292-310, 334-352)
   - Added extraction calls in `_process_audio()` after transcription
   - Added extraction calls in `_process_text()` after reading
   - Controlled by `extract_activities` flag in instructions

3. **`adapters/inbound/journals_ui.py`** (lines 657-665)
   - Set `extract_activities=True` in processing instructions
   - Enables automatic entity extraction for all journal uploads

### Bootstrap Wiring

```python
activity_extractor = ReportActivityExtractorService(
    # Activity Domains (6)
    tasks_service=activity_services["tasks"].core,
    habits_service=activity_services["habits"].core,
    goals_service=activity_services["goals"].core,
    events_service=activity_services["events"].core,
    principles_service=activity_services["principles"].core,
    choices_service=activity_services["choices"].core,
    # Finance (1)
    finance_service=core_services["finance"],
    # Curriculum (3)
    ku_service=learning_services["ku_service"],
    ls_service=learning_services["learning_steps"],
    lp_service=learning_services["learning_paths"],
    # Meta (3)
    report_service=report_service,
    # Destination (1)
    lifepath_service=lifepath_service,
)
```

### Processing Pipeline Integration

```python
# In _process_audio() and _process_text()
if instructions and instructions.get("extract_activities", False):
    if self.activity_extractor:
        await self._extract_activities(updated_report, report.user_uid, instructions)
```

### Journal Upload Default

```python
# journals_ui.py - upload_journal route
process_result = await processing_service.process_report(
    report.uid,
    instructions={
        "instructions": instructions_text,
        "extract_activities": True,  # ← ENABLED by default
    },
)
```

## Testing

All 15 DSL integration tests pass:
```bash
poetry run pytest tests/test_dsl_integration.py -v
# Result: 15 passed in 9.45s
```

Test coverage:
- Activity parsing (tasks, habits, goals, events)
- Entity creation via services
- Empty content handling
- Extraction preview
- Result metadata tracking

## Value Proposition

**Before:** Journals were passive records. Users had to manually:
1. Review their journal entries
2. Identify action items
3. Create tasks/habits/goals separately
4. Lose the connection between reflection and action

**After:** Journals are active task managers. Users:
1. Speak/write naturally with `@context()` tags
2. SKUEL automatically creates entities
3. Maintains `EXTRACTED_FROM` graph relationships
4. Transforms passive → active in one step

## Example Usage

### Voice Journal (Audio Upload)

User records voice memo:
> "Tomorrow morning I need to call the bank at 9am. That's important.
> I also want to start meditating daily for 20 minutes.
> And by next month, I should finish learning Python."

User adds DSL tags in the upload notes or the LLM can suggest them:
```markdown
- [ ] Call the bank @context(task) @priority(1) @when(tomorrow 9am)
- [ ] Morning meditation @context(habit) @duration(20m) @repeat(daily)
- [ ] Finish learning Python @context(goal) @deadline(next month)
```

**Result:** 1 Task, 1 Habit, 1 Goal automatically created and linked to the journal.

### Text Journal (Markdown Upload)

User uploads `daily-reflection.md`:
```markdown
# Daily Reflection - Feb 9, 2026

Made good progress today. For tomorrow:

- [ ] Review PR #123 @context(task) @priority(2) @when(morning)
- [ ] Read 30min before bed @context(habit) @energy(calm)
- [ ] Launch v2.0 by Friday @context(goal) @deadline(friday)
```

**Result:** 1 Task, 1 Habit, 1 Goal + report metadata tracking extraction stats.

## Metadata Tracking

Each report's `metadata.activity_extraction` stores:
```json
{
  "activities_found": 3,
  "tasks_found": 1,
  "habits_found": 1,
  "goals_found": 1,
  "tasks_created": 1,
  "habits_created": 1,
  "goals_created": 1,
  "created_task_uids": ["task_review-pr_abc123"],
  "created_habit_uids": ["habit_reading_xyz789"],
  "created_goal_uids": ["goal_launch-v2_def456"],
  "total_created": 3,
  "extraction_started_at": "2026-02-09T10:30:00Z",
  "extraction_completed_at": "2026-02-09T10:30:02Z"
}
```

## Next Steps (Optional Enhancements)

1. **LLM-Assisted Tagging:** Pre-process raw text with LLM to suggest `@context()` tags
2. **UI Preview:** Show extraction preview before finalizing upload
3. **Extraction Report:** Generate summary of created entities after processing
4. **Bulk Extraction:** Re-process existing journals to extract activities retroactively
5. **Custom Instructions:** Let users define extraction rules per ReportProject

## References

- **Multi-Modal Pipeline:** `MULTI_MODAL_JOURNALS_COMPLETE.md` (complete implementation guide)
- **Service:** `core/services/dsl/report_activity_extractor.py`
- **Mode Classifier:** `core/services/journals/journal_mode_classifier.py`
- **Output Generator:** `core/services/journals/journal_output_generator.py`
- **Tests:** `tests/test_dsl_integration.py`
- **DSL Spec:** `docs/dsl/DSL_SPECIFICATION.md`
- **Architecture:** `docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md` (DSL section)
- **Journals Domain:** `docs/domains/journals.md` (multi-modal architecture)
