---
title: Finance Categories System
updated: 2025-11-27
status: current
category: architecture
tags: [architecture, categories, finance, guide]
related: []
---

# Finance Categories System

**Date:** October 6, 2025
**Status:** Integrated and Active

---

## Overview

The finance categories system provides a **hierarchical, YAML-configured** approach to expense categorization. Instead of hardcoded enums, categories are defined in a configuration file that can be customized without code changes.

---

## Configuration File

**Location:** `/data/config/finance_categories.yaml`

**Structure:**

```yaml
# Main budget categories (top-level)
main_categories:
  - name: "Personal"
    code: "PERSONAL"
    description: "Personal expenses"

  - name: "House (2222)"
    code: "HOUSE"
    description: "House-related expenses for 2222 Brandywine"

  - name: "SKUEL"
    code: "SKUEL"
    description: "SKUEL business expenses"

# Subcategories mapped to main categories
subcategories:
  PERSONAL:
    - name: "Food & Dining"
      code: "food"
      tags: ["groceries", "restaurants", "coffee"]

    - name: "Vehicle"
      code: "vehicle"
      tags: ["gas", "maintenance", "insurance"]

  HOUSE:
    - name: "Mortgage/Rent"
      code: "mortgage"
      tags: ["mortgage", "rent", "property_tax"]

    - name: "Utilities"
      code: "utilities"
      tags: ["electricity", "water", "gas", "trash"]

  SKUEL:
    - name: "Software & Tools"
      code: "software"
      tags: ["licenses", "subscriptions", "apis"]

    - name: "Infrastructure"
      code: "infrastructure"
      tags: ["hosting", "domains", "servers"]
```

**Key Features:**
- ✅ **Hierarchical** - Main categories contain subcategories
- ✅ **Tag-based** - Each subcategory has tags for smart matching
- ✅ **Customizable** - Edit YAML to add/modify categories
- ✅ **No code changes** - Categories loaded at runtime

---

## Category Hierarchy

```
PERSONAL (Main Category)
├── Food & Dining (code: food)
│   └── Tags: groceries, restaurants, coffee
├── Vehicle (code: vehicle)
│   └── Tags: gas, maintenance, insurance
├── Phone & Internet (code: phone)
│   └── Tags: mobile, internet, streaming
├── Health & Fitness (code: health)
│   └── Tags: medical, gym, supplements
├── Personal Care (code: personal_care)
│   └── Tags: haircut, clothing, supplies
└── Entertainment (code: entertainment)
    └── Tags: movies, games, hobbies

HOUSE (Main Category)
├── Mortgage/Rent (code: mortgage)
│   └── Tags: mortgage, rent, property_tax
├── Utilities (code: utilities)
│   └── Tags: electricity, water, gas, trash
├── Maintenance (code: maintenance)
│   └── Tags: repairs, landscaping, cleaning
├── Home Improvement (code: improvement)
│   └── Tags: renovation, furniture, appliances
└── Insurance (code: home_insurance)
    └── Tags: homeowners, flood, umbrella

SKUEL (Main Category)
├── Software & Tools (code: software)
│   └── Tags: licenses, subscriptions, apis
├── Infrastructure (code: infrastructure)
│   └── Tags: hosting, domains, servers
├── Professional Services (code: professional)
│   └── Tags: consulting, legal, accounting
├── Marketing (code: marketing)
│   └── Tags: advertising, content, design
└── Education & Training (code: education)
    └── Tags: courses, books, conferences
```

---

## API Usage

### 1. Loading Categories

```python
from core.utils.finance_categories import load_finance_categories

# Load complete hierarchy
categories = load_finance_categories()

# Access main categories
for cat in categories.main_categories:
    print(f"{cat.code}: {cat.name}")
# Output:
# PERSONAL: Personal
# HOUSE: House (2222)
# SKUEL: SKUEL

# Access subcategories
personal_subs = categories.subcategories.get('PERSONAL', ())
for sub in personal_subs:
    print(f"  {sub.code}: {sub.name} - Tags: {sub.tags}")
# Output:
#   food: Food & Dining - Tags: ('groceries', 'restaurants', 'coffee')
#   vehicle: Vehicle - Tags: ('gas', 'maintenance', 'insurance')
```

---

### 2. Category Lookup

```python
from core.utils.finance_categories import get_category

# Get category by code
food_cat = get_category('food')
print(f"{food_cat.name}: {food_cat.tags}")
# Output: Food & Dining: ('groceries', 'restaurants', 'coffee')

# Get main category
personal = get_category('PERSONAL')
print(f"{personal.name}: {personal.description}")
# Output: Personal: Personal expenses
```

