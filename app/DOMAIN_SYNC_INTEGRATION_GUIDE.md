# Domain Sync Integration Guide

**Purpose:** Add admin-only sync triggers to domain list pages

**Components:**
- `DomainSyncTrigger` - Button to open sync modal
- `DomainSyncModal` - Configuration modal with form
- API Endpoint: `POST /api/ingest/domain/{domain_name}`

---

## Step 1: Import Components

At the top of your domain routes file:

```python
from ui.patterns.domain_sync_trigger import DomainSyncTrigger, DomainSyncModal
from core.auth import has_admin_role  # Or equivalent admin check
```

---

## Step 2: Integrate into Domain List Page

### Example: Knowledge Units (/ku)

**Before:**
```python
@rt("/ku")
async def ku_list_page(request: Request):
    kus = await ku_service.list_all()

    return BasePage(
        content=Div(
            H1("Knowledge Units"),
            KuListTable(kus),
        ),
        title="Knowledge Units",
        request=request,
    )
```

**After:**
```python
@rt("/ku")
async def ku_list_page(request: Request):
    # Check if user is admin
    is_admin = has_admin_role(request)  # Use your actual admin check

    kus = await ku_service.list_all()

    return BasePage(
        content=Div(
            # Header with sync button
            Div(
                H1("Knowledge Units"),
                DomainSyncTrigger("ku", is_admin),  # Admin-only button
                cls="flex justify-between items-center mb-4"
            ),

            # Main content
            KuListTable(kus),

            # Sync modal (hidden by default)
            DomainSyncModal(
                domain_name="ku",
                default_path="/home/mike/0bsidian/skuel/docs/ku"  # Optional
            ),
        ),
        title="Knowledge Units",
        request=request,
    )
```

---

## Step 3: Verify Admin Check Function

Ensure you have an admin check function available:

```python
def has_admin_role(request: Request) -> bool:
    """
    Check if current user has admin role.

    Returns:
        True if user is admin, False otherwise
    """
    try:
        from core.auth import get_current_user_from_request
        user = get_current_user_from_request(request)
        return user and user.role == "ADMIN"  # Adjust to your UserRole enum
    except Exception:
        return False
```

---

## Complete Example: Tasks Domain

```python
from fasthtml.common import *
from starlette.requests import Request

from core.auth import has_admin_role
from ui.layouts.base_page import BasePage
from ui.patterns.domain_sync_trigger import DomainSyncTrigger, DomainSyncModal


@rt("/tasks")
async def tasks_list_page(request: Request):
    """Tasks list page with admin-only sync trigger."""

    # Check admin status
    is_admin = has_admin_role(request)

    # Fetch tasks
    tasks = await tasks_service.list_all()

    return BasePage(
        content=Div(
            # Header with sync trigger
            Div(
                H1("Tasks", cls="text-2xl font-bold"),
                DomainSyncTrigger("tasks", is_admin),
                cls="flex justify-between items-center mb-6"
            ),

            # Tasks table
            TasksTable(tasks),

            # Sync modal (only shown when button clicked)
            DomainSyncModal(
                domain_name="tasks",
                default_path="/home/mike/0bsidian/skuel/docs/tasks"
            ),

            cls="max-w-7xl mx-auto p-6"
        ),
        title="Tasks",
        request=request,
    )
```

---

## Domains to Update (9 Total)

| Domain | Route File | Default Path |
|--------|-----------|--------------|
| **Curriculum (3)** |
| KU | `learning_routes.py` | `/home/mike/0bsidian/skuel/docs/ku` |
| LS | `learning_routes.py` | `/home/mike/0bsidian/skuel/docs/ls` |
| LP | `learning_routes.py` | `/home/mike/0bsidian/skuel/docs/lp` |
| **Activity (6)** |
| Tasks | `activity_routes.py` or `tasks_routes.py` | `/home/mike/0bsidian/skuel/docs/tasks` |
| Goals | `activity_routes.py` or `goals_routes.py` | `/home/mike/0bsidian/skuel/docs/goals` |
| Habits | `activity_routes.py` or `habits_routes.py` | `/home/mike/0bsidian/skuel/docs/habits` |
| Events | `activity_routes.py` or `events_routes.py` | `/home/mike/0bsidian/skuel/docs/events` |
| Choices | `activity_routes.py` or `choices_routes.py` | `/home/mike/0bsidian/skuel/docs/choices` |
| Principles | `activity_routes.py` or `principles_routes.py` | `/home/mike/0bsidian/skuel/docs/principles` |

