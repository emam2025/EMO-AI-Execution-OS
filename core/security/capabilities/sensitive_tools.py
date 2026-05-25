"""E2 — Sensitive Tool Classification.

Classifies tools by sensitivity level and provides audit logging
for sensitive tool access.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("emo_ai.security.sensitive_tools")


class Sensitivity(str, Enum):
    """Sensitivity level for tool classification."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


SENSITIVE_BY_DEFAULT: Dict[str, Sensitivity] = {
    "execute_command": Sensitivity.CRITICAL,
    "write_file": Sensitivity.HIGH,
    "delete_file": Sensitivity.CRITICAL,
    "read_file": Sensitivity.MEDIUM,
    "web_fetch": Sensitivity.MEDIUM,
    "network_request": Sensitivity.MEDIUM,
    "database_query": Sensitivity.HIGH,
    "sql_execute": Sensitivity.CRITICAL,
    "system_info": Sensitivity.LOW,
    "calculate": Sensitivity.LOW,
    "search": Sensitivity.LOW,
    "analyze": Sensitivity.LOW,
}


class SensitiveToolRegistry:
    """Classifies tools by sensitivity and audits sensitive access.

    Usage:
        registry = SensitiveToolRegistry()
        registry.classify("my_tool", Sensitivity.HIGH)
        if registry.is_sensitive("my_tool"):
            registry.audit_access("my_tool", "exec_123", "user_abc")
    """

    def __init__(self, initial: Optional[Dict[str, Sensitivity]] = None) -> None:
        self._classifications: Dict[str, Sensitivity] = dict(initial or SENSITIVE_BY_DEFAULT)
        self._audit_log: List[Dict[str, Any]] = []

    def classify(self, tool_name: str, level: Sensitivity) -> None:
        """Set the sensitivity level for a tool."""
        self._classifications[tool_name] = level
        logger.debug("Classified %s as %s", tool_name, level)

    def get_sensitivity(self, tool_name: str) -> Sensitivity:
        """Get the sensitivity level for a tool. Returns LOW if unclassified."""
        return self._classifications.get(tool_name, Sensitivity.LOW)

    def is_sensitive(self, tool_name: str, threshold: Sensitivity = Sensitivity.MEDIUM) -> bool:
        """Check if a tool meets or exceeds a sensitivity threshold."""
        level = self.get_sensitivity(tool_name)
        hierarchy = [s.value for s in Sensitivity]
        return hierarchy.index(level.value) >= hierarchy.index(threshold.value)

    def sensitive_tools(self, threshold: Sensitivity = Sensitivity.MEDIUM) -> List[str]:
        """Return all tools at or above the given threshold."""
        return [
            name for name in self._classifications
            if self.is_sensitive(name, threshold)
        ]

    def audit_access(
        self,
        tool_name: str,
        execution_id: str,
        principal: str = "system",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record an audit entry for sensitive tool access."""
        entry = {
            "tool": tool_name,
            "sensitivity": self.get_sensitivity(tool_name).value,
            "execution_id": execution_id,
            "principal": principal,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
        }
        self._audit_log.append(entry)
        logger.info(
            "Sensitive access: %s (%s) by %s for exec %s",
            tool_name, entry["sensitivity"], principal, execution_id,
        )

    def audit_log(self) -> List[Dict[str, Any]]:
        """Return the full audit log."""
        return list(self._audit_log)

    def recent_audit_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return the most recent audit entries."""
        return self._audit_log[-limit:]

    def clear_audit_log(self) -> None:
        """Clear the audit log."""
        self._audit_log.clear()
