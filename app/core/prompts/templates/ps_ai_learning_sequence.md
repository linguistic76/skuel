Suggest a learning sequence for this path step (up to {max_suggestions} items each).

Return ONLY valid JSON in this exact shape:
{{
  "prerequisites": [
    {{"title": "prerequisite step title", "reason": "why this should come first"}}
  ],
  "next_steps": [
    {{"title": "next step title", "reason": "why this builds on the current step"}}
  ]
}}

Prerequisites: foundational knowledge needed before this step.
Next steps: natural progressions after mastering this step.
