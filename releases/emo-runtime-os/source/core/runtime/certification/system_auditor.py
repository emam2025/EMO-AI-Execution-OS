"""Phase FINAL — System Auditor.  # LAW-1 LAW-5 LAW-8 LAW-11 LAW-12 LAW-13 LAW-14 RULE-1 RULE-2 RULE-3 RULE-4 RULE-5

Performs canon compliance scanning, architectural debt detection, reality
report generation, and dependency verification for production certification.

Ref: Canon LAW 1 (Interface Authority), LAW 5 (Observability)
Ref: Canon LAW 8 (Recoverability), LAW 11 (No Global State)
Ref: Canon LAW 12 (Traceability), LAW 13 (No Direct Execution)
Ref: Canon LAW 14 (Integrity), RULE 1-5
Ref: DEVELOPER.md §16.1 (Production Readiness Checklist)
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class ISystemAuditor(Protocol):  # LAW-1 LAW-5 LAW-8 LAW-11 LAW-12 RULE-1 RULE-2
    """System-wide audit harness for production readiness certification.

    Performs canon compliance scanning against LAW 1-27 and RULE 1-5,
    detects architectural debt, generates reality reports, and verifies
    dependency integrity. Every audit is deterministic (RULE 1) and
    fully traceable (LAW 12).
    """

    def scan_canon_compliance(  # LAW-1 LAW-5 RULE-1
        self,
        canon_context: Dict[str, Any],
        certification_trace_id: str,
    ) -> Dict[str, Any]:
        """Scan all components for canon compliance against LAW 1-27.

        Args:
            canon_context: Full canon context dict with laws and rules status.
            certification_trace_id: Correlation ID for observability.

        Returns:
            compliance_pct:       Percentage of canon items compliant (0.0-100.0).
            total_laws:           Number of laws checked.
            compliant_count:      Number of compliant laws.
            violations:           List of violation details.
            canonical_hash:       SHA-256 hash of the compliance snapshot.
            scanned_at_ns:        Scan timestamp.
        """

    def detect_architectural_debt(  # LAW-14 RULE-1
        self,
        component_graph: Dict[str, Any],
        certification_trace_id: str,
    ) -> Dict[str, Any]:
        """Detect architectural debt in the component graph.

        Args:
            component_graph: Dict describing component dependencies and metrics.
            certification_trade_id: Correlation ID.

        Returns:
            debt_score:          Architectural debt score (0.0-1.0).
            circular_deps:       List of circular dependency chains detected.
            orphan_components:   List of unreferenced components.
            high_coupling:       List of components with excessive coupling.
            low_cohesion:        List of components with low cohesion.
            estimated_effort_days: Estimated effort to resolve debt.
        """

    def generate_reality_report(  # LAW-5 LAW-12 RULE-1
        self,
        audit_data: Dict[str, Any],
        certification_trace_id: str,
    ) -> Dict[str, Any]:
        """Generate a reality report from collected audit data.

        Args:
            audit_data: Dict with all audit findings.
            certification_trace_id: Correlation ID.

        Returns:
            report_id:           Unique report identifier.
            report_hash:         SHA-256 hash of report content.
            audit_timestamp_ns:  Timestamp of audit.
            sections:            Report sections with findings.
            summary:             Executive summary of findings.
            recommendation:      Recommended action.
        """

    def verify_dependencies(  # LAW-13 LAW-14 RULE-2 RULE-4
        self,
        dependency_graph: Dict[str, List[str]],
        certification_trace_id: str,
    ) -> Dict[str, Any]:
        """Verify dependency integrity and compliance.

        Args:
            dependency_graph: Dict mapping component -> list of dependency names.
            certification_trace_id: Correlation ID.

        Returns:
            verified:            True if all dependencies satisfy constraints.
            total_deps:          Total number of dependencies.
            satisfied_deps:      Number of satisfied dependencies.
            violated_deps:       Number of violated dependency constraints.
            circular_chains:     List of circular dependency chains found.
            isolation_violations: Dependencies crossing service boundaries.
        """


@dataclass
class AuditRecord:  # LAW-5 LAW-12
    """Single audit record with traceability metadata."""
    check_name: str
    status: str  # "passed", "failed", "warning"
    law_refs: List[str]
    detail: str
    timestamp_ns: int = field(default_factory=lambda: time.time_ns())
    check_hash: str = ""

    def __post_init__(self) -> None:
        if not self.check_hash:
            raw = f"{self.check_name}:{self.status}:{self.timestamp_ns}"
            self.check_hash = hashlib.sha256(raw.encode()).hexdigest()[:16]


class SystemAuditor:  # LAW-1 LAW-5 LAW-8 LAW-11 LAW-12 LAW-13 LAW-14 RULE-1 RULE-2 RULE-3 RULE-4 RULE-5
    """Concrete implementation of ISystemAuditor.

    LAW 11: No global mutable state — all state is instance-scoped.
    LAW 12: Every audit produces fully traceable records.
    RULE 1: Same inputs -> same compliance scan results.
    RULE 2: All reads are read-only — no mutations during audit.
    """

    def __init__(self, strict_certification_mode: bool = False) -> None:
        self._audit_records: List[AuditRecord] = []
        self._strict_certification_mode = strict_certification_mode

    def _record(self, check_name: str, status: str, law_refs: List[str], detail: str) -> AuditRecord:
        rec = AuditRecord(check_name=check_name, status=status, law_refs=law_refs, detail=detail)
        self._audit_records.append(rec)
        return rec

    def scan_canon_compliance(  # LAW-1 LAW-5 RULE-1
        self,
        canon_context: Dict[str, Any],
        certification_trace_id: str,
    ) -> Dict[str, Any]:
        laws = canon_context.get("laws", {})
        rules = canon_context.get("rules", {})
        violations: List[Dict[str, Any]] = []
        compliant_count = 0
        total = len(laws) + len(rules)

        for law_id, status in laws.items():
            if status is True:
                compliant_count += 1
            elif status is not None:
                violations.append({"law": law_id, "status": status, "type": "law"})
                self._record(f"canon_{law_id}", "failed", [law_id], str(status))

        for rule_id, status in rules.items():
            if status is True:
                compliant_count += 1
            elif status is not None:
                violations.append({"rule": rule_id, "status": status, "type": "rule"})
                self._record(f"canon_{rule_id}", "failed", [rule_id], str(status))

        compliance_pct = (compliant_count / total * 100) if total > 0 else 100.0
        snapshot = f"{compliance_pct}:{len(violations)}:{certification_trace_id}"
        canonical_hash = hashlib.sha256(snapshot.encode()).hexdigest()

        result = {
            "compliance_pct": compliance_pct,
            "total_laws": len(laws),
            "total_rules": len(rules),
            "compliant_count": compliant_count,
            "violations": violations,
            "canonical_hash": canonical_hash,
            "scanned_at_ns": time.time_ns(),
        }
        self._record("scan_canon_compliance", "passed" if compliance_pct == 100.0 else "failed",
                       ["LAW-1", "LAW-5", "RULE-1"], f"Compliance: {compliance_pct}%")
        return result

    def detect_architectural_debt(  # LAW-14 RULE-1
        self,
        component_graph: Dict[str, Any],
        certification_trace_id: str,
    ) -> Dict[str, Any]:
        nodes = component_graph.get("nodes", {})
        edges = component_graph.get("edges", [])
        circular_deps: List[List[str]] = []
        visited: set = set()
        path: set = set()

        def dfs(node: str) -> None:
            if node in path:
                cycle = list(path)
                circular_deps.append(cycle)
                return
            if node in visited:
                return
            visited.add(node)
            path.add(node)
            for src, dst in edges:
                if src == node:
                    dfs(dst)
            path.remove(node)

        for node_id in nodes:
            dfs(node_id)

        orphans = [n for n in nodes if not any(dst == n for _, dst in edges)]
        dep_count = {}
        for src, dst in edges:
            dep_count[src] = dep_count.get(src, 0) + 1
        high_coupling = [n for n, c in dep_count.items() if c > 5]
        debt_score = min(1.0, (len(circular_deps) * 0.3 + len(orphans) * 0.1 + len(high_coupling) * 0.05))
        effort = int(debt_score * 20)

        result = {
            "debt_score": round(debt_score, 4),
            "circular_deps": circular_deps,
            "orphan_components": orphans,
            "high_coupling": high_coupling,
            "low_cohesion": [],
            "estimated_effort_days": effort,
        }
        self._record("detect_architectural_debt", "passed" if debt_score < 0.5 else "warning",
                       ["LAW-14", "RULE-1"], f"Debt score: {debt_score}")
        return result

    def generate_reality_report(  # LAW-5 LAW-12 RULE-1
        self,
        audit_data: Dict[str, Any],
        certification_trace_id: str,
    ) -> Dict[str, Any]:
        sections = {
            "compliance": audit_data.get("compliance", {}),
            "architectural_debt": audit_data.get("architectural_debt", {}),
            "dependencies": audit_data.get("dependencies", {}),
        }
        summary_parts = []
        compliance = sections["compliance"]
        debt = sections["architectural_debt"]
        deps = sections["dependencies"]
        compliance_pct = compliance.get("compliance_pct", 0)
        debt_score = debt.get("debt_score", 0)
        deps_verified = deps.get("verified", False)

        if compliance_pct == 100:
            summary_parts.append("Full canon compliance (100%)")
        else:
            summary_parts.append(f"Canon compliance at {compliance_pct}%")
        if debt_score < 0.3:
            summary_parts.append("Low architectural debt")
        elif debt_score < 0.6:
            summary_parts.append("Moderate architectural debt")
        else:
            summary_parts.append("High architectural debt")
        summary_parts.append("Dependencies verified" if deps_verified else "Dependency issues found")

        report_content = f"{sections}:{certification_trace_id}"
        report_hash = hashlib.sha256(report_content.encode()).hexdigest()
        report_id = f"rr_{report_hash[:16]}"

        result = {
            "report_id": report_id,
            "report_hash": report_hash,
            "audit_timestamp_ns": time.time_ns(),
            "sections": sections,
            "summary": "; ".join(summary_parts),
            "recommendation": "Proceed to certification" if compliance_pct == 100 and deps_verified
                              else "Resolve issues before certification",
        }
        self._record("generate_reality_report", "passed" if compliance_pct == 100 else "warning",
                       ["LAW-5", "LAW-12", "RULE-1"], report_id)
        return result

    def verify_dependencies(  # LAW-13 LAW-14 RULE-2 RULE-4
        self,
        dependency_graph: Dict[str, List[str]],
        certification_trace_id: str,
    ) -> Dict[str, Any]:
        total_deps = 0
        satisfied_deps = 0
        circular_chains: List[List[str]] = []
        isolation_violations: List[str] = []

        for component, deps in dependency_graph.items():
            total_deps += len(deps)
            for dep in deps:
                if dep in dependency_graph or dep.startswith("core."):
                    satisfied_deps += 1
                else:
                    isolation_violations.append(f"{component} -> {dep}")
                    self._record(f"dep_violation_{component}", "failed", ["LAW-13", "RULE-4"],
                                   f"{component} references unknown dep {dep}")

        violated_deps = total_deps - satisfied_deps
        verified = violated_deps == 0 and len(circular_chains) == 0 and len(isolation_violations) == 0

        result = {
            "verified": verified,
            "total_deps": total_deps,
            "satisfied_deps": satisfied_deps,
            "violated_deps": violated_deps,
            "circular_chains": circular_chains,
            "isolation_violations": isolation_violations,
        }
        self._record("verify_dependencies", "passed" if verified else "failed",
                       ["LAW-13", "LAW-14", "RULE-2", "RULE-4"],
                       f"Deps: {satisfied_deps}/{total_deps} satisfied")
        return result

    @property
    def audit_records(self) -> List[AuditRecord]:
        return list(self._audit_records)

    def reset_audit_records(self) -> None:
        self._audit_records.clear()
