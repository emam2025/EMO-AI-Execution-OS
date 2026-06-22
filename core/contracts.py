"""Execution Contract Layer — DAG schema versioning + ToolContract enforcement.

Defines the formal contract every DAG and tool must satisfy:
  1. Schema versioning for the DAG format
  2. Declared input/output schemas per tool
  3. Runtime contract validation before/after tool execution

Architecture:
    ToolContract  ─── declares expected inputs + outputs for a tool
    ContractValidator ─ validates a PlanNode against its ToolContract
    DependencyGraph ─── carries a SCHEMA_VERSION
    ExecutionEngine ═══ validates contracts at runtime (pre-flight + post-flight)
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("emo_ai.contracts")

MAX_PAYLOAD_SIZE = 10 * 1024 * 1024  # 10 MB

# Dangerous unicode patterns: bidirectional text, zero-width chars, confusables
_UNSAFE_UNICODE_RE = re.compile(
    "["
    "\U0000200B"  # ZERO WIDTH SPACE
    "\U0000200C"  # ZERO WIDTH NON-JOINER
    "\U0000200D"  # ZERO WIDTH JOINER
    "\U0000200E"  # LEFT-TO-RIGHT MARK
    "\U0000200F"  # RIGHT-TO-LEFT MARK
    "\U00002028"  # LINE SEPARATOR
    "\U00002029"  # PARAGRAPH SEPARATOR
    "\U0000202A"  # LEFT-TO-RIGHT EMBEDDING
    "\U0000202B"  # RIGHT-TO-LEFT EMBEDDING
    "\U0000202C"  # POP DIRECTIONAL FORMATTING
    "\U0000202D"  # LEFT-TO-RIGHT OVERRIDE
    "\U0000202E"  # RIGHT-TO-LEFT OVERRIDE
    "\U0000FEFF"  # ZERO WIDTH NO-BREAK SPACE (BOM)
    "]"
)

# Current DAG schema version. Bump when PlanNode/PlanEdge fields change.
DAG_SCHEMA_VERSION = "1.0.0"

# Known schema versions the engine can execute (semver matching).
SUPPORTED_SCHEMA_VERSIONS: Set[str] = {"1.0.0"}


class ContractViolation(Exception):
    """Raised when a tool's execution violates its declared contract."""

    def __init__(self, tool: str, message: str, details: Optional[Dict[str, Any]] = None):
        self.tool = tool
        self.details = details or {}
        super().__init__(f"[{tool}] Contract violation: {message}")


class SchemaVersionMismatch(Exception):
    """Raised when a DAG's schema version is incompatible with the engine."""

    def __init__(self, dag_version: str, supported: Set[str]):
        self.dag_version = dag_version
        self.supported = supported
        super().__init__(
            f"DAG schema v{dag_version} not in supported versions: {sorted(supported)}"
        )


# ═══════════════════════════════════════════════════════════════════════
# ToolContract
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class ParamSpec:
    """Describes a single parameter in a tool's contract."""
    name: str
    type_hint: str               # "str", "int", "dict", "list", "any"
    required: bool = True
    description: str = ""


@dataclass
class ToolContract:
    """Formal input/output contract for a tool.

    The execution engine validates every node's inputs against
    the `inputs` spec before running, and the outputs against
    the `outputs` spec after running.

    A contract with no input specs means "any inputs are accepted".
    A contract with no output specs means "any outputs are accepted".
    """
    tool_name: str = ""
    description: str = ""
    inputs: List[ParamSpec] = field(default_factory=list)
    outputs: List[ParamSpec] = field(default_factory=list)
    version: str = DAG_SCHEMA_VERSION

    # If True, unknown input keys cause a violation. If False, they are ignored.
    strict_inputs: bool = True
    strict_outputs: bool = True


# ═══════════════════════════════════════════════════════════════════════
# ContractValidator
# ═══════════════════════════════════════════════════════════════════════


