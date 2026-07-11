You are reviewing one of a user's personal knowledge notes against candidate knowledge units (Kus) from a personal-development curriculum. The candidates were matched to the note by vector similarity; your job is to filter out superficial matches. For each candidate, decide whether the note GENUINELY ENGAGES the concept — applies it, reflects on it, or works with it substantively — or merely brushes past it (shared vocabulary or topic, no real engagement).

Note (excerpt):
Title: {entry_title}
{entry_excerpt}

Candidate knowledge units:

{candidates_block}

Be conservative: "engages": true claims the note substantively works with the concept, not just topical overlap.

Respond with ONLY a JSON array, one object per candidate, no prose:
[{{"index": 1, "engages": true, "rationale": "one concise line"}}, ...]

Every rationale must be a single line. Every index from the list above must appear exactly once.
