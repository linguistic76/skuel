# SKUEL Activity Vault Template

This template provides the folder structure and example YAML files
for uploading Activity Domain data to SKUEL.

## Folder Structure

```
tasks/       — Work to be done
goals/       — Outcomes to achieve
habits/      — Behaviors to build
events/      — Time commitments to keep
choices/     — Decisions to make
principles/  — Values to embody
```

## How to Use

1. Author YAML files in the appropriate folders.
2. Each file must include a `type` field matching the folder (e.g., `type: Task`).
3. Upload files at `/upload` in the SKUEL app.

## Required Fields

| Type      | Required Fields      |
|-----------|---------------------|
| Task      | `title`             |
| Goal      | `title`             |
| Habit     | `title`             |
| Event     | `title`             |
| Choice    | `title`             |
| Principle | `name`, `statement` |

All other fields are optional. See the example files for common fields.

## File Naming

Name files descriptively: `task_read-chapter-3.yaml`, `habit_morning-journal.yaml`.
If no `uid` field is set in the YAML, one is generated from the filename.

## Tips

- Edit these files in Obsidian, VS Code, or any text editor.
- Upload as many files as you like in a single batch (max 50 per upload).
- Re-uploading a file with the same UID updates the existing entity.
- Use the `connections` field to link entities across domains.
