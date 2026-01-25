# SKUEL Folder Consolidation - Migration Summary

**Date:** 2026-01-25
**Status:** ✅ COMPLETE

---

## What Was Done

### ✅ Phase 1: Backup and Verification
- Created backup: `/home/mike/skuel-backup-20260125-070717.tar.gz` (68MB)
- Stopped all running services (Neo4j, Python app)
- Identified hardcoded paths in configuration files

### ✅ Phase 2: Create New Structure
- Created `/home/mike/skuel/` with subdirectories:
  - `app/` - Application code (from `skuel00/`)
  - `infrastructure/` - Neo4j services (from `infra/`)
  - `config/` - Future configs (from `.skuel/`)
- Verified successful copy (file sizes match exactly)
- Used rsync to preserve all file attributes

### ✅ Phase 3: Update Configuration
Updated paths in:
- `.claude/settings.local.json` - Permission rules
- `infrastructure/README.md` - Documentation paths
- `CLAUDE.md` - Project instructions
- `docs/INDEX.md` - Documentation index
- `DOCUMENTATION_UPDATES_2026-01-25.md`
- `adapters/inbound/README_AUTOMATION.md`
- `SETUP.md`
- `docs/README.md`
- `docs/CLAUDE_QUICKSTART.md`

### ✅ Phase 4: Shell Aliases
Added to `~/.bashrc`:
```bash
alias skuel='cd ~/skuel/app'
alias skuel-infra='cd ~/skuel/infrastructure'
alias skuel-root='cd ~/skuel'
```

### ✅ Phase 5: Git Repository
- Initialized git at `/home/mike/skuel/`
- Created comprehensive `.gitignore`
- Initial commit with 4,083 files (645,888 insertions)
- Configured git user for repository

### ✅ Phase 6: Cleanup
- Cleaned npm cache: 527MB → 101MB (freed 426MB)

### ✅ Phase 7: Verification
- Folder structure verified
- Git repository working
- Neo4j started successfully
- Poetry environment functional
- .claude skills accessible (15+ skill folders)
- npm cache cleaned
- Backup preserved

---

## New Directory Structure

```
/home/mike/skuel/
├── .git/                          # Git repository
├── .gitignore                     # Git ignore rules
├── app/                           # Application code (was skuel00/)
│   ├── .claude/                   # Project-specific Claude skills
│   ├── CLAUDE.md                  # Project documentation
│   ├── pyproject.toml             # Poetry configuration
│   ├── poetry.lock                # Poetry dependencies lock file
│   ├── core/                      # Business logic
│   ├── adapters/                  # External interfaces
│   ├── components/                # UI components
│   ├── main.py                    # Application entry point
│   └── ...
├── infrastructure/                # Infrastructure services (was infra/)
│   ├── docker-compose.yml         # Neo4j service definition
│   ├── .env                       # Infrastructure credentials
│   ├── neo4j/                     # Neo4j database
│   └── README.md                  # Infrastructure docs
└── config/                        # Future configs (was .skuel/)
```

---

## Updated Development Workflow

### ⚠️ IMPORTANT: Poetry Commands Must Run from `app/` Directory

The `pyproject.toml` and `poetry.lock` files are located in `/home/mike/skuel/app/`, so **all Poetry commands must be run from that directory**:

```bash
# CORRECT - Run from app directory
cd ~/skuel/app
poetry install
poetry run python main.py
poetry run pytest

# INCORRECT - Will fail with "could not find pyproject.toml"
cd ~/skuel
poetry install  # ❌ FAILS - pyproject.toml not in this directory
```

### Start Infrastructure (once)
```bash
cd ~/skuel/infrastructure
docker compose up -d
```

### Develop Application
```bash
cd ~/skuel/app
poetry install              # Install/update dependencies
poetry run python main.py   # Run application
```

### Testing
```bash
cd ~/skuel/app
poetry run pytest           # Run all tests
poetry run pytest tests/unit  # Run specific test directory
```