class ContractValidator:
    """Validates tool inputs/outputs against a ToolContract.

    Hardening applied (AD-002 resolution):
      1. Payload size limit enforced on serialized inputs/outputs.
      2. Unicode sanitization — dangerous bidirectional/zero-width chars rejected.
      3. Unknown type hints log a warning instead of silently accepting.
    """

    @staticmethod
    def _check_payload_size(data: Dict[str, Any], label: str) -> List[str]:
        errors: List[str] = []
        try:
            size = len(json.dumps(data, default=str))
        except Exception:
            size = 0
        if size > MAX_PAYLOAD_SIZE:
            errors.append(
                f"{label} payload {size} bytes exceeds limit of {MAX_PAYLOAD_SIZE} bytes"
            )
        return errors

    @staticmethod
    def _check_unicode(value: Any, path: str) -> List[str]:
        errors: List[str] = []
        if isinstance(value, str):
            match = _UNSAFE_UNICODE_RE.search(value)
            if match:
                errors.append(
                    f"Unicode sanitization: dangerous char U+{ord(match.group()):04X} "
                    f"at {path}"
                )
        elif isinstance(value, dict):
            for k, v in value.items():
                errors.extend(ContractValidator._check_unicode(k, f"{path}.{k}"))
                errors.extend(ContractValidator._check_unicode(v, f"{path}.{k}"))
        elif isinstance(value, list):
            for i, v in enumerate(value):
                errors.extend(ContractValidator._check_unicode(v, f"{path}[{i}]"))
        return errors

    @staticmethod
    def validate_inputs(contract: ToolContract, inputs: Dict[str, Any]) -> List[str]:
        """Return a list of violation messages (empty = valid)."""
        errors: List[str] = []

        # AD-002: payload size limit
        errors.extend(ContractValidator._check_payload_size(inputs, "Input"))

        # AD-002: unicode sanitization
        for k, v in inputs.items():
            errors.extend(ContractValidator._check_unicode(v, f"inputs.{k}"))

        spec_map = {p.name: p for p in contract.inputs}
        provided = set(inputs.keys())

        # Check required params
        for spec in contract.inputs:
            if spec.required and spec.name not in provided:
                errors.append(f"Missing required input '{spec.name}' ({spec.type_hint})")

        # Check param types
        for name, value in inputs.items():
            spec = spec_map.get(name)
            if spec is not None and spec.type_hint != "any":
                if not ContractValidator._type_matches(value, spec.type_hint):
                    errors.append(
                        f"Input '{name}': expected {spec.type_hint}, got {type(value).__name__}"
                    )

        # Strict mode: reject unknown inputs
        if contract.strict_inputs:
            unknown = provided - set(spec_map.keys())
            if unknown and contract.inputs:
                for k in sorted(unknown):
                    errors.append(f"Unknown input '{k}' (not in contract)")

        return errors

    @staticmethod
    def validate_outputs(contract: ToolContract, outputs: Dict[str, Any]) -> List[str]:
        """Return a list of violation messages (empty = valid)."""
        errors: List[str] = []

        # AD-002: payload size limit
        errors.extend(ContractValidator._check_payload_size(outputs, "Output"))

        # AD-002: unicode sanitization
        for k, v in outputs.items():
            errors.extend(ContractValidator._check_unicode(v, f"outputs.{k}"))

        spec_map = {p.name: p for p in contract.outputs}
        provided = set(outputs.keys())

        # Check promised outputs exist
        for spec in contract.outputs:
            if spec.required and spec.name not in provided:
                errors.append(f"Missing required output '{spec.name}' ({spec.type_hint})")

        # Check output types
        for name, value in outputs.items():
            spec = spec_map.get(name)
            if spec is not None and spec.type_hint != "any":
                if not ContractValidator._type_matches(value, spec.type_hint):
                    errors.append(
                        f"Output '{name}': expected {spec.type_hint}, got {type(value).__name__}"
                    )

        # Strict mode: reject unknown outputs
        if contract.strict_outputs:
            unknown = provided - set(spec_map.keys())
            if unknown and contract.outputs:
                for k in sorted(unknown):
                    errors.append(f"Unknown output '{k}' (not in contract)")

        return errors

    @staticmethod
    def _type_matches(value: Any, type_hint: str) -> bool:
        mapping = {
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "dict": dict,
            "list": list,
            "any": object,
        }
        expected = mapping.get(type_hint)
        if expected is None:
            logger.warning("Unknown type hint '%s' in contract — accepting value", type_hint)
            return True
        return isinstance(value, expected)


# ═══════════════════════════════════════════════════════════════════════
# Pre-built contracts for all 10 registered tools
# ═══════════════════════════════════════════════════════════════════════

# ── Consolidated agent contract ──────────────────────────────
# All agent.* tools return the same shape:
#   {"insight_summary": str, "evidence": dict, "heuristic_analysis": dict, "conclusion": str}
# Rather than duplicating 5 output contracts that never match, we
# mark them non-strict and trust the runner.  Inputs vary slightly:
# agent.impact accepts `target`, the rest accept `symbol_id`.
_AGENT_INPUT = [
    ParamSpec("symbol_id", "str", description="Target symbol"),
]
_NONSTRICT_AGENT = ToolContract(
    inputs=_AGENT_INPUT,
    strict_inputs=True,          # enforce symbol_id
    strict_outputs=False,        # accept any output shape
)


