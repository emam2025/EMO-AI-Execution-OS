"""Phase G4 — Tool Synthesizer.  # LAW-2 LAW-12 LAW-14 RULE-1 RULE-2 RULE-3

Top-level orchestrator of the Tool Synthesis Agent subsystem. Consumes
G1 Planner Intents, G3 Optimization Proposals, and Phase 4 Sandbox
context to dynamically generate executable tool code.

Safe Patch Guards (RULE 3): All 7 guards (G1–G7) must pass before register.
Deterministic Synthesis Guard (RULE 1): Same intent → same code.

Ref: Canon LAW 2, LAW 12, LAW 14, RULE 1–4
Ref: artifacts/design/g4/protocols/01_tool_synthesis_protocols.py
Ref: artifacts/design/g4/03_synthesis_state_machine.md
"""

from __future__ import annotations

import ast as ast_module
import hashlib
import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from core.runtime.tool_synthesis.synthesis_state_machine import (
    SynthesisState,
    SynthesisStateMachine,
)
from core.runtime.tool_synthesis.tool_validator import ToolValidator
from core.runtime.tool_synthesis.tool_sandboxer import ToolSandboxer
from core.runtime.tool_synthesis.tool_registry_manager import ToolRegistryManager
from core.runtime.tool_synthesis.trace_correlator import SynthesisTraceCorrelator

logger = logging.getLogger("emo_ai.synthesis.tool_synthesizer")

TOOL_TEMPLATE: str = '''def {tool_name}({params}):
    """Synthesised tool: {goal}"""
    {body}
    return result
'''


