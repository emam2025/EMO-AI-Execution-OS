"""
Reflection Engine — IReflectionEngine implementation.

Analyses failures from traces, generates corrective strategies,
and maintains a reflection log. No execution, no scheduling.
LAW-6 enforced on all public methods.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from releases.cognitive_os.core.interfaces.cognitive.IReflectionEngine import IReflectionEngine
from releases.cognitive_os.core.models.cognitive import ReflectionEntry, ReflectionSeverity


class _FailureAnalyzer:
    """Internal failure pattern analysis."""

    ERROR_PATTERNS = {
        "timeout": {"severity": ReflectionSeverity.HIGH, "category": "resource"},
        "crash": {"severity": ReflectionSeverity.CRITICAL, "category": "stability"},
        "auth": {"severity": ReflectionSeverity.HIGH, "category": "security"},
        "permission": {"severity": ReflectionSeverity.HIGH, "category": "security"},
        "not_found": {"severity": ReflectionSeverity.MEDIUM, "category": "dependency"},
        "connection": {"severity": ReflectionSeverity.MEDIUM, "category": "network"},
        "oom": {"severity": ReflectionSeverity.CRITICAL, "category": "resource"},
        "time_out": {"severity": ReflectionSeverity.HIGH, "category": "resource"},
        "syntax": {"severity": ReflectionSeverity.LOW, "category": "code"},
        "type_error": {"severity": ReflectionSeverity.MEDIUM, "category": "code"},
    }

    @staticmethod
    def detect_severity(outcome: dict) -> ReflectionSeverity:
        errors = outcome.get("errors", [])
        if not errors and not outcome.get("success", True) is False:
            return ReflectionSeverity.LOW
        for e in errors:
            msg = str(e.get("message", "") + " " + e.get("type", "")).lower()
            for pattern, meta in _FailureAnalyzer.ERROR_PATTERNS.items():
                if pattern in msg:
                    return meta["severity"]
        if outcome.get("success") is False and len(outcome.get("steps", [])) > 0:
            return ReflectionSeverity.MEDIUM
        return ReflectionSeverity.LOW

    @staticmethod
    def generate_analysis(outcome: dict) -> Dict[str, Any]:
        errors = outcome.get("errors", [])
        steps = outcome.get("steps", [])
        failed_steps = [s for s in steps if not s.get("success", True)]
        return {
            "error_count": len(errors),
            "total_steps": len(steps),
            "failed_steps": len(failed_steps),
            "success_rate": (len(steps) - len(failed_steps)) / max(len(steps), 1),
            "primary_error": errors[0] if errors else None,
            "failure_patterns": list({e.get("type", "unknown") for e in errors}),
        }

    @staticmethod
    def generate_strategy(analysis: dict, severity: ReflectionSeverity) -> Dict[str, Any]:
        strategies = {
            ReflectionSeverity.CRITICAL: {"action": "halt_and_rollback", "priority": 1},
            ReflectionSeverity.HIGH: {"action": "retry_with_backoff", "priority": 2},
            ReflectionSeverity.MEDIUM: {"action": "log_and_continue", "priority": 3},
            ReflectionSeverity.LOW: {"action": "monitor", "priority": 4},
        }
        base = strategies.get(severity, {"action": "log_and_continue", "priority": 3})
        return {
            **base,
            "corrective_steps": [
                f"verify_{p}" for p in analysis.get("failure_patterns", ["unknown"])
            ],
            "updated_constraints": {"max_retries": 3, "timeout_ms": 30000},
        }


class ReflectionEngine(IReflectionEngine):
    """Analyses failures and generates corrective strategies.

    LAW-6: every public method requires tenant_id.
    """

    def __init__(self) -> None:
        self._reflections: Dict[str, ReflectionEntry] = {}

    def analyze_failure(
        self,
        trace_id: str,
        outcome: Dict[str, Any],
        tenant_id: str,
    ) -> ReflectionEntry:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        severity = _FailureAnalyzer.detect_severity(outcome)
        analysis = _FailureAnalyzer.generate_analysis(outcome)
        strategy = _FailureAnalyzer.generate_strategy(analysis, severity)
        entry = ReflectionEntry(
            reflection_id=f"ref-{uuid.uuid4().hex[:16]}",
            tenant_id=tenant_id,
            source_trace_id=trace_id,
            analysis=analysis,
            strategy_update=strategy,
            severity=severity,
        )
        self._reflections[entry.reflection_id] = entry
        return entry

    def generate_correction(
        self,
        reflection: Dict[str, Any],
        tenant_id: str,
    ) -> Dict[str, Any]:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        return {
            "correction_id": f"corr-{uuid.uuid4().hex[:12]}",
            "timestamp": time.time(),
            "strategy": reflection.get("strategy_update", {}),
            "analysis": reflection.get("analysis", {}),
            "tenant_id": tenant_id,
        }

    def list_reflections(
        self,
        tenant_id: str,
        source_skill_id: str = "",
        limit: int = 20,
    ) -> List[str]:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        results: List[str] = []
        for ref in self._reflections.values():
            if ref.tenant_id != tenant_id:
                continue
            if source_skill_id and ref.source_skill_id != source_skill_id:
                continue
            results.append(ref.reflection_id)
        return results[:limit]

    def get_reflection(
        self,
        reflection_id: str,
        tenant_id: str,
    ) -> ReflectionEntry:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        ref = self._reflections.get(reflection_id)
        if not ref or ref.tenant_id != tenant_id:
            raise KeyError(f"Reflection not found: {reflection_id}")
        return ref
