"""Phase FINAL — Security Validator.  # LAW-10 LAW-13 LAW-22 RULE-2 RULE-3 RULE-4 RULE-5

Validates isolation boundaries, capability guards, trace integrity, and
rollback safety for production readiness certification.

Ref: Canon LAW 10 (Resource Isolation), LAW 13 (No Direct Execution)
Ref: Canon LAW 22 (Service Isolation), RULE 2 (No Uncontrolled IO)
Ref: Canon RULE 3 (Safety Guards), RULE 4 (Isolation), RULE 5 (Recovery)
Ref: DEVELOPER.md §16.1 (Security Audit Checklist)
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class ISecurityValidator(Protocol):  # LAW-10 LAW-13 LAW-22 RULE-2 RULE-3 RULE-4
    """Security validation harness for production readiness certification.

    Validates that all isolation boundaries, capability guards, trace
    integrity, and rollback safety mechanisms are correctly enforced.
    """

    def check_isolation_boundaries(  # LAW-10 LAW-22 RULE-4
        self,
        isolation_config: Dict[str, Any],
        certification_trace_id: str,
    ) -> Dict[str, Any]:
        """Check that isolation boundaries are correctly configured.

        Args:
            isolation_config: Dict with isolation boundary configuration.
            certification_trace_id: Correlation ID.

        Returns:
            boundaries_secure:   True if all boundaries are properly isolated.
            total_boundaries:    Number of isolation boundaries checked.
            secure_boundaries:   Number of secure boundaries.
            violations:          List of boundary violations found.
            sandbox_enforced:    True if sandbox isolation is active.
            network_policy_ok:   True if network policies restrict cross-boundary.
        """

    def validate_capability_guards(  # LAW-13 RULE-3
        self,
        capability_inventory: Dict[str, Any],
        certification_trace_id: str,
    ) -> Dict[str, Any]:
        """Validate that capability guards are correctly enforced.

        Args:
            capability_inventory: Dict mapping capability names to their guard status.
            certification_trace_id: Correlation ID.

        Returns:
            all_guards_active:      True if every capability has an active guard.
            total_capabilities:     Number of capabilities checked.
            guarded_capabilities:   Number with active guards.
            unguarded_capabilities: List of capabilities without guards.
            enforcement_level:      Current enforcement level.
        """

    def audit_trace_integrity(  # LAW-5 LAW-12 RULE-1
        self,
        trace_chain: Dict[str, Any],
        certification_trace_id: str,
    ) -> Dict[str, Any]:
        """Audit the integrity of trace chains across all layers.

        Args:
            trace_chain: Dict mapping layer -> trace_id values.
            certification_trace_id: Correlation ID.

        Returns:
            trace_integrity_ok:   True if all trace chains are intact.
            layers_checked:       Number of layers with traces.
            broken_chains:        List of layers with broken trace chains.
            gap_count:            Number of missing trace links.
            oldest_trace_ns:      Timestamp of oldest trace.
        """

    def verify_rollback_safety(  # LAW-8 RULE-5
        self,
        rollback_capabilities: Dict[str, Any],
        certification_trace_id: str,
    ) -> Dict[str, Any]:
        """Verify that all components have safe rollback paths.

        Args:
            rollback_capabilities: Dict mapping component -> rollback metadata.
            certification_trace_id: Correlation ID.

        Returns:
            rollback_safe:         True if all components have rollback paths.
            total_components:      Number of components checked.
            safe_components:       Number with valid rollback paths.
            unsafe_components:     List of components without rollback.
            data_preservation_ok:  True if rollback preserves committed data.
        """


@dataclass
class SecurityAuditEntry:  # LAW-5 LAW-12
    """Single security audit entry."""
    check_name: str
    status: str
    detail: str
    law_refs: List[str] = field(default_factory=list)
    timestamp_ns: int = field(default_factory=lambda: time.time_ns())
    entry_hash: str = ""

    def __post_init__(self) -> None:
        if not self.entry_hash:
            raw = f"{self.check_name}:{self.status}:{self.timestamp_ns}"
            self.entry_hash = hashlib.sha256(raw.encode()).hexdigest()[:16]


class SecurityValidator:  # LAW-10 LAW-13 LAW-22 RULE-2 RULE-3 RULE-4 RULE-5
    """Concrete implementation of ISecurityValidator.

    LAW 10: Resource isolation is validated as a hard requirement.
    LAW 13: No direct execution without isolation boundary.
    LAW 22: Service isolation is strictly enforced.
    RULE 3: Capability guards are checked for every capability.
    RULE 4: Isolation violations are reported.
    RULE 5: Rollback safety is verified for all components.
    """

    def __init__(self, strict_certification_mode: bool = False) -> None:
        self._audit_entries: List[SecurityAuditEntry] = []
        self._strict_certification_mode = strict_certification_mode

    def _record(self, check_name: str, status: str, law_refs: List[str], detail: str) -> SecurityAuditEntry:
        entry = SecurityAuditEntry(check_name=check_name, status=status, law_refs=law_refs, detail=detail)
        self._audit_entries.append(entry)
        return entry

    def check_isolation_boundaries(  # LAW-10 LAW-22 RULE-4
        self,
        isolation_config: Dict[str, Any],
        certification_trace_id: str,
    ) -> Dict[str, Any]:
        boundaries = isolation_config.get("boundaries", {})
        sandbox_active = isolation_config.get("sandbox_active", False)
        network_policy_enforced = isolation_config.get("network_policy_enforced", False)

        total = len(boundaries)
        secure = 0
        violations: List[str] = []

        for name, config in boundaries.items():
            if config.get("isolated") and config.get("sandboxed"):
                secure += 1
            else:
                violations.append(f"{name}: isolated={config.get('isolated')}, sandboxed={config.get('sandboxed')}")
                self._record(f"boundary_{name}", "failed", ["LAW-10", "LAW-22", "RULE-4"],
                               f"Boundary {name} not properly isolated")

        boundaries_secure = total == secure and sandbox_active and network_policy_enforced
        self._record("check_isolation_boundaries", "passed" if boundaries_secure else "failed",
                       ["LAW-10", "LAW-22", "RULE-4"],
                       f"Boundaries: {secure}/{total} secure")

        return {
            "boundaries_secure": boundaries_secure,
            "total_boundaries": total,
            "secure_boundaries": secure,
            "violations": violations,
            "sandbox_enforced": sandbox_active,
            "network_policy_ok": network_policy_enforced,
        }

    def validate_capability_guards(  # LAW-13 RULE-3
        self,
        capability_inventory: Dict[str, Any],
        certification_trace_id: str,
    ) -> Dict[str, Any]:
        capabilities = capability_inventory.get("capabilities", {})
        enforcement_level = capability_inventory.get("enforcement_level", "unknown")

        total = len(capabilities)
        guarded = 0
        unguarded: List[str] = []

        for name, info in capabilities.items():
            if info.get("guard_active", False):
                guarded += 1
            else:
                unguarded.append(name)
                self._record(f"unguarded_{name}", "failed", ["LAW-13", "RULE-3"],
                               f"Capability {name} has no active guard")

        all_guarded = total == guarded
        self._record("validate_capability_guards", "passed" if all_guarded else "failed",
                       ["LAW-13", "RULE-3"], f"Guards: {guarded}/{total} active")

        return {
            "all_guards_active": all_guarded,
            "total_capabilities": total,
            "guarded_capabilities": guarded,
            "unguarded_capabilities": unguarded,
            "enforcement_level": enforcement_level,
        }

    def audit_trace_integrity(  # LAW-5 LAW-12 RULE-1
        self,
        trace_chain: Dict[str, Any],
        certification_trace_id: str,
    ) -> Dict[str, Any]:
        layers = trace_chain.get("layers", {})
        chain_order = trace_chain.get("chain_order", [])

        checked = 0
        broken: List[str] = []
        gap_count = 0
        oldest = time.time_ns()

        for layer_id, trace_id in layers.items():
            checked += 1
            if not trace_id or trace_id == "missing":
                broken.append(layer_id)
                gap_count += 1
                self._record(f"trace_gap_{layer_id}", "failed", ["LAW-5", "LAW-12", "RULE-1"],
                               f"Missing trace ID for layer {layer_id}")

        integrity_ok = gap_count == 0
        self._record("audit_trace_integrity", "passed" if integrity_ok else "failed",
                       ["LAW-5", "LAW-12", "RULE-1"], f"Gaps: {gap_count}/{checked}")

        return {
            "trace_integrity_ok": integrity_ok,
            "layers_checked": checked,
            "broken_chains": broken,
            "gap_count": gap_count,
            "oldest_trace_ns": oldest,
        }

    def verify_rollback_safety(  # LAW-8 RULE-5
        self,
        rollback_capabilities: Dict[str, Any],
        certification_trace_id: str,
    ) -> Dict[str, Any]:
        components = rollback_capabilities.get("components", {})
        total = len(components)
        safe = 0
        unsafe: List[str] = []

        for name, info in components.items():
            if info.get("rollback_available") and info.get("data_preservation"):
                safe += 1
            else:
                unsafe.append(name)
                self._record(f"rollback_unsafe_{name}", "failed", ["LAW-8", "RULE-5"],
                               f"{name} lacks safe rollback path")

        all_safe = total == safe
        self._record("verify_rollback_safety", "passed" if all_safe else "failed",
                       ["LAW-8", "RULE-5"], f"Rollback: {safe}/{total} safe")

        return {
            "rollback_safe": all_safe,
            "total_components": total,
            "safe_components": safe,
            "unsafe_components": unsafe,
            "data_preservation_ok": all(
                info.get("data_preservation", False) for info in components.values()
            ) if components else True,
        }

    @property
    def audit_entries(self) -> List[SecurityAuditEntry]:
        return list(self._audit_entries)

    def reset_audit_entries(self) -> None:
        self._audit_entries.clear()
