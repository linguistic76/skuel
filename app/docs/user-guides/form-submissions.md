# Form Templates & Submissions — Admin/Builder Guide

## What Are Forms?

Forms are a **general-purpose content collection system** decoupled from the learning loop. Unlike Exercises (which are curriculum-bound and flow through the submission → report → revision cycle), Forms are standalone structured data collectors that can be embedded anywhere.

| Concept | What It Is |
|---------|-----------|
| **FormTemplate** | A reusable form definition created by admin. Contains `form_schema` (field specs) and optional `instructions`. Shared content — all users can see and fill it. |
| **FormSubmission** | A user's response to a FormTemplate. Stores structured `form_data` as JSON. User-owned — only the submitter and shared recipients can see it. |

### Forms vs Exercises

| Feature | Exercise | FormTemplate |
|---------|----------|-------------|
| Purpose | Practice curriculum concepts | Collect any structured data |
| Base class | `Curriculum` (21 extra fields) | `Entity` (lightweight) |
| Submission type | `ExerciseSubmission` (file upload) | `FormSubmission` (JSON) |
| Report cycle | Yes (ExerciseReport → RevisedExercise) | No |
| Embedding | Articles only | Articles (via EMBEDS_FORM) |
| Sharing | Via group assignment | At submit time (group, direct, admin) |

---

## Defining `form_schema`

A FormTemplate's `form_schema` is a list of field specifications. Each field is a dict with required and optional keys.

### Required Keys

| Key | Type | Description |
|-----|------|-------------|
| `name` | string | Field identifier (used as key in form_data) |
| `type` | string | One of: `text`, `textarea`, `number`, `select`, `checkbox`, `date`, `email`, `url` |
| `label` | string | Human-readable label shown to the user |

### Optional Keys

| Key | Type | Description |
|-----|------|-------------|
| `required` | boolean | Whether the field must be filled (default: false) |
| `placeholder` | string | Placeholder text |
| `options` | list[string] | **Required** for `select` type — dropdown options |
| `min` | number | Minimum value (for `number` type) |
| `max` | number | Maximum value (for `number` type) |

### Example Schema

```json
[
  {
    "name": "reflection",
    "type": "textarea",
    "label": "What did you learn this week?",
    "required": true,
    "placeholder": "Write freely..."
  },
  {
    "name": "confidence",
    "type": "select",
    "label": "How confident do you feel?",
    "options": ["Not at all", "Somewhat", "Confident", "Very confident"]
  },
  {
    "name": "hours_studied",
    "type": "number",
    "label": "Hours studied",
    "min": 0,
    "max": 168
  },
  {
    "name": "follow_up",
    "type": "checkbox",
    "label": "I'd like a follow-up discussion"
  }
]
```

---

## Embedding Forms in Articles

FormTemplates are linked to Articles via the `EMBEDS_FORM` relationship. When a user reads an Article, any embedded forms render inline after the article content.

### Linking via API

```
POST /api/form-templates/link-article
{
  "form_template_uid": "ft_weekly_reflection_abc123",
  "article_uid": "a_intro_to_python_xyz789"
}
```

### Unlinking

```
POST /api/form-templates/unlink-article
{
  "form_template_uid": "ft_weekly_reflection_abc123",
  "article_uid": "a_intro_to_python_xyz789"
}
```

An Article can embed multiple FormTemplates. A FormTemplate can be embedded in multiple Articles.

---

## Form Submission Flow

1. User reads an Article with an embedded FormTemplate
2. The form renders inline with all fields from `form_schema`
3. User fills out the form and optionally selects sharing targets
4. On submit:
   - `form_data` is validated against the template's `form_schema`
   - `template_schema_hash` (SHA-256 of schema + instructions) is pinned — so if the template changes later, the submission records exactly which schema the user responded to
   - `processed_content` is built canonically: schema-ordered fields, labels (not raw keys), bools normalized to "Yes"/"No", unknown keys excluded
   - Node + OWNS + RESPONDS_TO_FORM relationships are created atomically in a single Cypher query
5. Sharing happens automatically based on selected targets

### Quick-Share at Submit Time

When submitting, users can share their response immediately:

| Target | How |
|--------|-----|
| **Group** | Select a group — submission gets `SHARED_WITH_GROUP` relationship |
| **Specific users** | Provide user UIDs — `SHARES_WITH` relationships created |
| **Admin** | Check "send to admin" — shared with admin user |

