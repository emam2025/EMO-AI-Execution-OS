"""Parse DEVELOPER.md Canon section into structured rules."""

import re
from typing import Any, Dict, List


def load_canon_from_markdown(text: str) -> List[Dict[str, str]]:
    """Extract LAW definitions from markdown text.

    Matches patterns like::

        | **LAW 14** | All boundary decisions MUST be derived from CodeGraph analysis |
        **LAW 13:** `CompositionRoot` is the only valid entry point
    """
    rules: List[Dict[str, str]] = []

    # Table row pattern: | **LAW N** | description |
    table_pattern = r"\|\s*\*\*LAW\s+(\d+)\*\*\s*\|\s*(.+?)\s*\|"
    for num, desc in re.findall(table_pattern, text):
        rules.append({
            "id": f"LAW_{num}",
            "description": desc.strip(),
            "severity": "HIGH",
        })

    # Inline pattern: **LAW N:** description
    inline_pattern = r"\*\*LAW\s+(\d+):\*\*\s*(.+?)(?:\n|$)"
    for num, desc in re.findall(inline_pattern, text):
        rules.append({
            "id": f"LAW_{num}",
            "description": desc.strip(),
            "severity": "HIGH",
        })

    return rules