---

### 3. Smart Categorization (Tag Matching)

```python
from core.utils.finance_categories import suggest_category

# Suggest category based on expense description
description = "Whole Foods groceries $52.34"
suggested = suggest_category(description)
print(f"Suggested category: {suggested}")
# Output: Suggested category: food

# Another example
description = "AWS hosting bill"
suggested = suggest_category(description)
print(f"Suggested category: {suggested}")
# Output: Suggested category: infrastructure
```

---

### 4. Validation

```python
from core.utils.finance_categories import validate_category

# Validate category code
is_valid = validate_category('food')
print(f"Is 'food' valid? {is_valid}")
# Output: Is 'food' valid? True

is_valid = validate_category('invalid_category')
print(f"Is 'invalid_category' valid? {is_valid}")
# Output: Is 'invalid_category' valid? False
```

---

## FinanceService Integration

The `FinanceService` automatically loads categories on initialization.

### Service Methods

#### Get All Categories

```python
finance_service = FinanceService(backend)

# Get complete hierarchy
hierarchy = finance_service.get_all_categories()

# Get main categories as dicts
main_cats = finance_service.get_main_categories()
# Returns: [
#   {"name": "Personal", "code": "PERSONAL", "description": "Personal expenses"},
#   {"name": "House (2222)", "code": "HOUSE", "description": "House-related expenses..."},
#   {"name": "SKUEL", "code": "SKUEL", "description": "SKUEL business expenses"}
# ]
```

#### Get Subcategories

```python
# Get subcategories for PERSONAL
personal_subs = finance_service.get_subcategories_for('PERSONAL')
# Returns: [
#   {"name": "Food & Dining", "code": "food", "tags": ["groceries", "restaurants", "coffee"], "parent": "PERSONAL"},
#   {"name": "Vehicle", "code": "vehicle", "tags": ["gas", "maintenance", "insurance"], "parent": "PERSONAL"},
#   ...
# ]
```

#### Validate Category

```python
result = finance_service.validate_expense_category('food')
if result.is_ok:
    print("Category is valid!")
else:
    print(f"Error: {result.error.message}")
```

#### Suggest Category

```python
suggestion = finance_service.suggest_category_for_expense("Starbucks coffee")
if suggestion:
    print(f"Suggested: {suggestion['name']} (confidence: {suggestion['confidence']})")
# Output: Suggested: Food & Dining (confidence: high)
```

#### Get Category Info

```python
info = finance_service.get_category_info('software')
print(info)
# Output: {
#   "name": "Software & Tools",
#   "code": "software",
#   "description": None,
#   "tags": ["licenses", "subscriptions", "apis"],
#   "parent": "SKUEL",
#   "path": "SKUEL.software"
# }
```

---

## Usage Examples

### Creating an Expense with Smart Categorization

```python
from core.services.finance_service import FinanceService

# Initialize service
finance_service = FinanceService(backend)

# User enters expense description
description = "Whole Foods groceries $52.34"

# Suggest category
suggested = finance_service.suggest_category_for_expense(description)

if suggested:
    print(f"💡 Suggested category: {suggested['name']}")
    print(f"   Confidence: {suggested['confidence']}")
    # User can accept or choose different category
    category_code = suggested['code']  # 'food'
else:
    # Fall back to manual selection
    categories = finance_service.get_main_categories()
    # Show category picker UI
```

### Building a Category Picker UI

```python
# Get all main categories for dropdown
main_categories = finance_service.get_main_categories()

# User selects "PERSONAL"
selected_main = "PERSONAL"

# Load subcategories dynamically
subcategories = finance_service.get_subcategories_for(selected_main)

# Display in UI:
# - Food & Dining
# - Vehicle
# - Phone & Internet
# - Health & Fitness
# - Personal Care
# - Entertainment

# User selects "Food & Dining" (code: 'food')
# Store 'food' as the expense category
```

### Expense Categorization Flow