### Post-Submit Sharing

After submission, users can share from the detail page:

```
POST /api/form-submissions/share
{
  "uid": "fs_my_response_abc123",
  "group_uid": "group_class_a_xyz",
  "recipient_uids": ["user_teacher_1"]
}
```

---

## Viewing Submissions

### My Form Submissions Page

`GET /my-forms` — Lists all of the user's form submissions with title, template reference, and submission date.

### Submission Detail

`GET /my-forms/detail?uid=fs_abc123` — Shows full form data as key-value pairs, with delete button.

### Deleting

Users can delete their own submissions from the detail page. The delete is ownership-verified — users can only delete their own submissions.

---

## API Reference

### FormTemplate (Admin-Only)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/form-templates/create` | Create a new FormTemplate |
| GET | `/api/form-templates/get?uid=` | Get a FormTemplate by UID |
| GET | `/api/form-templates/list` | List all FormTemplates |
| PUT | `/api/form-templates/update?uid=` | Update a FormTemplate |
| DELETE | `/api/form-templates/delete?uid=` | Delete a FormTemplate |
| POST | `/api/form-templates/link-article` | Link FormTemplate to Article |
| POST | `/api/form-templates/unlink-article` | Unlink FormTemplate from Article |

### FormSubmission (User)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/form-submissions/submit` | Submit a form response |
| GET | `/api/form-submissions` | List my submissions |
| GET | `/api/form-submissions/get?uid=` | Get a submission by UID |
| DELETE | `/api/form-submissions/delete?uid=` | Delete own submission |
| POST | `/api/form-submissions/share` | Share a submission |

### Create FormTemplate Request

```json
{
  "title": "Weekly Reflection",
  "description": "End-of-week learning reflection form",
  "instructions": "Take 5 minutes to reflect on your week.",
  "form_schema": [
    {"name": "reflection", "type": "textarea", "label": "What did you learn?", "required": true},
    {"name": "rating", "type": "select", "label": "How was the week?", "options": ["Great", "Good", "OK", "Tough"]}
  ],
  "tags": ["reflection", "weekly"]
}
```

### Submit FormSubmission Request

```json
{
  "form_template_uid": "ft_weekly_reflection_abc123",
  "form_data": {
    "reflection": "I learned about async/await patterns...",
    "rating": "Great"
  },
  "title": "Week 3 Reflection",
  "group_uid": "group_class_a_xyz",
  "share_with_admin": true
}
```

---

## Graph Relationships

```
(Article)-[:EMBEDS_FORM]->(FormTemplate)     # Article embeds a form
(FormSubmission)-[:RESPONDS_TO_FORM]->(FormTemplate)  # Submission links to template
(User)-[:OWNS]->(FormSubmission)             # User owns their submission
(FormSubmission)-[:SHARED_WITH_GROUP]->(Group)  # Shared with a group
(User)-[:SHARES_WITH]->(FormSubmission)      # Shared with specific user
```

## Data Integrity

### Schema Pinning

Every `FormSubmission` stores a `template_schema_hash` — the SHA-256 hash of the template's `form_schema` + `instructions` at the time of submission. If an admin later modifies the template, old submissions retain the hash of the schema the user actually saw. Use `FormTemplate.schema_fingerprint()` to compute the current hash and compare.

### Canonical Processed Content

`processed_content` (used for search and embedding) is generated by `build_form_processed_content()` in `core/services/forms/form_content.py`. It follows schema field order (not dict insertion order), uses field labels instead of raw key names, normalizes booleans to "Yes"/"No", ignores unknown keys, and truncates at 10,000 characters.

### Atomic Writes

`FormSubmissionBackend.create_with_relationships()` creates the submission node, OWNS relationship, and RESPONDS_TO_FORM relationship in a single Cypher query. This prevents orphaned nodes if part of the operation fails.

---

## EntityType Traits

| Trait | FormTemplate | FormSubmission |
|-------|-------------|----------------|
| `requires_user_uid()` | `False` (shared) | `True` (user-owned) |
| `content_origin()` | `CURATED` | `USER_CREATED` |
| `is_activity()` | `False` | `False` |
| `is_derived()` | `False` | `True` |
| `is_processable()` | `False` | `False` |
| Default status | `DRAFT` | `COMPLETED` |
| Default visibility | `PUBLIC` | `PRIVATE` |
