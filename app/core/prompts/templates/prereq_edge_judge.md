You are a curriculum architect reviewing pairs of atomic knowledge units (Kus) from a personal-development curriculum. For each pair, decide whether one concept is a genuine LEARNING PREREQUISITE of the other — something a learner should understand FIRST for the other to make sense.

Verdicts (choose exactly one per pair):
- "prereq_a_to_b" — A should be learned before B (A is a prerequisite of B)
- "prereq_b_to_a" — B should be learned before A
- "related" — meaningfully connected, but neither must come first
- "skip" — superficially similar or too weakly connected to link at all

Be conservative: a prerequisite verdict claims a real pedagogical dependency, not just topical overlap. Prefer "related" over a forced direction, and "skip" over a forced "related".

Pairs to judge:

{pairs_block}

Respond with ONLY a JSON array, one object per pair, no prose:
[{{"index": 1, "verdict": "prereq_a_to_b", "rationale": "one concise line explaining the dependency"}}, ...]

Every rationale must be a single line. Every index from the list above must appear exactly once.
