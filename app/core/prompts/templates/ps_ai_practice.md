Suggest {num_activities} practice activities for this path step.

Return ONLY valid JSON in this exact shape:
{{
  "activities": [
    {{
      "name": "activity name",
      "type": "hands-on | reflective | applied | creative",
      "description": "what the learner should do"
    }}
  ]
}}

Each activity must be specific, actionable, and varied in type.