### CSS/JS Build
```bash
cd ~/skuel/app
npm run build:css
```

### Using Aliases
```bash
skuel          # cd ~/skuel/app (where Poetry commands work)
skuel-infra    # cd ~/skuel/infrastructure
skuel-root     # cd ~/skuel (git operations only)
```

---

## Outstanding Items

### ⚠️ Manual Cleanup Required

The following old directories could not be automatically removed due to Docker file permissions:

- `/home/mike/skuel00` - Old application directory (most files removed, some Docker artifacts remain)
- `/home/mike/infra` - Old infrastructure directory (Neo4j database files owned by Docker user 7474)

**To clean up manually:**

```bash
# Option 1: Use sudo to remove (requires password)
sudo rm -rf /home/mike/skuel00 /home/mike/infra

# Option 2: Change ownership first, then remove
sudo chown -R mike:mike /home/mike/infra
rm -rf /home/mike/skuel00 /home/mike/infra
```

**Note:** These directories are safe to delete - all content has been successfully copied to `/home/mike/skuel/`.

### 📦 Backup Retention

- Backup file: `/home/mike/skuel-backup-20260125-070717.tar.gz` (68MB)
- **Recommendation:** Keep for 1-2 weeks, then delete after confirming everything works
- To restore if needed: `cd /home/mike && tar -xzf skuel-backup-20260125-070717.tar.gz`

---

## Verification Checklist

- ✅ New structure created at `/home/mike/skuel/`
- ✅ Git repository initialized (commit 15e1487)
- ✅ Configuration files updated with new paths
- ✅ Shell aliases added to `~/.bashrc`
- ✅ Neo4j running from new location
- ✅ Poetry environment working (from `/home/mike/skuel/app/`)
  - Virtual environment: `/home/mike/.cache/pypoetry/virtualenvs/skuel-H8cAGK-Q-py3.12`
  - Python version: 3.12.3
  - All dependencies installed
- ✅ .claude skills accessible
- ✅ npm cache cleaned (426MB freed)
- ✅ Backup preserved

---

## Benefits Achieved

### Organization
- ✅ All SKUEL code in one parent folder
- ✅ Clear separation: `app/` vs `infrastructure/` vs `config/`
- ✅ Single backup target

### Version Control
- ✅ Git repository at root level
- ✅ Comprehensive .gitignore
- ✅ All 4,083 files tracked

### Maintenance
- ✅ Consistent path structure
- ✅ Easier documentation updates
- ✅ Clearer for new developers

---

## Next Steps

1. **Test thoroughly** - Run application for 1-2 days to ensure everything works
2. **Clean up old folders** - Remove `skuel00/` and `infra/` manually (see above)
3. **Update any external scripts** - If you have scripts outside the project referencing old paths
4. **Delete backup** - After confirming everything works (1-2 weeks)
5. **Apply shell aliases** - Run `source ~/.bashrc` or restart terminal

---

## Rollback (If Needed)

If you encounter critical issues:

```bash
# 1. Stop services
cd ~/skuel/infrastructure && docker compose down
pkill -f "python main.py"

# 2. Restore from backup
cd /home/mike
tar -xzf skuel-backup-20260125-070717.tar.gz

# 3. Restart services
cd ~/infra && docker compose up -d
cd ~/skuel00 && poetry run python main.py
```

---

## Common Issues & Solutions

### "Poetry could not find a pyproject.toml file"

**Problem:** Running `poetry install` from `/home/mike/skuel/` instead of `/home/mike/skuel/app/`

**Solution:**
```bash
# Always run Poetry commands from app/ directory
cd ~/skuel/app
poetry install

# Or use the alias
skuel  # Already in the right directory
poetry install
```

The `pyproject.toml` and `poetry.lock` files are in the `app/` subdirectory, so Poetry must be run from there.

---

**Migration completed successfully! 🎉**

All services verified and working. Poetry environment confirmed functional from `app/` directory. The only remaining task is manual cleanup of old directories when you're ready.
