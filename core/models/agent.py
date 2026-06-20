"""Agent OS — Domain Models.

Pure data structures (stdlib only, zero internal imports).

Ref: LAW 6 (Shared Models MUST NOT live inside runtime engines)
Ref: LAW 11 (No Global State)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


# ── Enums ─────────────────────────────────────────────────────────────────────


class AgentStatus(Enum):
    """Agent lifecycle states."""

    CREATED = "created"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"


class AutonomyLevel(Enum):
    """Agent autonomy levels (L0-L4).

    Ref: Human Governance (RC16.7-C)
    """

    L0_OBSERVE = "observe"
    L1_RECOMMEND = "recommend"
    L2_EXECUTE_WITH_APPROVAL = "execute_with_approval"
    L3_LIMITED_AUTONOMOUS = "limited_autonomous"
    L4_DOMAIN_AUTONOMOUS = "domain_autonomous"


class MemoryType(Enum):
    """Memory types."""

    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
    EPISODIC = "episodic"


# ── Dataclasses ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AgentIdentity:
    """Immutable agent identity.

    Integrated with ResourceManager (ResourceType.AGENT).
    """

    id: str
    tenant_id: str
    org_id: Optional[str]
    name: str
    agent_type: str
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    version: str = "1.0.0"
    capabilities: List[str] = field(default_factory=list)
    trust_level: float = 0.5


@dataclass
class AgentMemory:
    """Agent memory (short-term, long-term, episodic)."""

    short_term: Dict[str, Any] = field(default_factory=dict)
    long_term: Dict[str, Any] = field(default_factory=dict)
    episodic: List[Dict[str, Any]] = field(default_factory=list)
    max_short_term_size: int = 100
    max_long_term_size: int = 10000
    max_episodic_size: int = 1000

    def store_short_term(self, key: str, value: Any) -> None:
        if len(self.short_term) >= self.max_short_term_size:
            oldest_key = next(iter(self.short_term))
            del self.short_term[oldest_key]
        self.short_term[key] = value

    def store_long_term(self, key: str, value: Any) -> None:
        if len(self.long_term) >= self.max_long_term_size:
            raise MemoryError("Long-term memory full")
        self.long_term[key] = value

    def store_episodic(self, episode: Dict[str, Any]) -> None:
        if len(self.episodic) >= self.max_episodic_size:
            self.episodic.pop(0)
        self.episodic.append(episode)


@dataclass
class AgentSkills:
    """Registered skills and learned patterns."""

    registered_tools: List[str] = field(default_factory=list)
    learned_patterns: Dict[str, Any] = field(default_factory=dict)
    success_rate_by_skill: Dict[str, float] = field(default_factory=dict)
    usage_count_by_skill: Dict[str, int] = field(default_factory=dict)

    def register_tool(self, tool_name: str) -> None:
        if tool_name not in self.registered_tools:
            self.registered_tools.append(tool_name)

    def record_success(self, skill_name: str) -> None:
        self.usage_count_by_skill[skill_name] = (
            self.usage_count_by_skill.get(skill_name, 0) + 1
        )
        current = self.success_rate_by_skill.get(skill_name, 0.5)
        self.success_rate_by_skill[skill_name] = current * 0.9 + 0.1

    def record_failure(self, skill_name: str) -> None:
        self.usage_count_by_skill[skill_name] = (
            self.usage_count_by_skill.get(skill_name, 0) + 1
        )
        current = self.success_rate_by_skill.get(skill_name, 0.5)
        self.success_rate_by_skill[skill_name] = current * 0.9


@dataclass
class AgentPermissions:
    """RBAC permissions (integrated with PolicyManager)."""

    allowed_actions: List[str] = field(default_factory=list)
    denied_actions: List[str] = field(default_factory=list)
    resource_limits: Dict[str, int] = field(default_factory=dict)
    requires_approval_for: List[str] = field(default_factory=list)

    def can_perform(self, action: str) -> bool:
        if action in self.denied_actions:
            return False
        if self.allowed_actions and action not in self.allowed_actions:
            return False
        return True

    def requires_approval(self, action: str) -> bool:
        return action in self.requires_approval_for


@dataclass
class AgentRisk:
    """Current risk level and autonomy mode (L0-L4)."""

    autonomy_level: AutonomyLevel = AutonomyLevel.L1_RECOMMEND
    risk_score: float = 0.0
    last_risk_assessment: Optional[str] = None
    risk_factors: List[str] = field(default_factory=list)

    def assess_risk(self, action: str, context: Dict[str, Any]) -> float:
        """Assess risk for an action. Returns 0.0-1.0."""
        base_risk = 0.1
        if action in ["delete", "terminate", "modify_production"]:
            base_risk = 0.8
        elif action in ["create", "update"]:
            base_risk = 0.3
        self.risk_score = base_risk
        self.last_risk_assessment = datetime.now(timezone.utc).isoformat()
        return self.risk_score


@dataclass
class AgentCost:
    """Token usage, compute tracking, billing."""

    tokens_used: int = 0
    compute_seconds: float = 0.0
    api_calls: int = 0
    estimated_cost_usd: float = 0.0
    budget_limit_usd: Optional[float] = None

    def record_usage(
        self, tokens: int, compute_seconds: float, api_calls: int = 0
    ) -> None:
        self.tokens_used += tokens
        self.compute_seconds += compute_seconds
        self.api_calls += api_calls
        self.estimated_cost_usd += (tokens / 1000) * 0.002

    def is_over_budget(self) -> bool:
        if self.budget_limit_usd is None:
            return False
        return self.estimated_cost_usd > self.budget_limit_usd


@dataclass
class AgentAudit:
    """Action log, decision traces."""

    action_log: List[Dict[str, Any]] = field(default_factory=list)
    decision_traces: List[Dict[str, Any]] = field(default_factory=list)
    max_log_size: int = 10000

    def record_action(
        self, action: str, context: Dict[str, Any], result: Dict[str, Any]
    ) -> str:
        """Record an action. Returns audit_id."""
        audit_id = f"audit_{len(self.action_log)}"
        entry = {
            "audit_id": audit_id,
            "action": action,
            "context": context,
            "result": result,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if len(self.action_log) >= self.max_log_size:
            self.action_log.pop(0)
        self.action_log.append(entry)
        return audit_id

    def record_decision(
        self, decision: str, reasoning: str, outcome: str
    ) -> None:
        """Record a decision trace."""
        trace = {
            "decision": decision,
            "reasoning": reasoning,
            "outcome": outcome,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.decision_traces.append(trace)