```python
async def create_expense_with_categorization(
    description: str,
    amount: float,
    finance_service: FinanceService
):
    """Create expense with smart categorization."""

    # 1. Suggest category based on description
    suggestion = finance_service.suggest_category_for_expense(description)

    if suggestion:
        category_code = suggestion['code']
        print(f"✅ Auto-categorized as: {suggestion['name']}")
    else:
        # 2. Prompt user to select category
        main_cats = finance_service.get_main_categories()
        print("Select main category:")
        for i, cat in enumerate(main_cats):
            print(f"  {i+1}. {cat['name']}")

        # User selects PERSONAL (index 0)
        selected_main = main_cats[0]['code']

        # Show subcategories
        subs = finance_service.get_subcategories_for(selected_main)
        print(f"\nSelect subcategory for {selected_main}:")
        for i, sub in enumerate(subs):
            print(f"  {i+1}. {sub['name']}")

        # User selects Food & Dining (index 0)
        category_code = subs[0]['code']

    # 3. Validate category
    validation = finance_service.validate_expense_category(category_code)
    if not validation.is_ok:
        print(f"❌ Invalid category: {validation.error.message}")
        return

    # 4. Create expense with validated category
    expense = ExpensePure(
        uid=generate_uid(),
        description=description,
        amount=amount,
        category=category_code,  # Stores 'food' or other code
        date=date.today()
    )

    # 5. Save to backend
    result = await finance_service.create(expense)
    return result
```

---

## Customizing Categories

### Adding a New Category

**Edit:** `/data/config/finance_categories.yaml`

```yaml
subcategories:
  PERSONAL:
    # ... existing categories ...

    # Add new category
    - name: "Pet Care"
      code: "pet_care"
      tags: ["vet", "pet_food", "grooming", "pet_supplies"]
```

**Restart service** - Categories are loaded on initialization

**No code changes needed!**

### Adding Tags to Existing Category

```yaml
subcategories:
  PERSONAL:
    - name: "Food & Dining"
      code: "food"
      tags: ["groceries", "restaurants", "coffee", "takeout", "delivery"]  # Added new tags
```

### Adding a New Main Category

```yaml
main_categories:
  # ... existing ...

  - name: "Investment Property"
    code: "PROPERTY_2"
    description: "Second property expenses"

subcategories:
  PROPERTY_2:
    - name: "Mortgage"
      code: "property2_mortgage"
      tags: ["mortgage", "interest"]

    - name: "Maintenance"
      code: "property2_maintenance"
      tags: ["repairs", "landscaping"]
```

---

## Data Flow

```
User enters expense
       ↓
Finance Service suggests category (tag matching)
       ↓
User accepts or selects different category
       ↓
Category code validated against YAML config
       ↓
Expense saved with category code
       ↓
Category displayed in UI using get_category_info()
```

---

## Benefits Over Hardcoded Enums

| Aspect | Old (Enum) | New (YAML) |
|--------|------------|------------|
| **Customization** | Requires code changes | Edit YAML file |
| **Deployment** | Rebuild & redeploy | Just restart service |
| **Hierarchy** | Flat list | Multi-level hierarchy |
| **Tags** | Not supported | Built-in tag matching |
| **UI Generation** | Manual | Auto-generated from config |
| **User-specific** | One size fits all | Can have user-specific configs (future) |

---

## Implementation Details

### Singleton Pattern

The loader uses a singleton pattern to ensure categories are loaded only once per process:

```python
loader = get_categories_loader()  # Same instance every time
hierarchy = loader.get_hierarchy()  # Cached result
```

### Immutable Data Structures

All category data uses frozen dataclasses to prevent accidental modification:

```python
@dataclass(frozen=True)
class CategoryInfo:
    name: str
    code: str
    tags: tuple[str, ...]  # Immutable tuple
```

### Performance

- Categories loaded once at service initialization
- Lookups are O(1) dictionary operations
- Tag matching is O(n) where n = number of tags (~50)
- Minimal memory footprint (~few KB)

---

## Future Enhancements

### User-Specific Categories

```yaml
# /data/config/finance_categories.{user_uid}.yaml
# User-specific overrides for custom categorization
```

### Machine Learning Categorization

```python
# Train on historical expense descriptions + categories
# Improve suggestion confidence scores
# Learn user's categorization preferences
```

### Budget Integration

```yaml
subcategories:
  PERSONAL:
    - name: "Food & Dining"
      code: "food"
      tags: ["groceries", "restaurants"]
      budget_monthly: 600.00  # Budget amount
```

### Category Analytics

```python
# Track most used categories
# Identify unused categories
# Suggest category merges/splits
```

---

## Related Documentation

- **FinanceService:** `/core/services/finance_service.py`
- **Categories Loader:** `/core/utils/finance_categories.py`
- **Config File:** `/data/config/finance_categories.yaml`

---

## Summary

✅ **Finance categories are now loaded from YAML configuration**
✅ **FinanceService provides convenience methods for categorization**
✅ **Smart tag-based category suggestions**
✅ **Fully customizable without code changes**
✅ **Hierarchical structure supports complex budgeting needs**

**Last Updated:** October 6, 2025
**Integration Status:** Complete and Active ✅
