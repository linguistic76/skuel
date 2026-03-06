# Roadmap: ev__ / msr__ Daily Notes

**Status:** Not started
**Priority:** After edge ingestion is implemented
**Depends on:** Edge ingestion support

## Summary

Introduce two new entity/record types for timestamped tracking:
- **ev__** (Event instance) - A timestamped occurrence of an activity
- **msr__** (Measurement) - A numeric or categorical observation at a point in time

Together with Daily Notes, these enable quantified self-tracking integrated into the curriculum graph.

## Concepts

### Event Instance (ev__)

An `ev__` is a timestamped occurrence -- a "run" of a Learning Step or Exercise.

```yaml
uid: ev:ls_track_coffee_buzzing:2026_03_06
type: EventInstance
run_of: ls:track-coffee-buzzing     # RUN_OF -> Ls
timestamp: "2026-03-06T10:30:00+07:00"
duration_minutes: 5
notes: "Tracked coffee intake and buzzing levels for the morning."
```

**Graph pattern:** `(ev:EventInstance)-[:RUN_OF]->(ls:Ls)`

### Measurement (msr__)

An `msr__` is a numeric or categorical observation at a specific time.

```yaml
uid: msr:buzzing:2026_03_06_1030
type: Measurement
ku_uid: ku:attention:buzzing          # MEASURES -> Ku
value: 7                              # numeric value (0-10 scale)
unit: subjective_rating
timestamp: "2026-03-06T10:30:00+07:00"
context: "30 minutes after second coffee"
```

**Graph pattern:** `(msr:Measurement)-[:MEASURES]->(ku:Ku)`

### Daily Note

A Daily Note is a user-facing document that generates structured data:

```
Daily Note (2026-03-06)
  generates:
    1 Ev run (of ls:track-coffee-buzzing)
    3 Msr entries:
      - msr:buzzing:2026_03_06_1030 (buzzing=7)
      - msr:coffee:2026_03_06_0800 (coffee=1 cup)
      - msr:coffee:2026_03_06_1000 (coffee=1 cup)
```

## UID Formats

```
ev:{ls_slug}:{date}              # ev:ls_track_coffee_buzzing:2026_03_06
msr:{ku_slug}:{date}_{time}      # msr:buzzing:2026_03_06_1030
```

## Query Examples

### "Show me buzzing scores on days with coffee after 2pm"

```cypher
MATCH (msr_b:Measurement)-[:MEASURES]->(ku:Ku {uid: 'ku:attention:buzzing'})
WHERE msr_b.timestamp >= date('2026-02-01')
WITH msr_b, date(msr_b.timestamp) AS day

// Find coffee measurements after 2pm on same days
OPTIONAL MATCH (msr_c:Measurement)-[:MEASURES]->(coffee:Ku {uid: 'ku:nutrition:caffeine'})
WHERE date(msr_c.timestamp) = day
  AND time(msr_c.timestamp) > time('14:00')

RETURN day,
       msr_b.value AS buzzing_score,
       count(msr_c) AS afternoon_coffees
ORDER BY day
```

### "What's my average buzzing on coffee vs no-coffee days?"

```cypher
MATCH (msr:Measurement)-[:MEASURES]->(ku:Ku {uid: 'ku:attention:buzzing'})
WITH date(msr.timestamp) AS day, avg(msr.value) AS avg_buzzing

OPTIONAL MATCH (coffee:Measurement)-[:MEASURES]->(c:Ku {uid: 'ku:nutrition:caffeine'})
WHERE date(coffee.timestamp) = day

WITH day, avg_buzzing, count(coffee) > 0 AS had_coffee
RETURN had_coffee, avg(avg_buzzing) AS mean_buzzing, count(day) AS days
```

## Implementation Steps

1. Add `EntityType.EVENT_INSTANCE` and `EntityType.MEASUREMENT` (or separate model)
2. Create frozen dataclasses: `EventInstance`, `Measurement`
3. Add Neo4j labels: `:EventInstance`, `:Measurement`
4. Create backends and services
5. Add ingestion support for `type: EventInstance` and `type: Measurement`
6. Build Daily Note parser (markdown -> ev__ + msr__ records)
7. Add visualization routes (time series charts)

## Relationship to Existing Entities

- `EventInstance` is NOT the same as `Event` (activity domain). Events are schedulable templates; EventInstances are timestamped occurrences.
- `Measurement` connects to Kus via `MEASURES` -- the Ku defines what is being measured.
- Edge evidence (`confidence`, `polarity`) is distinct from Measurements (`value`, `unit`). Edges are about relationships; Measurements are about individual observations.

## Timeline

After edge ingestion is implemented and working. ev__/msr__ depends on the edge infrastructure for evidence-property patterns on Neo4j relationships.