---

## User Experience Flow

### 1. Admin User Views Domain Page
- Sees sync button in header: "🔄 Sync {DOMAIN}"
- Non-admin users: button is hidden

### 2. Admin Clicks Sync Button
- Modal opens with form:
  - **Source Directory:** Pre-filled with default path (editable)
  - **File Pattern:** `*.md` (editable)
  - **Preview only:** Checkbox for dry-run mode

### 3. Admin Configures and Submits
- **Without dry-run:**
  - HTMX POST to `/api/ingest/domain/{domain_name}`
  - Results displayed in `#sync-results-{domain_name}` div
  - Shows formatted stats: files synced, nodes created, errors

- **With dry-run:**
  - Same endpoint with `dry_run=true`
  - Shows preview: files to create/update/skip
  - "Execute Sync" button to run actual sync

### 4. Results Display
- Success: Green stat cards with summary
- Errors: Red error table with suggestions
- Modal remains open for review
- Admin can close or run again

---

## API Endpoint Details

### Endpoint
```
POST /api/ingest/domain/{domain_name}
```

### Form Parameters
- `source_path` (required): Directory path to sync
- `pattern` (optional): File glob pattern (default: `*.md`)
- `dry_run` (optional): "true" for preview mode

### Supported Domains
- `ku`, `ls`, `lp` (curriculum)
- `tasks`, `goals`, `habits`, `events`, `choices`, `principles` (activity)

### Returns
- **Dry-run mode:** HTML with `DryRunPreviewComponent`
- **Normal mode:** HTML with `SyncResultsSummary`
- **Error:** Result.fail() with error details

---

## Security Notes

1. **Admin-Only Access**
   - `@require_admin` decorator on API endpoint
   - Button hidden for non-admin users via `is_admin` check
   - Modal still exists in DOM but cannot be opened without button

2. **Path Validation**
   - Uses `_validate_ingestion_path()` to prevent traversal attacks
   - Checks against `SKUEL_INGESTION_ALLOWED_PATHS` env var if set

3. **No Client-Side Filtering**
   - Backend enforces all security (never trust client)
   - Admin role checked on every request

---

## Testing Checklist

### Admin User Tests
- ✅ Sync button visible on domain pages
- ✅ Modal opens when button clicked
- ✅ Form fields pre-filled with defaults
- ✅ Dry-run shows preview without writing to DB
- ✅ Normal sync creates/updates entities
- ✅ Results display correctly (stats, errors, breakdowns)
- ✅ Modal can be closed and reopened

### Non-Admin User Tests
- ✅ Sync button hidden
- ✅ Direct API call returns 403 Forbidden
- ✅ Page functions normally without sync features

### Error Handling Tests
- ✅ Invalid directory path: Clear error message
- ✅ Empty directory: "No files found" message
- ✅ Parse errors: Error table with suggestions
- ✅ Network errors: Appropriate error display

---

## Troubleshooting

### Button Not Visible (Admin User)
1. Verify `is_admin` function returns True
2. Check that `DomainSyncTrigger` is called with `is_admin=True`
3. Inspect HTML: button should exist with `btn` classes

### Modal Not Opening
1. Verify modal ID matches trigger: `sync-modal-{domain_name}`
2. Check browser console for JavaScript errors
3. Ensure DaisyUI modal classes are correct

### Sync Fails with 403
1. Verify `@require_admin` decorator on API endpoint
2. Check user authentication status
3. Verify user role is "ADMIN"

### Results Not Displaying
1. Check HTMX `hx-target` matches results div ID
2. Verify `boundary_handler` is returning HTML (not JSON)
3. Check browser network tab for response content

---

## Future Enhancements

### Phase 1 (Implemented)
- ✅ Dry-run preview
- ✅ Formatted results display
- ✅ Admin-only security

### Phase 2 (Future)
- ⏳ Real-time progress via WebSocket
- ⏳ Entity type filtering (sync only specific entities)
- ⏳ Sync history view (past operations)
- ⏳ Scheduled syncs (cron-like)
- ⏳ Sync profiles (saved configurations)

---

**End of Guide**
