#!/bin/bash
# Config Directory Consolidation Migration
# =========================================
# Date: 2025-10-06
# Purpose: Consolidate three config directories into clear, purpose-driven structure
#
# BEFORE:
#   /home/mike/skuel0/core/config/    - Application config (Python)
#   /home/mike/skuel0/config/         - Orphaned domain data (YAML)
#   /home/mike/skuel0/conf/           - Infrastructure (Docker/Neo4j)
#
# AFTER:
#   /home/mike/skuel0/core/config/    - Application config (unchanged)
#   /home/mike/skuel0/data/config/    - Domain data config (moved from /config)
#   /home/mike/skuel0/infrastructure/ - Infrastructure (renamed from /conf)

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Base directory
BASE_DIR="/home/mike/skuel0"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Config Directory Consolidation Migration${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Function to print status
print_status() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

# Step 1: Verify current state
echo -e "${BLUE}Step 1: Verifying current state...${NC}"

if [ ! -d "${BASE_DIR}/core/config" ]; then
    print_error "core/config directory not found!"
    exit 1
fi
print_status "core/config exists"

if [ ! -d "${BASE_DIR}/config" ]; then
    print_warning "config directory not found (may have been moved already)"
else
    print_status "config directory exists"
fi

if [ ! -d "${BASE_DIR}/conf" ]; then
    print_warning "conf directory not found (may have been moved already)"
else
    print_status "conf directory exists"
fi

echo ""

# Step 2: Create new directory structure
echo -e "${BLUE}Step 2: Creating new directory structure...${NC}"

mkdir -p "${BASE_DIR}/data/config"
print_status "Created data/config directory"

echo ""

# Step 3: Move domain config files
echo -e "${BLUE}Step 3: Moving domain configuration files...${NC}"

if [ -d "${BASE_DIR}/config" ]; then
    if [ -f "${BASE_DIR}/config/finance_categories.yaml" ]; then
        mv "${BASE_DIR}/config/finance_categories.yaml" "${BASE_DIR}/data/config/"
        print_status "Moved finance_categories.yaml to data/config/"
    else
        print_warning "finance_categories.yaml not found in config/"
    fi

    # Check if config directory is now empty
    if [ -z "$(ls -A ${BASE_DIR}/config)" ]; then
        rmdir "${BASE_DIR}/config"
        print_status "Removed empty config directory"
    else
        print_warning "config directory not empty, manual review needed:"
        ls -la "${BASE_DIR}/config"
    fi
else
    print_warning "config directory doesn't exist, skipping"
fi

echo ""

# Step 4: Rename infrastructure directory
echo -e "${BLUE}Step 4: Renaming infrastructure directory...${NC}"

if [ -d "${BASE_DIR}/conf" ]; then
    if [ -d "${BASE_DIR}/infrastructure" ]; then
        print_warning "infrastructure directory already exists, merging contents..."
        cp -r "${BASE_DIR}/conf/"* "${BASE_DIR}/infrastructure/"
        rm -rf "${BASE_DIR}/conf"
        print_status "Merged conf into existing infrastructure directory"
    else
        mv "${BASE_DIR}/conf" "${BASE_DIR}/infrastructure"
        print_status "Renamed conf to infrastructure"
    fi
else
    print_warning "conf directory doesn't exist, may have been renamed already"
fi

echo ""

# Step 5: Create README files
echo -e "${BLUE}Step 5: Creating README files...${NC}"

# README for core/config
cat > "${BASE_DIR}/core/config/README.md" << 'EOF'
# Application Configuration

Python application runtime settings, credentials, and environment configuration.

## Contents

- `unified_config.py` - Main configuration dataclasses and factory functions
- `settings.py` - Settings accessor functions for the application
- `credential_setup.py` - Interactive credential setup tool
- `credential_store.py` - Secure credential storage and retrieval
- `environment_validator.py` - Environment validation and API key management
- `validation.py` - Configuration validation logic

## Usage

```python
from core.config import get_settings, get_database_config

settings = get_settings()
db_config = get_database_config()
```

## Credential Setup

**Do not edit credential files manually.** Use the credential setup tool:

```bash
python -m core.config
```

## Architecture

This configuration module follows SKUEL's principles:
- **Single source of truth** - All settings flow through unified_config.py
- **Type-safe** - Pydantic-based configuration with validation
- **Environment-aware** - Automatic environment detection and adaptation
- **Secure** - Credentials stored separately with proper file permissions

## Configuration Hierarchy

1. **Environment variables** (highest priority)
2. **Credential store** (secure vault)
3. **Default values** (fallback)

---

**Location:** `/core/config/` - Application configuration (Python)
**Related:** `/data/config/` - Domain data configuration (YAML)
**Related:** `/infrastructure/` - Infrastructure configuration (Docker/Neo4j)
EOF

print_status "Created core/config/README.md"

# README for data/config
cat > "${BASE_DIR}/data/config/README.md" << 'EOF'
# Domain Configuration Data

User-editable domain configuration files in YAML/JSON format.

## Purpose

This directory contains domain-specific configuration data that users can customize:
- Finance categories and budget templates
- Default settings for domain entities
- User-customizable templates
- Domain-specific constants

## Contents

- `finance_categories.yaml` - Finance category hierarchy for expense tracking

## Usage

These files are loaded by services at runtime:

```python
from core.services.finance_service import load_finance_categories

categories = load_finance_categories()
```

## Editing Guidelines

1. **YAML format** - Use proper YAML syntax (validate with `yamllint`)
2. **Comments** - Add comments to explain purpose
3. **Structure** - Follow existing patterns for consistency
4. **Validation** - Run service tests after editing to verify changes

## Adding New Configuration

To add new domain configuration:

1. Create YAML file in this directory
2. Add loader function in relevant service
3. Document structure and usage in this README
4. Add validation tests

## Example: Finance Categories Structure

```yaml
main_categories:
  - name: "Personal"
    code: "PERSONAL"
    description: "Personal expenses"

subcategories:
  PERSONAL:
    - name: "Food & Dining"
      code: "food"
      tags: ["groceries", "restaurants"]
```

---

**Location:** `/data/config/` - Domain data configuration (YAML)
**Related:** `/core/config/` - Application configuration (Python)
**Related:** `/infrastructure/` - Infrastructure configuration (Docker/Neo4j)
EOF

print_status "Created data/config/README.md"

# README for infrastructure
cat > "${BASE_DIR}/infrastructure/README.md" << 'EOF'
# Infrastructure Configuration

Docker, Neo4j, and deployment configuration files.

## Contents

- `apoc.conf` - Neo4j APOC plugin configuration
- `neo4j.conf.example` - Neo4j database configuration template
- `docker-compose.neo4j.yml` - Docker Compose for Neo4j container

## Purpose

This directory contains infrastructure-level configuration used by:
- Docker containers
- Neo4j database
- Deployment scripts
- Development environment setup

## Neo4j Configuration

### APOC Configuration

The `apoc.conf` file configures the APOC plugin for Neo4j:
- Enabled procedures and functions
- Security settings
- Performance tuning

**Phase 6 Update (October 2025):**
APOC is now used **only for infrastructure operations**, not domain logic.
Domain services use pure Cypher with semantic relationships.

### Neo4j Configuration Template

The `neo4j.conf.example` provides a template for Neo4j configuration.
Copy and customize as needed:

```bash
cp neo4j.conf.example neo4j.conf
# Edit neo4j.conf with your settings
```

## Docker Compose

### Starting Neo4j

```bash
cd /home/mike/skuel0/infrastructure
docker-compose -f docker-compose.neo4j.yml up -d
```

### Stopping Neo4j

```bash
docker-compose -f docker-compose.neo4j.yml down
```

### Viewing Logs

```bash
docker-compose -f docker-compose.neo4j.yml logs -f
```

## Configuration Principles

1. **Infrastructure only** - Application config goes in `/core/config/`
2. **Version controlled** - All config files tracked in git
3. **Environment-specific** - Use `.example` pattern for sensitive settings
4. **Documented** - Add comments explaining each setting

## Security Notes

- **Never commit passwords** - Use environment variables or `.env` files
- **File permissions** - Keep sensitive configs with restricted permissions
- **APOC security** - Only enable necessary procedures (see apoc.conf)

---

**Location:** `/infrastructure/` - Infrastructure configuration (Docker/Neo4j)
**Related:** `/core/config/` - Application configuration (Python)
**Related:** `/data/config/` - Domain data configuration (YAML)
EOF

print_status "Created infrastructure/README.md"

echo ""

# Step 6: Verify final structure
echo -e "${BLUE}Step 6: Verifying final structure...${NC}"

echo ""
echo -e "${YELLOW}Final directory structure:${NC}"
echo ""

if [ -d "${BASE_DIR}/core/config" ]; then
    echo -e "${GREEN}✓${NC} /core/config/           - Application config (Python)"
    echo "    Files: $(ls -1 ${BASE_DIR}/core/config/*.py | wc -l) Python files"
else
    echo -e "${RED}✗${NC} /core/config/ - MISSING!"
fi

if [ -d "${BASE_DIR}/data/config" ]; then
    echo -e "${GREEN}✓${NC} /data/config/           - Domain data config (YAML)"
    echo "    Files: $(ls -1 ${BASE_DIR}/data/config/*.yaml 2>/dev/null | wc -l) YAML files"
else
    echo -e "${RED}✗${NC} /data/config/ - MISSING!"
fi

if [ -d "${BASE_DIR}/infrastructure" ]; then
    echo -e "${GREEN}✓${NC} /infrastructure/        - Infrastructure (Docker/Neo4j)"
    echo "    Files: $(ls -1 ${BASE_DIR}/infrastructure/* 2>/dev/null | wc -l) config files"
else
    echo -e "${RED}✗${NC} /infrastructure/ - MISSING!"
fi

echo ""

# Check for old directories
if [ -d "${BASE_DIR}/config" ]; then
    print_warning "Old /config directory still exists"
fi

if [ -d "${BASE_DIR}/conf" ]; then
    print_warning "Old /conf directory still exists"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Migration Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Next steps:"
echo "1. Review the README files in each config directory"
echo "2. Create finance categories loader (see data/config/README.md)"
echo "3. Update any hardcoded paths in scripts"
echo "4. Run tests to verify no imports broke"
echo ""
