# SKUEL Troubleshooting Guide

**Last Updated**: 2026-01-31

This document covers common issues encountered during development and deployment of SKUEL.

---

## Table of Contents

1. [Server Startup Issues](#server-startup-issues)
2. [Route Registration Issues](#route-registration-issues)
3. [Import Errors](#import-errors)
4. [Service Dependency Issues](#service-dependency-issues)
5. [Type Annotation Issues](#type-annotation-issues)

---

## Server Startup Issues

### Port Already in Use

**Symptom**: `ERROR: [Errno 98] error while attempting to bind on address ('0.0.0.0', 8000): address already in use`

**Cause**: Another SKUEL server instance is already running on port 8000

**Solution**:
```bash
# Kill all processes using port 8000
lsof -ti:8000 | xargs kill -9 2>/dev/null || true

# Or kill by process name
pkill -9 -f "uvicorn" 2>/dev/null || true
pkill -9 -f "python main.py" 2>/dev/null || true

# Wait and restart
sleep 2
./dev serve
```

**Prevention**: Always kill existing servers before starting a new one during development.

---

### Embeddings Service Required Error

**Symptom**: `ValueError: Embeddings service is required - vector search is not optional`

**Cause**: `EntityRetrieval` service initialized without embeddings service when code expected it to be required

**Solution**: Embeddings service is now optional (fixed 2026-01-31). Server will gracefully degrade to keyword search.

**Verification**:
```bash
# Check logs for graceful degradation message
grep "keyword search fallback" /tmp/server.log

# Expected output:
# ✅ EntityRetrieval initialized with keyword search fallback (no embeddings)
```

**Related**: See `/EMBEDDINGS_SERVICE_FIX_COMPLETE.md`

---

## Route Registration Issues

### 404 on Valid Routes

**Symptom**: HTTP 404 on routes that should exist (e.g., `/tasks`, `/habits`, `/goals`)

**Diagnostic Steps**:
```bash
# 1. Check if server started successfully
grep "Application startup complete" /tmp/server.log

# 2. Check if routes were registered
grep -E "Tasks routes|Goals routes|Habits routes" /tmp/server.log

# 3. Test the endpoint
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:8000/tasks
# Expected: 401 (auth required) or 200 (success)
# Bad: 404 (route doesn't exist)
```

**Common Causes**:

1. **UI routes not registered** (only API routes)
   - **Example**: Tasks routes (fixed 2026-01-31)
   - **Solution**: Ensure both `create_*_api_routes()` and `create_*_ui_routes()` are called in bootstrap

2. **DomainRouteConfig not called**
   - **Symptom**: Routes defined in code but never registered
   - **Solution**: Check `bootstrap.py` calls `register_domain_routes()` or direct factory functions

3. **Missing route imports**
   - **Symptom**: ImportError in bootstrap
   - **Solution**: Add missing import in `_wire_all_routes()` function

**Fix Template** (from Tasks routes fix):
```python
# In /scripts/dev/bootstrap.py

if services.tasks:
    from adapters.inbound.tasks_api import create_tasks_api_routes
    from adapters.inbound.tasks_ui import create_tasks_ui_routes  # ✅ Must import UI routes

    # Register API routes
    create_tasks_api_routes(
        app, rt, services.tasks,
        user_service=services.user_service,
        # ... other services
    )

    # ✅ Register UI routes
    create_tasks_ui_routes(
        app, rt, services.tasks,
        services=services,
    )
```

---

### 401 vs 404 - Understanding the Difference

**401 Unauthorized**: Route exists, but requires authentication
- **Meaning**: ✅ Route registered successfully, user needs to log in
- **Action**: Navigate to `/` and sign in

**404 Not Found**: Route doesn't exist
- **Meaning**: ❌ Route was never registered in bootstrap
- **Action**: Check route registration in `bootstrap.py`

**Quick Test**:
```bash
# Test without auth
curl -s -w "HTTP %{http_code}\n" http://localhost:8000/tasks

# 401 = Good (route exists, need auth)
# 404 = Bad (route not registered)
```

---

## Import Errors

### FastHTML Components Import

**Symptom**: `ImportError: cannot import name 'X' from 'ui.daisy_components'` or `ModuleNotFoundError: No module named 'ui.daisy_components'`

**Cause**: `ui/daisy_components.py` was decomposed into 8 focused modules (March 2026). Standard HTML/FastHTML primitives (`H1`, `Div`, `Span`, etc.) were never part of SKUEL's wrappers.

**Solution**:
```python
# ❌ WRONG — module no longer exists
from ui.daisy_components import Button, ButtonT, Card, Progress

# ✅ CORRECT — import from focused modules
from ui.buttons import Button, ButtonT
from ui.cards import Card, CardBody
from ui.feedback import Progress, ProgressT
from ui.forms import FormControl, Input, Label, Select, Textarea
from ui.layout import Container, DivHStacked, Size
from ui.modals import Modal, ModalBox, ModalAction, ModalBackdrop
from ui.navigation import Dropdown, Menu, Navbar, Tabs
from ui.data import Divider, Stats, Table, Tooltip

# Standard HTML/FastHTML elements always come from fasthtml.common
from fasthtml.common import Div, H1, H2, H3, Option, P, Span
```

**Rule**: SKUEL DaisyUI wrappers live in `ui/{module}.py`. Standard HTML/FastHTML components come from `fasthtml.common`. See: `/docs/ui/COMPONENT_CATALOG.md` for the full module map.

---

### Missing Type Imports

**Symptom**: `NameError: name 'Any' is not defined`

**Cause**: Used `Any` in type hint without importing from `typing`

**Solution**:
```python
# ❌ WRONG
def my_function(param: Any):  # Any not imported
    pass

# ✅ CORRECT
from typing import Any

def my_function(param: Any):
    pass
```

**Common Missing Imports**:
- `Any`, `Optional`, `Union`, `List`, `Dict` → `from typing import ...`
- `Protocol` → `from typing import Protocol`
- `Callable` → `from typing import Callable`

---

## Service Dependency Issues

### Service Not Available in Bootstrap

**Symptom**: `AttributeError: 'ServiceContainer' object has no attribute 'tasks'`

**Cause**: Service not initialized in `services_bootstrap.py` or initialization failed

**Diagnostic**:
```bash
# Check service composition logs
grep "Service composition" /tmp/server.log
grep "✅.*service created" /tmp/server.log

# Look for specific service
grep -i "tasks.*service" /tmp/server.log
```

**Solution**:
1. Verify service is created in `services_bootstrap.py`
2. Check for errors during service initialization
3. Ensure all dependencies of the service are available

---

### Circular Dependencies

**Symptom**: ImportError or AttributeError during service composition

**SKUEL Pattern**: Services are composed in dependency order in `services_bootstrap.py`

**Solution**:
1. Check dependency graph - services must be created before their dependents
2. Use protocol interfaces instead of concrete types to break cycles
3. Inject dependencies via constructor, not imports

---

## Type Annotation Issues

### Forward Reference Union Types

**Symptom**: `TypeError: unsupported operand type(s) for |: 'str' and 'NoneType'`

**Cause**: Using `|` operator with string forward references (Python 3.10+ syntax not compatible with strings)

**Solution**:
```python
# ❌ WRONG (forward reference with |)
def my_function() -> "FT" | None:
    pass

# ✅ CORRECT (use Optional)
from typing import Optional

def my_function() -> Optional["FT"]:
    pass
```

**Rule**: Forward references (quoted types) must use `Optional[...]` or `Union[..., None]`, not `|`.

---

### TYPE_CHECKING Pattern

**Best Practice**: Use `TYPE_CHECKING` for expensive imports only needed for type hints

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from expensive.module import ExpensiveType

def my_function(param: "ExpensiveType") -> None:  # Forward reference
    pass
```

---

## Common Error Patterns

### Error: "Routes registered but 404 on access"

**Checklist**:
1. [ ] Both API and UI routes registered?
2. [ ] Route path matches test URL?
3. [ ] Authentication required? (401 vs 404)
4. [ ] Server restarted after code changes?

### Error: "Server starts but crashes on first request"

**Common Causes**:
1. Service dependency missing (check logs)
2. Import error in route handler
3. Protocol mismatch (service doesn't implement expected interface)

**Diagnostic**:
```bash
# Test a simple endpoint first
curl http://localhost:8000/

# Then test the failing endpoint
curl -v http://localhost:8000/tasks

# Check logs for exceptions
tail -100 /tmp/server.log | grep -A10 "Error\|Exception"
```

---

## Quick Diagnostic Checklist

When server won't start or routes don't work:

```bash
# 1. Clear port
lsof -ti:8000 | xargs kill -9 2>/dev/null || true

# 2. Start server with logging
./dev serve > /tmp/server.log 2>&1 &

# 3. Wait for startup
sleep 25

# 4. Check startup success
grep "Application startup complete" /tmp/server.log

# 5. Check route registration
grep -E "routes registered" /tmp/server.log

# 6. Test endpoints
curl -s -w "HTTP %{http_code}\n" http://localhost:8000/
curl -s -w "HTTP %{http_code}\n" http://localhost:8000/tasks

# 7. Check for errors
grep -E "Error|Exception|Failed" /tmp/server.log | tail -20
```

---

## Getting Help

If issues persist:

1. **Check logs**: Look for ERROR or WARNING messages in server output
2. **Verify environment**: Ensure `.env` file has required variables
3. **Test services**: Use `uv run pytest tests/integration/ -v` to verify core functionality
4. **Consult docs**: Check `/docs/` for architecture and pattern guides
5. **Search issues**: Look in `/docs/migrations/` and completion documents for similar problems

---

## Version History

- **2026-01-31**: Initial version covering Phase 1 deployment issues
  - Port already in use
  - Embeddings service optional
  - Tasks UI routes missing
  - Import errors (Any, forward references, FastHTML components)
