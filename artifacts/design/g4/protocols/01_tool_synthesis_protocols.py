"""Phase G4 — Tool Synthesis Agent: Protocols.  # LAW-2 LAW-10 LAW-12 LAW-14

Formal typing.Protocol definitions for the Tool Synthesis Agent subsystem.
Each protocol maps to a specific ROADMAP Phase G4 responsibility:

  IToolSynthesizer         — Top-level orchestrator (synthesize → validate → sign → publish)
  IToolValidator           — AST validation, security analysis, capability matching
  IToolSandboxer           — Sandboxed dry-run execution within Phase 4 isolation boundaries
  IToolRegistryManager     — Auto-registration of synthesised tools in the ToolRegistry

Ref: Canon LAW 2 (Interface Authority), LAW 10 (Unreliable Workers)
Ref: Canon LAW 12 (Traceability), LAW 14 (Resource Governance)
Ref: Canon RULE 1 (Determinism), RULE 2 (No Uncontrolled IO)
Ref: Canon RULE 3 (Safety Guards), RULE 4 (Isolation)
Ref: DEVELOPER.md §15.2, §15.10, §15.15b
Ref: ROADMAP Phase G4
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


# ═══════════════════════════════════════════════════════════════════
# 1. IToolSynthesizer
# ═══════════════════════════════════════════════════════════════════


@runtime_checkable
class IToolSynthesizer(Protocol):  # LAW-2 LAW-12 RULE-1 RULE-2
    """Top-level orchestrator of the Tool Synthesis Agent subsystem.

    Consumes G1 Planner Intents, G3 Optimization Proposals, and Phase 4
    Sandbox context to dynamically generate executable tool code:

      - synthesize_from_intent:  G1 intent → generated code
      - validate_ast:            AST-level validation of generated code
      - generate_tool_signature: Derive typing signature + capability set
      - publish_synthesis_report: Emit synthesis result to EventBus

    LAW 2:  All tool interfaces MUST conform to typing.Protocol authority.
    LAW 12: Every synthesis carries a synthesis_trace_id.
    RULE 1: Same intent + context → same generated code (Deterministic Synthesis Guard).
    RULE 2: Generated code MUST never perform uncontrolled IO.
    """

    def synthesize_from_intent(
        self,
        intent: Dict[str, Any],
        context: Dict[str, Any],
        synthesis_trace_id: str = "",
    ) -> Dict[str, Any]:
        """Synthesize executable tool code from a G1 Planner intent.

        Args:
            intent:  G1 intent dict with fields:
                - intent_id (str): Unique intent identifier
                - goal (str): Natural-language goal description
                - target_nodes (List[str]): DAG node IDs this intent targets
                - constraints (Dict[str, Any]): Resource / security / isolation constraints
                - confidence (float): G1 planning confidence [0,1]
            context:  Context dict with fields:
                - plan_id (str):  Parent G1 plan ID
                - dag_topology (List[Dict]): Current DAG structure
                - node_capabilities (Dict[str, List[str]]): Capabilities per node
                - sandbox_profile (Dict[str, Any]): Phase 4 sandbox config
                - optimizer_trace_id (str): Cross-layer trace from G3
            synthesis_trace_id:  Cross-layer trace ID for LAW 12 compliance.

        Returns:
            Dict with:
                - generated_code (str): The synthesised tool source code
                - ast_hash (str): SHA-256 hash of the AST (LAW 14)
                - capability_set (List[str]): Declared capabilities
                - estimated_risk_score (float): [0,1] risk estimate from static analysis
                - synthesis_trace_id (str): Matches the input trace ID
        """

    def validate_ast(
        self,
        code: str,
    ) -> Dict[str, Any]:
        """Perform AST-level validation on generated code.

        Checks:
          - Syntactically valid Python
          - No os.system, subprocess.Popen, eval, exec, __import__
          - No file writes outside sandbox-allowed paths
          - No network imports (urllib, requests, socket, http)

        Returns:
            Dict with:
                - ast_valid (bool): AST parses without error
                - no_os_imports (bool): No OS-level imports detected
                - security_findings (List[Dict]): List of {severity, rule, line}
                - ast_hash (str): SHA-256 of canonical AST
        """

    def generate_tool_signature(
        self,
        code: str,
        capability_set: List[str],
    ) -> Dict[str, Any]:
        """Derive a typing-compatible signature and metadata from synthesised code.

        Extracts function/class names, parameter types, return types,
        and capability annotations. Produces a formal signature suitable
        for ToolRegistry registration.

        Returns:
            Dict with:
                - tool_name (str): Extracted function/class name
                - parameters (List[Dict]): [{name, type_hint, default}]
                - return_type (str): Inferred return type annotation
                - capability_set (List[str]): Declared capabilities
                - signature_hash (str): SHA-256 of canonical signature
        """

    def publish_synthesis_report(
        self,
        report: Dict[str, Any],
    ) -> None:
        """Publish synthesis report to EventBus.

        §15.15b: All reports MUST be routed to EventBus topics:
          - tool.synthesis.completed
          - tool.synthesis.failed
          - tool.synthesis.security_violation
          - tool.synthesis.registered
          - tool.synthesis.rollback
        """


# ═══════════════════════════════════════════════════════════════════
# 2. IToolValidator
# ═══════════════════════════════════════════════════════════════════


@runtime_checkable
class IToolValidator(Protocol):  # LAW-10 RULE-2 RULE-3 RULE-4
    """Security and safety validation for synthesised tools.

    Performs static analysis, capability matching, and confidence scoring
    to ensure synthesised tools comply with isolation and IO policies.

    RULE 2:  No OS imports, no network IO, no uncontrolled file access.
    RULE 3:  Safety guards MUST block registration if any check fails.
    RULE 4:  Validation MUST assume no trust — all code is untrusted.
    """

    def check_capability_match(
        self,
        tool_spec: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Validate that the tool's declared capabilities match its code.

        Cross-references declared capability_set against AST-inferred
        capabilities. Flags mismatches.

        Returns:
            Dict with:
                - capability_match_score (float): [0,1] fraction of declared
                  capabilities that are reflected in the code
                - mismatches (List[str]): Capabilities declared but not found
                - undeclared (List[str]): Capabilities found but not declared
        """

    def analyze_security_risk(
        self,
        ast: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Analyze AST for security violations.

        Categories (severity HIGH / MEDIUM / LOW):
          - HIGH:   os.*, subprocess.*, importlib, __import__, eval, exec, compile
          - MEDIUM: open(), file I/O, path traversal, environ access
          - LOW:    large recursion, unbounded loops, all()/any() misuse

        Returns:
            Dict with:
                - security_findings (List[Dict]): {severity, category, line, rule}
                - overall_risk_score (float): [0,1] aggregated risk
                - allowed (bool): True if no HIGH findings
        """

    def verify_no_os_imports(
        self,
        ast: Dict[str, Any],
    ) -> bool:
        """Check that the AST contains zero OS-level imports.

        Banned modules (non-exhaustive):
          os, subprocess, shutil, signal, ctypes, fcntl,
          pty, resource, syslog, posix, grp, pwd, spwd

        Returns:
            True if no banned imports found.
        """

    def rate_confidence(
        self,
        validation_reports: List[Dict[str, Any]],
    ) -> float:
        """Compute aggregate confidence score from all validation stages.

        Scoring:
          - AST valid:                               +0.3
          - No OS imports:                           +0.3
          - Capability match >= 0.8:                 +0.2
          - Security risk score <= 0.2:              +0.2
          - Each HIGH finding:                       -0.2
          - Each MEDIUM finding:                     -0.1

        Returns:
            Float [0,1] — aggregate confidence score.
        """


# ═══════════════════════════════════════════════════════════════════
# 3. IToolSandboxer
# ═══════════════════════════════════════════════════════════════════


@runtime_checkable
class IToolSandboxer(Protocol):  # LAW-10 RULE-2 RULE-4
    """Sandboxed dry-run execution within Phase 4 isolation boundaries.

    Executes synthesised tool code in a constrained sandbox to verify
    behaviour, capture side effects, and measure resource consumption
    BEFORE registration in ToolRegistry.

    Phase 4: All execution MUST happen inside an isolated sandbox.
    RULE 2:  Sandbox MUST block all uncontrolled IO.
    RULE 4:  Sandbox MUST enforce strict resource limits.
    """

    def prepare_sandbox_context(
        self,
        tool_spec: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Create a sandbox context for the tool.

        Builds a confined execution environment with:
          - Allowed capabilities list
          - Resource limits (CPU time, memory, fd count)
          - IO policy (read-only paths, blocked network)
          - Timeout
          - Network mode (always OFF for synthesised tools)

        Returns:
            Dict with:
                - sandbox_id (str): Unique sandbox session ID
                - allowed_capabilities (List[str]): Capabilities granted
                - resource_limits (Dict): {max_cpu_sec, max_memory_mb, max_fds}
                - io_policy (Dict): {allowed_read_paths[], blocked_imports[]}
                - timeout_sec (float): Max execution time
                - network_mode (str): Always "blocked"
        """

    def execute_dry_run(
        self,
        sandbox_ctx: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute tool code inside the sandbox.

        Returns:
            Dict with:
                - success (bool): Dry-run completed without exception
                - output (str): Captured stdout/stderr
                - resource_used (Dict): {cpu_sec, memory_mb, fd_count}
                - duration_ms (float): Actual execution time
        """

    def capture_side_effects(
        self,
        sandbox_ctx: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Capture all side effects observed during dry-run.

        Monitors:
          - File system writes (path, bytes written)
          - Network connections attempted (blocked)
          - Process spawn attempts (blocked)
          - Environment variable reads/writes
          - Shared memory access

        Returns:
            List of Dicts: {effect_type, target, value, blocked(bool)}
        """

    def cleanup_sandbox(
        self,
        sandbox_ctx: Dict[str, Any],
    ) -> None:
        """Clean up sandbox resources after dry-run completes.

        Guarantees:
          - All temp files are removed
          - All subprocesses are killed
          - All allocated memory is freed
          - EventBus emits `sandbox.cleaned` topic
        """


# ═══════════════════════════════════════════════════════════════════
# 4. IToolRegistryManager
# ═══════════════════════════════════════════════════════════════════


@runtime_checkable
class IToolRegistryManager(Protocol):  # LAW-2 LAW-14 RULE-3
    """Auto-registration of synthesised tools in the ToolRegistry.

    Manages the lifecycle of tool registration, compliance validation,
    rollback, and EventBus notification.

    LAW 2:  All registered tools MUST conform to Interface Authority.
            Registration stores the typing.Protocol signature.
    LAW 14: Registration metadata MUST include ast_hash for traceability.
    RULE 3: Registration MUST be rejected if any safety guard fails.
    """

    def register_synthesized_tool(
        self,
        tool_metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Register a synthesised tool in ToolRegistry.

        Args:
            tool_metadata: Dict with:
                - tool_id (str): Unique tool ID
                - signature (Dict): From generate_tool_signature
                - generated_code (str): The source code
                - ast_hash (str): LAW 14 traceability hash
                - capability_set (List[str])
                - estimated_risk_score (float)
                - sandbox_results (Dict)
                - synthesis_trace_id (str)
                - compliance_proof (Dict): Proof that all guards passed

        Returns:
            Dict with:
                - registration_id (str): Confirmation ID
                - status (str): "registered" | "rejected" | "rolled_back"
                - rollback_token (str): Token for rollback_registration
        """

    def validate_registration_compliance(
        self,
        tool_metadata: Dict[str, Any],
    ) -> bool:
        """Validate that the tool metadata satisfies all registration guards.

        Guards (all MUST pass):
          - ast_hash matches generated_code
          - capability_set is non-empty
          - estimated_risk_score <= 0.3
          - sandbox_results.success == true
          - sandbox_results.side_effects list is empty (no blocked effects)

        Returns:
            True if all guards pass.
        """

    def publish_tool_available_event(
        self,
        tool_id: str,
        signature: Dict[str, Any],
    ) -> None:
        """Publish a tool.available event to EventBus.

        §15.15b: All newly registered tools MUST be broadcast on
        the `tool.available` topic so G1 Planner, D8 Service Mesh,
        and F1 UnifiedRuntime can discover them.
        """

    def rollback_registration(
        self,
        tool_id: str,
        rollback_token: str,
    ) -> bool:
        """Roll back a tool registration.

        Removal sequence:
          1. Remove from ToolRegistry index
          2. Emit `tool.registration.rolled_back` on EventBus
          3. Return True on success; False if token is invalid

        Args:
            tool_id: The tool to roll back.
            rollback_token: Token from register_synthesized_tool.

        Returns:
            True if rollback succeeded.
        """
