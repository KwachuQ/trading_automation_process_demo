"""Constants for trade tagging and post-session review.

Defines static dropdown values and category options for manual tags
assigned to trades during post-session analysis.
"""

from __future__ import annotations

# Static dropdown values for manual tags
ENTRY_TYPES = [
    "frontrun",
    "standard",
    "late_entry",
    "re-entry",
]

ENTRY_CONTEXTS = [
    "ETH",
    "RTH",
]

CLOSE_TYPES = [
    "SL",
    "trailed_SL",
    "TP",
    "scratch",
    "misclick",
    "manual_exit",
]
