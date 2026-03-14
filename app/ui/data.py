"""
SKUEL Data Display Components
================================

Table and Divider display components using MonsterUI.
"""

from monsterui.franken import Divider as MDivider
from monsterui.franken import DividerSplit, DividerT, TableFromDicts, TableFromLists, TableT
from monsterui.franken import Table as MTable

__all__ = [
    "Table",
    "TableFromDicts",
    "TableFromLists",
    "TableT",
    "Divider",
    "DividerSplit",
    "DividerT",
]


# Re-export MonsterUI Table and Divider directly
Table = MTable
Divider = MDivider
