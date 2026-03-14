"""
SKUEL Data Display Components
================================

Table and Divider display components using MonsterUI.
"""

from monsterui.franken import Divider as MDivider
from monsterui.franken import DividerSplit, DividerT
from monsterui.franken import Table as MTable
from monsterui.franken import TableFromDicts, TableFromLists, TableT

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
