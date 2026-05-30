from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List


@dataclass
class CanonRule:
    id: str
    description: str
    severity: str
    evaluate: Callable[..., bool]
    message: str


@dataclass
class CanonViolation:
    rule_id: str
    message: str
    severity: str  # LOW | MEDIUM | HIGH | CRITICAL
    context: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"[{self.severity}] {self.rule_id}: {self.message}"


@dataclass
class CanonValidationResult:
    allowed: bool
    violations: List[CanonViolation] = field(default_factory=list)
    severity: str = "LOW"

    @property
    def block(self) -> bool:
        return not self.allowed
