"""CanonValidator — runtime enforcement engine for Canon laws."""

from typing import Dict, List, Optional

from core.canon.context import ValidationContext
from core.canon.default_rules import DEFAULT_RULES
from core.canon.result import CanonRule, CanonValidationResult, CanonViolation

SEVERITY_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


class CanonValidator:
    """Core enforcement engine.

    Evaluates all registered Canon rules against a ValidationContext
    and returns a CanonValidationResult with block/no-block decision.
    """

    def __init__(self, rules: Optional[List[CanonRule]] = None) -> None:
        self._rules = rules or list(DEFAULT_RULES)

    def validate(self, context: ValidationContext) -> CanonValidationResult:
        violations: List[CanonViolation] = []
        for rule in self._rules:
            try:
                result = rule.evaluate(context)
                if not result:
                    violations.append(CanonViolation(
                        rule_id=rule.id,
                        message=rule.message,
                        severity=rule.severity,
                        context={"file": context.file_path or "unknown"},
                    ))
            except Exception as e:
                violations.append(CanonViolation(
                    rule_id=rule.id,
                    message=f"Rule execution error: {e}",
                    severity="CRITICAL",
                    context={"error": str(e)},
                ))

        if not violations:
            return CanonValidationResult(allowed=True, severity="LOW")

        max_severity = max(
            (SEVERITY_ORDER.get(v.severity, 0) for v in violations),
            default=0,
        )
        severity_label = {0: "LOW", 1: "MEDIUM", 2: "HIGH", 3: "CRITICAL"}.get(
            max_severity, "CRITICAL"
        )
        allowed = max_severity < 2  # Allow only LOW and MEDIUM violations

        return CanonValidationResult(
            allowed=allowed,
            violations=violations,
            severity=severity_label,
        )