TOOL_CONTRACTS: Dict[str, ToolContract] = {
    # ── Graph retrieval ──────────────────────────────────────
    # Outputs are bare lists or dicts with varying keys; mark
    # non-strict so the contract reflects reality.
    "graph_retrieval.ranked_hotspots": ToolContract(
        tool_name="graph_retrieval.ranked_hotspots",
        description="Retrieve ranked hotspot symbols from the graph",
        inputs=[ParamSpec("limit", "int", required=False, description="Max results")],
        strict_inputs=False,
        strict_outputs=False,
    ),
    "graph_retrieval.retrieve_impact_chain": ToolContract(
        tool_name="graph_retrieval.retrieve_impact_chain",
        description="Retrieve impact chain for a symbol",
        inputs=[
            ParamSpec("symbol_id", "str", description="Target symbol"),
            ParamSpec("max_depth", "int", required=False, description="Max traversal depth"),
        ],
        strict_outputs=False,
    ),
    "graph_retrieval.heuristic_analysis": ToolContract(
        tool_name="graph_retrieval.heuristic_analysis",
        description="Run heuristics on a symbol",
        inputs=[ParamSpec("symbol_id", "str", description="Target symbol")],
        strict_outputs=False,
    ),
    "graph_retrieval.retrieve_symbol_core": ToolContract(
        tool_name="graph_retrieval.retrieve_symbol_core",
        description="Retrieve core metadata for a symbol",
        inputs=[ParamSpec("symbol_id", "str", description="Target symbol")],
        strict_outputs=False,
    ),

    # ── Agent ────────────────────────────────────────────────
    # All agent tools share the same output shape; input varies
    # slightly (agent.impact expects `target`, not `symbol_id`).
    "agent.explain": ToolContract(
        tool_name="agent.explain",
        description="Explain what a symbol does",
        inputs=_AGENT_INPUT,
        strict_inputs=True,
        strict_outputs=False,
    ),
    "agent.impact": ToolContract(
        tool_name="agent.impact",
        description="Analyze impact of a symbol or file",
        inputs=[ParamSpec("target", "str", description="Symbol ID or file ID")],
        strict_inputs=True,
        strict_outputs=False,
    ),
    "agent.why": ToolContract(
        tool_name="agent.why",
        description="Explain why a symbol matters",
        inputs=_AGENT_INPUT,
        strict_inputs=True,
        strict_outputs=False,
    ),
    "agent.suggest_refactor": ToolContract(
        tool_name="agent.suggest_refactor",
        description="Suggest refactoring for a symbol",
        inputs=_AGENT_INPUT,
        strict_inputs=True,
        strict_outputs=False,
    ),
    "agent.top_hotspots": ToolContract(
        tool_name="agent.top_hotspots",
        description="Enrich hotspot list with AI analysis",
        inputs=[ParamSpec("limit", "int", required=False, description="Max results")],
        strict_inputs=False,
        strict_outputs=False,
    ),

    # ── Hybrid retrieval ─────────────────────────────────────
    # Already non-strict; keep as-is.
    "hybrid_retrieval.retrieve": ToolContract(
        tool_name="hybrid_retrieval.retrieve",
        description="Hybrid semantic + graph retrieval",
        inputs=[
            ParamSpec("query", "str", required=False, description="Search query"),
            ParamSpec("top_k", "int", required=False, description="Max results"),
        ],
        strict_inputs=False,
        strict_outputs=False,
    ),

    # ── Context Compiler ──────────────────────────────────────
    "context_compiler.build_llm_context": ToolContract(
        tool_name="context_compiler.build_llm_context",
        description="Assemble full LLM-ready context for a symbol",
        inputs=[
            ParamSpec("symbol_id", "str", required=True,
                      description="Target symbol ID"),
        ],
        strict_inputs=True,
        strict_outputs=False,
    ),
    "context_compiler.build_symbol_context": ToolContract(
        tool_name="context_compiler.build_symbol_context",
        description="Build symbol-level context (callers, callees, neighbours)",
        inputs=[
            ParamSpec("symbol_id", "str", required=True,
                      description="Target symbol ID"),
        ],
        strict_inputs=True,
        strict_outputs=False,
    ),
    "context_compiler.build_file_context": ToolContract(
        tool_name="context_compiler.build_file_context",
        description="Build file-level context (symbols, deps, impact, hotspots)",
        inputs=[
            ParamSpec("file_id", "str", required=True,
                      description="Target file ID"),
        ],
        strict_inputs=True,
        strict_outputs=False,
    ),
}