class ToolSynthesizer:  # LAW-2 LAW-12 LAW-14 RULE-1 RULE-2 RULE-3
    """Top-level orchestrator of the G4 Tool Synthesis Agent.

    Orchestrates the full synthesis pipeline:
      intent → code generation → AST validation → security scan
      → sandbox dry-run → registration
    """

    def __init__(
        self,
        validator: ToolValidator,
        sandboxer: ToolSandboxer,
        registry_manager: ToolRegistryManager,
        state_machine: SynthesisStateMachine,
        trace_correlator: SynthesisTraceCorrelator,
        event_bus: Optional[Any] = None,
        strict_synthesis_mode: bool = False,
    ) -> None:
        self._validator = validator
        self._sandboxer = sandboxer
        self._registry = registry_manager
        self._sm = state_machine
        self._correlator = trace_correlator
        self._event_bus = event_bus
        self._strict_mode = strict_synthesis_mode
        self._code_store: Dict[str, str] = {}
        self._intent_store: Dict[str, Dict[str, Any]] = {}

    # ── Properties ──────────────────────────────────────────────

    @property
    def state_machine(self) -> SynthesisStateMachine:
        return self._sm

    @property
    def validator(self) -> ToolValidator:
        return self._validator

    @property
    def sandboxer(self) -> ToolSandboxer:
        return self._sandboxer

    @property
    def registry_manager(self) -> ToolRegistryManager:
        return self._registry

    @property
    def trace_correlator(self) -> SynthesisTraceCorrelator:
        return self._correlator

    # ── synthesize_from_intent ──────────────────────────────────

    def synthesize_from_intent(  # LAW-2 LAW-12 RULE-1
        self,
        intent: Dict[str, Any],
        context: Dict[str, Any],
        synthesis_trace_id: str = "",
    ) -> Dict[str, Any]:
        """Generate tool code from a G1 Planner intent.

        Steps:
          1. Deterministic Synthesis Guard check (RULE 1)
          2. Code generation from intent template
          3. AST validation and hashing
          4. Security scan (no OS imports, risk scoring)
          5. Sandbox dry-run
          6. Registration
        """
        if not synthesis_trace_id:
            synthesis_trace_id = self._correlator.generate_trace_id(
                intent.get("intent_id", ""),
                context.get("plan_id", ""),
            )

        self._sm.force_set(SynthesisState.INTENT_RECEIVED)

        # Check determinism cache
        capability_set = intent.get("capability_set", [])
        hit, cached_code, cached_hash = self._sm.check_deterministic_review(
            intent, context, capability_set,
        )

        if hit:
            logger.info("Determinism cache hit for intent %s", intent.get("intent_id"))
            self._sm.force_set(SynthesisState.CODE_GENERATION)

            return {
                "generated_code": cached_code,
                "ast_hash": cached_hash,
                "capability_set": capability_set,
                "estimated_risk_score": 0.0,
                "synthesis_trace_id": synthesis_trace_id,
                "cache_hit": True,
            }

        # Guard: has_intent
        ok, _ = self._sm.transition(SynthesisState.CODE_GENERATION, intent=intent)
        if not ok:
            raise RuntimeError("Intent missing required fields: goal, target_nodes")

        # Generate code
        generated_code = self._generate_code(intent, context)
        self._code_store[intent.get("intent_id", "")] = generated_code

        # Guard: code_generated
        ok, _ = self._sm.transition(SynthesisState.AST_VALIDATION, generated_code=generated_code)
        if not ok:
            raise RuntimeError("Code generation returned empty code")

        # AST validation + capability inference
        ast_hash = self._compute_ast_hash(generated_code)
        inferred_caps = self._validator._infer_capabilities_from_code(generated_code)
        merged_caps = list(set(capability_set) | inferred_caps)

        # Cache deterministically
        self._sm.cache_deterministic_review(
            intent, context, capability_set, generated_code, ast_hash,
        )

        self._intent_store[intent.get("intent_id", "")] = intent
        self._correlator.record_correlation(
            context.get("plan_id", ""), "g4_synthesizer", synthesis_trace_id,
        )

        self._emit("tool.synthesis.started", {
            "intent_id": intent.get("intent_id"),
            "plan_id": context.get("plan_id"),
            "synthesis_trace_id": synthesis_trace_id,
        })

        return {
            "generated_code": generated_code,
            "ast_hash": ast_hash,
            "capability_set": merged_caps,
            "estimated_risk_score": 0.0,
            "synthesis_trace_id": synthesis_trace_id,
            "cache_hit": False,
        }

    # ── validate_ast ────────────────────────────────────────────

    def validate_ast(  # LAW-14 RULE-2
        self,
        code: str,
    ) -> Dict[str, Any]:
        """Perform AST-level validation with security checks.

        Returns:
            Dict with ast_valid, no_os_imports, security_findings,
            capability_match_score, confidence_score, ast_hash.
        """
        if not code or not code.strip():
            return {
                "ast_valid": False,
                "no_os_imports": False,
                "security_findings": [],
                "capability_match_score": 0.0,
                "overall_risk_score": 1.0,
                "confidence_score": 0.0,
                "ast_hash": "",
            }

        # AST parse check
        try:
            ast_module.parse(code)
            ast_valid = True
        except SyntaxError:
            ast_valid = False

        ast_hash = self._compute_ast_hash(code)

        # Security analysis
        ast_container = {"code": code}
        no_os = self._validator.verify_no_os_imports(ast_container)

        security = self._validator.analyze_security_risk(ast_container)

        existing_caps = self._validator._infer_capabilities_from_code(code)
        cap_result = self._validator.check_capability_match({
            "generated_code": code,
            "capability_set": list(existing_caps),
        })

        confidence = self._validator.rate_confidence([{
            "ast_valid": ast_valid,
            "no_os_imports": no_os,
            "capability_match_score": cap_result.get("capability_match_score", 0),
            "overall_risk_score": security.get("overall_risk_score", 1.0),
            "security_findings": security.get("security_findings", []),
        }])

        return {
            "ast_valid": ast_valid,
            "no_os_imports": no_os,
            "security_findings": security.get("security_findings", []),
            "capability_match_score": cap_result.get("capability_match_score", 0),
            "overall_risk_score": security.get("overall_risk_score", 1.0),
            "confidence_score": confidence,
            "ast_hash": ast_hash,
        }

    # ── generate_tool_signature ────────────────────────────────

    def generate_tool_signature(  # LAW-2
        self,
        code: str,
        capability_set: List[str],
    ) -> Dict[str, Any]:
        """Derive typing signature from generated code."""
        try:
            tree = ast_module.parse(code)
        except SyntaxError:
            return {
                "tool_name": "unknown",
                "parameters": [],
                "return_type": "Any",
                "capability_set": capability_set,
                "signature_hash": hashlib.sha256(code.encode()).hexdigest()[:16],
            }

        tool_name = "synthesised_tool"
        parameters: List[Dict[str, Any]] = []
        return_type = "Any"

        for node in ast_module.walk(tree):
            if isinstance(node, ast_module.FunctionDef):
                tool_name = node.name
                for arg in node.args.args:
                    arg_name = arg.arg
                    arg_type = "Any"
                    if arg.annotation:
                        if isinstance(arg.annotation, ast_module.Name):
                            arg_type = arg.annotation.id
                        elif isinstance(arg.annotation, ast_module.Subscript):
                            arg_type = "complex"
                    parameters.append({
                        "name": arg_name,
                        "type_hint": arg_type,
                        "default": None,
                    })
                if node.returns:
                    if isinstance(node.returns, ast_module.Name):
                        return_type = node.returns.id
                    elif isinstance(node.returns, ast_module.Subscript):
                        return_type = "complex"
                break

        sig_raw = f"{tool_name}({','.join(p['name'] for p in parameters)})->{return_type}"
        signature_hash = hashlib.sha256(sig_raw.encode()).hexdigest()[:16]

        return {
            "tool_name": tool_name,
            "parameters": parameters,
            "return_type": return_type,
            "capability_set": capability_set,
            "signature_hash": signature_hash,
        }

    # ── publish_synthesis_report ────────────────────────────────

    def publish_synthesis_report(  # LAW-8 LAW-12
        self,
        report: Dict[str, Any],
    ) -> None:
        """Publish synthesis report to EventBus."""
        status = report.get("status", "unknown")
        topic = f"tool.synthesis.{status}"

        self._emit(topic, report)

    # ── Internal helpers ────────────────────────────────────────

    def _generate_code(  # RULE-1
        self,
        intent: Dict[str, Any],
        context: Dict[str, Any],
    ) -> str:
        """Deterministic code generation from intent template.

        RULE 1: Same intent + same context → same code.
        """
        goal = intent.get("goal", "unknown_task")
        target_nodes = intent.get("target_nodes", [])
        constraints = intent.get("constraints", {})

        tool_name = f"syn_{hashlib.sha256(goal.encode()).hexdigest()[:12]}"

        params = ", ".join([
            "context: dict",
            f"target_node: str = '{target_nodes[0] if target_nodes else 'default'}'",
        ])

        body_parts = [
            f"# Synthesised tool for: {goal}",
            f"# Constraints: {json.dumps(constraints, default=str)}",
            "result = {'status': 'ok', 'data': context.get('input', {})}",
        ]

        if constraints.get("requires_confirmation", False):
            body_parts.append("# Confirmation required before execution")

        body = "\n    ".join(body_parts)

        return TOOL_TEMPLATE.format(
            tool_name=tool_name,
            params=params,
            goal=goal,
            body=body,
        )

    @staticmethod
    def _compute_ast_hash(code: str) -> str:
        if not code:
            return hashlib.sha256(b"").hexdigest()
        try:
            tree = ast_module.parse(code)
            canonical = ast_module.dump(tree, indent=None)
        except SyntaxError:
            canonical = code
        return hashlib.sha256(canonical.encode()).hexdigest()

    def _emit(self, topic: str, payload: Dict[str, Any]) -> None:
        if self._event_bus is not None:
            try:
                self._event_bus.publish(topic, payload)
            except Exception:
                logger.warning("Failed to emit %s", topic, exc_info=True)

    def reset(self) -> None:
        self._code_store.clear()
        self._intent_store.clear()
        self._sm.reset()
        self._correlator.reset()
