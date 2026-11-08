You are reviewing one of a user's tasks against candidate knowledge units (Kus) from a personal-development curriculum. The candidates were matched to the task by vector similarity; your job is to filter out superficial matches. For each candidate, decide whether doing the task GENUINELY APPLIES the concept — puts it into practice or works with it substantively — or merely brushes past it (shared vocabulary or topic, no real application).

Task:
Title: {task_title}
{task_excerpt}

Candidate knowledge units:

{candidates_block}

Be conservative: "engages": true claims that doing the task substantively applies the concept, not just topical overlap.

Respond with ONLY a JSON array, one object per candidate, no prose:
[{{"index": 1, "engages": true, "rationale": "one concise line"}}, ...]

Every rationale must be a single line. Every index from the list above must appear exactly once.
