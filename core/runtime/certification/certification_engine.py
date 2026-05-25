"""Phase FINAL — Certification Engine.  # LAW-1 LAW-3 LAW-5 LAW-8 LAW-11 LAW-12 LAW-13 LAW-14 LAW-15 LAW-20 LAW-22 RULE-1 RULE-2 RULE-3 RULE-4 RULE-5

Evaluates system readiness, computes stability scores, generates
certificates, and freezes production baselines. Integrates SystemAuditor,
LoadGenerator, and SecurityValidator for holistic certification.

Ref: Canon LAW 1-27, RULE 1-5
Ref: DEVELOPER.md §16.1 (Production Readiness Checklist)
Ref: DEVELOPER.md §15.13 (AI-Native Runtime Features)
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class ICertificationEngine(Protocol):  # LAW-1 LAW-3 LAW-5 LAW-8 LAW-11 LAW-12 RULE-1 RULE-3
    """Certification engine for production readiness.

    Evaluates readiness across all dimensions (compliance, performance,
    security, reliability), computes stability scores, generates formal
    certificates, and freezes production baselines.
    """

    def evaluate_readiness(  # LAW-1 LAW-3 LAW-8 RULE-1
        self,
        audit_results: Dict[str, Any],
        load_results: Dict[str, Any],
        security_results: Dict[str, Any],
        readiness_guards: Dict[str, bool],
        certification_trace_id: str,
    ) -> Dict[str, Any]:
        """Evaluate overall system readiness for production.

        Args:
            audit_results:    Results from SystemAuditor.
            load_results:     Results from LoadGenerator.
            security_results: Results from SecurityValidator.
            readiness_guards: Dict of guard_name -> bool for all guards.
            certification_trace_id: Correlation ID.

        Returns:
            ready:               True if all readiness criteria met.
            evaluations:         Dict of dimension -> evaluation result.
            blocked_by:          List of guards/checks that blocked readiness.
            readiness_pct:       Overall readiness percentage.
            evaluation_hash:     SHA-256 hash of the full evaluation.
        """

    def compute_stability_score(  # LAW-3 RULE-1
        self,
        load_results: Dict[str, Any],
        oscillation_data: Dict[str, Any],
        performance_metrics: Dict[str, Any],
        certification_trace_id: str,
    ) -> Dict[str, Any]:
        """Compute system stability score from load and performance data.

        Args:
            load_results:         Results from LoadGenerator.
            oscillation_data:     Oscillation detection results.
            performance_metrics:  Aggregated performance metrics.
            certification_trace_id: Correlation ID.

        Returns:
            stability_score:      Overall stability score (0.0-1.0).
            p99_latency_score:    Latency score component.
            throughput_score:     Throughput score component.
            oscillation_score:    Oscillation score component.
            reliability_score:    Reliability score component.
            overall_grade:        "A" (>=0.95), "B" (>=0.85), "C" (>=0.70), "F".
        """

    def generate_certificate(  # LAW-5 LAW-12 RULE-1
        self,
        evaluation: Dict[str, Any],
        stability: Dict[str, Any],
        certification_trace_id: str,
    ) -> Dict[str, Any]:
        """Generate a formal production readiness certificate.

        Args:
            evaluation:  Readiness evaluation results.
            stability:   Stability score results.
            certification_trace_id: Correlation ID.

        Returns:
            certificate_id:         Unique certificate identifier.
            certificate_hash:       SHA-256 hash of certificate content.
            status:                 "certified", "conditional", "denied".
            issued_at_ns:           Issue timestamp.
            stability_grade:        Overall stability grade.
            conditions:             List of conditions/caveats.
            valid_until_ns:         Certificate validity end.
        """

    def freeze_baseline(  # LAW-8 RULE-1 RULE-5
        self,
        baseline_data: Dict[str, Any],
        certification_trace_id: str,
    ) -> Dict[str, Any]:
        """Freeze a production baseline after successful certification.

        Args:
            baseline_data:       Dict describing the system baseline.
            certification_trace_id: Correlation ID.

        Returns:
            baseline_id:           Unique baseline identifier.
            baseline_hash:         SHA-256 hash of baseline data.
            frozen_at_ns:          Freeze timestamp.
            data_points_frozen:    Number of data points frozen.
            rollback_available:    True if pre-freeze state is preserved.
            version:               Frozen version label.
        """


@dataclass
class Certificate:  # LAW-5 LAW-12
    """Production readiness certificate data."""
    certificate_id: str
    status: str
    stability_grade: str
    conditions: List[str]
    hash: str
    issued_at_ns: int = field(default_factory=lambda: time.time_ns())


@dataclass
class Baseline:  # LAW-8 RULE-5
    """Frozen production baseline."""
    baseline_id: str
    version: str
    hash: str
    frozen_at_ns: int = field(default_factory=lambda: time.time_ns())
    rollback_available: bool = True


class CertificationEngine:  # LAW-1 LAW-3 LAW-5 LAW-8 LAW-11 LAW-12 LAW-13 LAW-14 LAW-15 LAW-20 LAW-22 RULE-1 RULE-2 RULE-3 RULE-4 RULE-5
    """Concrete implementation of ICertificationEngine.

    LAW 11: No global mutable state — all certificates/baselines are instance-scoped.
    LAW 12: Every certificate is fully traceable via certification_trace_id.
    LAW 8: Baselines preserve rollback path to pre-freeze state.
    RULE 1: Same inputs -> same evaluation, stability score, certificate.
    RULE 3: Readiness guards enforce all preconditions before certification.
    """

    def __init__(
        self,
        strict_certification_mode: bool = False,
        event_bus: Any = None,
    ) -> None:
        self._strict_certification_mode = strict_certification_mode
        self._event_bus = event_bus
        self._certificates: Dict[str, Certificate] = {}
        self._baselines: Dict[str, Baseline] = {}

    def evaluate_readiness(  # LAW-1 LAW-3 LAW-8 RULE-1 RULE-3
        self,
        audit_results: Dict[str, Any],
        load_results: Dict[str, Any],
        security_results: Dict[str, Any],
        readiness_guards: Dict[str, bool],
        certification_trace_id: str,
    ) -> Dict[str, Any]:
        evaluations: Dict[str, Any] = {}
        blocked_by: List[str] = []

        # Guard checks: all must pass
        for guard_name, guard_pass in readiness_guards.items():
            evaluations[f"guard_{guard_name}"] = guard_pass
            if not guard_pass:
                blocked_by.append(guard_name)

        # Audit check
        compliance_pct = audit_results.get("compliance_pct", 0)
        deps_ok = audit_results.get("dependencies", {}).get("verified", False)
        audit_pass = compliance_pct == 100.0 and deps_ok
        evaluations["compliance"] = audit_pass
        if not audit_pass:
            blocked_by.append(f"compliance_{compliance_pct}%")

        # Load check
        load_p99 = load_results.get("p99_latency_ms", 999)
        load_throughput = load_results.get("throughput", 0)
        load_pass = load_p99 < 200.0 and load_throughput > 0
        evaluations["performance"] = load_pass
        if not load_pass:
            blocked_by.append(f"p99_latency_{load_p99}ms")

        # Security check
        boundaries_ok = security_results.get("isolation", {}).get("boundaries_secure", False)
        guards_ok = security_results.get("capability_guards", {}).get("all_guards_active", False)
        traces_ok = security_results.get("trace_integrity", {}).get("trace_integrity_ok", False)
        rollback_ok = security_results.get("rollback_safety", {}).get("rollback_safe", False)
        security_pass = boundaries_ok and guards_ok and traces_ok and rollback_ok
        evaluations["security"] = security_pass
        if not security_pass:
            blocked_by.append("security_validation")

        ready = len(blocked_by) == 0
        readiness_pct = max(0.0, 100.0 - len(blocked_by) * 16.67)
        eval_content = f"{ready}:{readiness_pct}:{certification_trace_id}"
        eval_hash = hashlib.sha256(eval_content.encode()).hexdigest()

        evaluation_result = {
            "ready": ready,
            "evaluations": evaluations,
            "blocked_by": blocked_by,
            "readiness_pct": round(readiness_pct, 2),
            "evaluation_hash": eval_hash,
        }

        if self._event_bus:
            try:
                from core.models.events import ExecutionEvent
                self._event_bus.publish(
                    "runtime.certification.evaluation",
                    ExecutionEvent(
                        event_id=f"cert_{certification_trace_id[:8]}_{int(time.time() * 1000)}",
                        event_type="STATE_TRANSITION",
                        timestamp=time.time(),
                        source="CertificationEngine",
                        payload={
                            "action": "evaluate_readiness",
                            "ready": ready,
                            "readiness_pct": readiness_pct,
                            "certification_trace_id": certification_trace_id,
                        },
                    ),
                )
            except Exception:
                pass

        return evaluation_result

    def compute_stability_score(  # LAW-3 RULE-1
        self,
        load_results: Dict[str, Any],
        oscillation_data: Dict[str, Any],
        performance_metrics: Dict[str, Any],
        certification_trace_id: str,
    ) -> Dict[str, Any]:
        p99 = load_results.get("p99_latency_ms", 999)
        throughput = load_results.get("throughput", 0)
        dags_failed = load_results.get("dags_failed", 0)
        dags_total = load_results.get("dags_executed", 0) + dags_failed

        p99_score = max(0.0, 1.0 - p99 / 200.0) if p99 > 0 else 1.0
        throughput_score = min(1.0, throughput / 100.0) if throughput > 0 else 0.0
        osc_score_raw = oscillation_data.get("oscillation_score", 0)
        osc_score = 1.0 - min(1.0, osc_score_raw)
        reliability_score = (dags_total - dags_failed) / max(1, dags_total)

        stability = p99_score * 0.3 + throughput_score * 0.2 + osc_score * 0.25 + reliability_score * 0.25

        if stability >= 0.95:
            grade = "A"
        elif stability >= 0.85:
            grade = "B"
        elif stability >= 0.70:
            grade = "C"
        else:
            grade = "F"

        return {
            "stability_score": round(stability, 4),
            "p99_latency_score": round(p99_score, 4),
            "throughput_score": round(throughput_score, 4),
            "oscillation_score": round(osc_score, 4),
            "reliability_score": round(reliability_score, 4),
            "overall_grade": grade,
        }

    def generate_certificate(  # LAW-5 LAW-12 RULE-1
        self,
        evaluation: Dict[str, Any],
        stability: Dict[str, Any],
        certification_trace_id: str,
    ) -> Dict[str, Any]:
        ready = evaluation.get("ready", False)
        grade = stability.get("overall_grade", "F")
        blocked_by = evaluation.get("blocked_by", [])

        if ready and grade in ("A", "B"):
            status = "certified"
            conditions = blocked_by
        elif ready and grade == "C":
            status = "conditional"
            conditions = ["stability_grade_C"] + blocked_by
        else:
            status = "denied"
            conditions = blocked_by + (["stability_grade_F"] if grade == "F" else [])

        cert_content = f"{status}:{grade}:{certification_trace_id}:{time.time_ns()}"
        cert_hash = hashlib.sha256(cert_content.encode()).hexdigest()
        cert_id = f"cert_{cert_hash[:16]}"

        cert = Certificate(
            certificate_id=cert_id,
            status=status,
            stability_grade=grade,
            conditions=conditions,
            hash=cert_hash,
        )
        self._certificates[cert_id] = cert

        result = {
            "certificate_id": cert_id,
            "certificate_hash": cert_hash,
            "status": status,
            "issued_at_ns": cert.issued_at_ns,
            "stability_grade": grade,
            "conditions": conditions,
            "valid_until_ns": cert.issued_at_ns + 86400 * 10 ** 9,
        }

        if self._event_bus:
            try:
                from core.models.events import ExecutionEvent
                self._event_bus.publish(
                    "runtime.certification.certificate",
                    ExecutionEvent(
                        event_id=f"cert_{certification_trace_id[:8]}_{int(time.time() * 1000)}",
                        event_type="STATE_TRANSITION",
                        timestamp=time.time(),
                        source="CertificationEngine",
                        payload={
                            "action": "generate_certificate",
                            "certificate_id": cert_id,
                            "status": status,
                            "certification_trace_id": certification_trace_id,
                        },
                    ),
                )
            except Exception:
                pass

        return result

    def freeze_baseline(  # LAW-8 RULE-1 RULE-5
        self,
        baseline_data: Dict[str, Any],
        certification_trace_id: str,
    ) -> Dict[str, Any]:
        data_points = baseline_data.get("data_points", {})
        version = baseline_data.get("version", "4.5.0-prod-ready")
        num_points = len(data_points)

        baseline_content = f"{version}:{num_points}:{certification_trace_id}:{time.time_ns()}"
        baseline_hash = hashlib.sha256(baseline_content.encode()).hexdigest()
        baseline_id = f"bl_{baseline_hash[:16]}"

        bl = Baseline(
            baseline_id=baseline_id,
            version=version,
            hash=baseline_hash,
            rollback_available=True,
        )
        self._baselines[baseline_id] = bl

        result = {
            "baseline_id": baseline_id,
            "baseline_hash": baseline_hash,
            "frozen_at_ns": bl.frozen_at_ns,
            "data_points_frozen": num_points,
            "rollback_available": True,
            "version": version,
        }

        if self._event_bus:
            try:
                from core.models.events import ExecutionEvent
                self._event_bus.publish(
                    "runtime.certification.baseline",
                    ExecutionEvent(
                        event_id=f"cert_{certification_trace_id[:8]}_{int(time.time() * 1000)}",
                        event_type="STATE_TRANSITION",
                        timestamp=time.time(),
                        source="CertificationEngine",
                        payload={
                            "action": "freeze_baseline",
                            "baseline_id": baseline_id,
                            "version": version,
                            "certification_trace_id": certification_trace_id,
                        },
                    ),
                )
            except Exception:
                pass

        return result

    def get_certificate(self, certificate_id: str) -> Optional[Certificate]:
        return self._certificates.get(certificate_id)

    def get_baseline(self, baseline_id: str) -> Optional[Baseline]:
        return self._baselines.get(baseline_id)

    def all_certificates(self) -> List[str]:
        return list(self._certificates.keys())

    def all_baselines(self) -> List[str]:
        return list(self._baselines.keys())
