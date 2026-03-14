# Tables Requiring Custom Design

Three tables were not migrated to `TableFromDicts` because their structure exceeds what the component API supports cleanly.

## 1. Habit System Breakdown (`ui/habits/atomic_intelligence.py:232`)

4 hardcoded rows + TOTAL row with `border-t-2`. Each row is a specific essentiality level with emoji prefix and conditional status Span. The TOTAL row needs per-row border styling. Could use `footer_data` for total but the hardcoded nature means `TableFromDicts` adds complexity without reducing code.

## 2. Velocity Breakdown (`ui/habits/atomic_intelligence.py:407`)

No `Thead`. 4 calculation rows + total row. Each row shows weighted math (`Nx weight = points`). This is a calculation layout, not tabular data. `TableFromDicts` requires headers.

## 3. Alternatives Comparison (`ui/patterns/relationships/alternatives_grid.py:61`)

Dynamic column count (1 + N alternatives). Headers are entity titles with composite Th content (title + entity_type subtitle). Transposed layout (rows=criteria, cols=entities). Dynamic columns make the `body_cell_render` pattern awkward.

## When to Revisit

If MonsterUI adds per-row styling or headerless table support, tables 1-2 become candidates. Table 3 would need a dynamic-column variant of `TableFromDicts`.
