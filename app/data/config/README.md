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
