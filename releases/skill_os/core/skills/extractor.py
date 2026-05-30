"""
Skill Extractor — ISkillExtractor implementation.

Analyses trace data from R2 Bridge and produces SkillDraft instances.
No storage, no runtime side effects. LAW-6 enforced on all public methods.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from releases.skill_os.core.interfaces.skills.ISkillExtractor import ISkillExtractor
from releases.skill_os.core.models.skills import SkillDomain, SkillNode


@dataclass
class SkillDraft:
    """Concrete draft produced by SkillExtractor."""

    skill_name: str
    pattern_hash: str
    confidence_score: float
    tenant_id: str
    project_id: str
    source_trace_id: str
    domain: SkillDomain = SkillDomain.UNKNOWN
    blueprint_steps: List[Dict[str, Any]] = field(default_factory=list)
    tool_sequence: List[str] = field(default_factory=list)
    failure_guardrails: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        if not self.skill_name:
            raise ValueError("skill_name is required")
        if not (0.0 <= self.confidence_score <= 1.0):
            raise ValueError("confidence_score must be in [0.0, 1.0]")


class _TraceParser:
    """Internal parser for R2 trace data."""

    @staticmethod
    def extract_steps(trace: dict) -> List[Dict[str, Any]]:
        return trace.get("steps", trace.get("decisions", []))

    @staticmethod
    def extract_tools(steps: List[Dict[str, Any]]) -> List[str]:
        seen: set = set()
        tools: List[str] = []
        for s in steps:
            t = s.get("tool", "")
            if t and t not in seen:
                seen.add(t)
                tools.append(t)
        return tools

    @staticmethod
    def compute_outcome_success(trace: dict) -> float:
        steps = trace.get("steps", [])
        if not steps:
            return 0.0
        successful = sum(1 for s in steps if s.get("success", False))
        return successful / len(steps)

    @staticmethod
    def compute_trace_quality(trace: dict) -> float:
        score = 0.0
        if trace.get("steps"):
            score += 0.3
        if trace.get("decisions"):
            score += 0.2
        if trace.get("outcome"):
            score += 0.2
        if trace.get("total_tokens", 0) > 100:
            score += 0.15
        if trace.get("agent_id"):
            score += 0.15
        return min(score, 1.0)

    @staticmethod
    def detect_domain(steps: List[Dict[str, Any]]) -> SkillDomain:
        tool_text = " ".join(s.get("tool", "") for s in steps).lower()
        action_text = " ".join(s.get("action", "") for s in steps).lower()
        combined = f"{tool_text} {action_text}"
        if any(k in combined for k in ("kubectl", "deploy", "helm", "terraform", "docker")):
            return SkillDomain.DEPLOYMENT
        if any(k in combined for k in ("pytest", "test", "lint", "debug", "fix", "error")):
            return SkillDomain.DEBUGGING
        if any(k in combined for k in ("write", "commit", "push", "build", "compile", "git")):
            return SkillDomain.CODING
        if any(k in combined for k in ("plan", "design", "review", "approve")):
            return SkillDomain.PLANNING
        return SkillDomain.UNKNOWN

    @staticmethod
    def compute_pattern_hash(skill_name: str, tool_sequence: List[str]) -> str:
        raw = json.dumps({"name": skill_name, "tools": tool_sequence}, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:32]


class SkillExtractor(ISkillExtractor):
    """Extracts skill drafts from R2 trace data.

    LAW-6: every public method requires tenant_id.
    """

    def extract_from_trace(
        self,
        trace_data: dict,
        tenant_id: str,
        project_id: str = "",
    ) -> SkillDraft:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        steps = _TraceParser.extract_steps(trace_data)
        tool_sequence = _TraceParser.extract_tools(steps)
        outcome_success = _TraceParser.compute_outcome_success(trace_data)
        trace_quality = _TraceParser.compute_trace_quality(trace_data)
        confidence = self.calculate_confidence(trace_quality, outcome_success)
        domain = _TraceParser.detect_domain(steps)
        skill_name = self._generate_skill_name(steps, domain)
        pattern_hash = _TraceParser.compute_pattern_hash(skill_name, tool_sequence)
        trace_id = trace_data.get("trace_id", trace_data.get("cognitive_trace_id", f"trace-{uuid.uuid4().hex[:8]}"))
        guardrails = self._extract_guardrails(trace_data)
        return SkillDraft(
            skill_name=skill_name,
            pattern_hash=pattern_hash,
            confidence_score=confidence,
            tenant_id=tenant_id,
            project_id=project_id or trace_data.get("project_id", ""),
            source_trace_id=trace_id,
            domain=domain,
            blueprint_steps=steps,
            tool_sequence=tool_sequence,
            failure_guardrails=guardrails,
        )

    def validate_pattern(self, draft: SkillDraft, tenant_id: str) -> bool:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        if draft.tenant_id != tenant_id:
            return False
        if not draft.skill_name or not draft.pattern_hash:
            return False
        if not (0.0 <= draft.confidence_score <= 1.0):
            return False
        if not draft.blueprint_steps:
            return False
        if draft.tool_sequence and not all(isinstance(t, str) and t for t in draft.tool_sequence):
            return False
        return True

    def list_extractable_traces(
        self,
        traces: List[dict],
        tenant_id: str,
        project_id: str = "",
        min_confidence: float = 0.0,
        limit: int = 20,
    ) -> List[str]:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        eligible: List[str] = []
        for t in traces:
            if t.get("tenant_id", "") != tenant_id:
                continue
            if project_id and t.get("project_id", "") != project_id:
                continue
            quality = _TraceParser.compute_trace_quality(t)
            success = _TraceParser.compute_outcome_success(t)
            confidence = self.calculate_confidence(quality, success)
            if confidence >= min_confidence:
                eligible.append(t.get("trace_id", t.get("cognitive_trace_id", "")))
        return eligible[:limit]

    @staticmethod
    def calculate_confidence(trace_quality: float, outcome_success: float) -> float:
        return max(0.0, min(1.0, outcome_success * 0.7 + trace_quality * 0.3))

    @staticmethod
    def _generate_skill_name(steps: List[Dict[str, Any]], domain: SkillDomain) -> str:
        if not steps:
            return f"skill-{uuid.uuid4().hex[:8]}"
        actions = [s.get("action", s.get("decision", "")).lower() for s in steps if s.get("action") or s.get("decision")]
        tools = list({s.get("tool", "") for s in steps if s.get("tool")})
        if actions and tools:
            return f"{'-'.join(actions[:3])}-with-{'-'.join(tools[:2])}"
        if tools:
            return f"use-{'-'.join(tools[:3])}"
        return f"skill-{uuid.uuid4().hex[:8]}"

    @staticmethod
    def _extract_guardrails(trace: dict) -> List[str]:
        guardrails: List[str] = []
        steps = trace.get("steps", [])
        for s in steps:
            if not s.get("success", True):
                guardrails.append(f"handle_{s.get('action', 'unknown')}_failure")
        errors = trace.get("errors", [])
        for e in errors:
            guardrails.append(f"guard_against_{e.get('type', 'error')}")
        trace.get("failure_guardrails", guardrails)  # passthrough
        return list(set(guardrails))
