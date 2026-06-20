"""Phase 4.2.2 — CapabilityRegistry: maps tools → capabilities.

Central registry for looking up execution capabilities by tool name.
Supports file-based permission manifests (JSON/YAML).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from core.models.dag import ToolSpec
from core.security.capabilities.capability_model import (
    AccessMode,
    Capability,
    Scope,
)

logger = logging.getLogger("emo_ai.security.capability_registry")

DEFAULT_CAPABILITY = Capability.restricted()

FULL_TRUST_TOOLS = {
    "calculate", "search", "analyze",
}

RESTRICTED_TOOLS = {
    "execute_command": "Full shell access — requires explicit approval per execution",
    "write_file": "Filesystem write — requires path validation and approval",
    "delete_file": "Filesystem delete — requires approval and backup verification",
}


def _cap_from_dict(name: str, d: Dict[str, Any]) -> Capability:
    """Build a Capability from a dict."""
    scopes_raw = d.get("scopes", ["execute"])
    scopes = [Scope(s) if isinstance(s, str) else s for s in scopes_raw]
    return Capability(
        network=d.get("network", False),
        filesystem=AccessMode(d.get("filesystem", "none")),
        subprocess=d.get("subprocess", False),
        max_cpu=float(d.get("max_cpu", 0)),
        max_memory=int(d.get("max_memory", 0)),
        allowed_domains=d.get("allowed_domains", []),
        allowed_paths=d.get("allowed_paths", []),
        scopes=scopes,
        description=d.get("description", f"Loaded for {name}"),
    )


class CapabilityRegistry:
    """Maps tool names to their allowed capabilities.

    Usage:
        registry = CapabilityRegistry()
        cap = registry.get_capability("web_fetch")
        if cap.network:
            # allow execution
    """

    def __init__(self) -> None:
        self._capabilities: Dict[str, Capability] = {}
        self._audit_log: List[Dict[str, Any]] = []
        self._init_defaults()

    def _init_defaults(self) -> None:
        for tool in FULL_TRUST_TOOLS:
            self.register(tool, Capability.full())

    def register(self, tool_name: str, capability: Capability) -> None:
        """Register a capability for a tool."""
        old_cap = self._capabilities.get(tool_name)
        self._capabilities[tool_name] = capability
        self._audit_log.append({
            'action': 'register',
            'tool': tool_name,
            'old_trust': old_cap.description if old_cap else 'none',
            'new_trust': capability.description,
        })
        logger.debug("Registered capability for %s: %s", tool_name, capability.description)

    def get_capability(self, tool_name: str) -> Capability:
        """Get the capability for a tool. Returns restricted default if not registered."""
        return self._capabilities.get(tool_name, DEFAULT_CAPABILITY)

    def has_capability(self, tool_name: str) -> bool:
        """Check if a tool has an explicitly registered capability."""
        return tool_name in self._capabilities

    def remove(self, tool_name: str) -> None:
        """Remove a tool's capability (reverts to restricted)."""
        old_cap = self._capabilities.pop(tool_name, None)
        if old_cap:
            self._audit_log.append({
                'action': 'remove',
                'tool': tool_name,
                'old_trust': old_cap.description,
            })

    def get_audit_log(self) -> List[Dict[str, Any]]:
        """Return the capability audit log."""
        return list(self._audit_log)

    def all_capabilities(self) -> Dict[str, Capability]:
        """Return all registered capabilities."""
        return dict(self._capabilities)

    def load_from_specs(self, specs: Dict[str, ToolSpec]) -> None:
        """Auto-register capabilities from tool specs metadata."""
        for name, spec in specs.items():
            meta = getattr(spec, "metadata", {}) or {}
            cap_config = meta.get("capability", {})
            if cap_config:
                cap = _cap_from_dict(name, cap_config)
                self.register(name, cap)

    # ── Permission Manifests (E2) ────────────────────────────────

    def load_from_dict(self, data: Dict[str, Any]) -> int:
        """Load capabilities from a dict (in-memory manifest).

        Expected format:
            {"tools": {"name": {"network": true, "filesystem": "read", ...}}}
        """
        tools = data.get("tools", data)
        count = 0
        for name, config in tools.items():
            if isinstance(config, dict):
                cap = _cap_from_dict(name, config)
                self.register(name, cap)
                count += 1
        logger.info("Loaded %d capabilities from dict manifest", count)
        return count

    def load_from_json(self, path: str) -> int:
        """Load capabilities from a JSON manifest file."""
        with open(path, "r") as f:
            data = json.load(f)
        return self.load_from_dict(data)

    def load_from_yaml(self, path: str) -> int:
        """Load capabilities from a YAML manifest file."""
        try:
            import yaml
        except ImportError:
            raise ImportError("PyYAML is required to load YAML manifests. Install with: pip install pyyaml")
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        return self.load_from_dict(data)

    # ── Scope-aware queries (E2) ─────────────────────────────────

    def has_scope(self, tool_name: str, scope: Scope) -> bool:
        """Check if a registered tool has the given scope."""
        cap = self._capabilities.get(tool_name)
        if cap is None:
            return False
        return cap.has_scope(scope)

    def tools_with_scope(self, scope: Scope) -> List[str]:
        """Return all tool names that have the given scope."""
        return [name for name, cap in self._capabilities.items() if cap.has_scope(scope)]

    def tools_with_minimum_scope(self, tool_names: List[str], minimum: Scope) -> List[str]:
        """Filter tool list to those meeting a minimum scope."""
        hierarchy = {s: i for i, s in enumerate(Scope)}
        min_rank = hierarchy.get(minimum, 0)
        result = []
        for name in tool_names:
            cap = self._capabilities.get(name)
            if cap is None:
                continue
            if any(hierarchy.get(s, -1) >= min_rank for s in cap.scopes):
                result.append(name)
        return result
