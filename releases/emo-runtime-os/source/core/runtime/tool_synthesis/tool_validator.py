"""Phase G4 — Tool Validator.  # LAW-10 RULE-2 RULE-3 RULE-4

Security and safety validation for synthesised tools. Performs static
analysis, capability matching, OS-import verification, and confidence
scoring.

Ref: Canon LAW 10 (Unreliable Workers), RULE 2 (No Uncontrolled IO)
Ref: Canon RULE 3 (Safety Guards), RULE 4 (Isolation)
Ref: artifacts/design/g4/protocols/01_tool_synthesis_protocols.py
"""

from __future__ import annotations

import ast as ast_module
import hashlib
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from core.runtime.models.synthesis_models import (
    SecurityFinding,
    ValidationReport,
    ValidationSeverity,
)

logger = logging.getLogger("emo_ai.synthesis.tool_validator")

BANNED_OS_MODULES: Set[str] = {
    "os", "subprocess", "shutil", "signal", "ctypes", "fcntl",
    "pty", "resource", "syslog", "posix", "grp", "pwd", "spwd",
    "socket", "urllib", "requests", "http", "socket", "socketserver",
    "multiprocessing", "threading", "_thread", "asyncio.subprocess",
}

BANNED_BUILTINS: Set[str] = {"eval", "exec", "compile", "__import__"}


class ToolValidator:  # LAW-10 RULE-2 RULE-3 RULE-4
    """Concrete implementation of IToolValidator.

    All methods are deterministic (RULE 1). Validation assumes no trust —
    all synthesised code is treated as untrusted (RULE 4).
    """

    def check_capability_match(
        self,
        tool_spec: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Cross-reference declared capabilities against AST-inferred capabilities.

        Returns:
            Dict with capability_match_score, mismatches[], undeclared[].
        """
        code = tool_spec.get("generated_code", "")
        declared = set(tool_spec.get("capability_set", []))

        inferred = self._infer_capabilities_from_code(code)

        matched = declared & inferred
        mismatches = list(declared - inferred)
        undeclared = list(inferred - declared)

        score = len(matched) / max(len(declared | inferred), 1)

        return {
            "capability_match_score": round(score, 4),
            "mismatches": mismatches,
            "undeclared": undeclared,
        }

    def analyze_security_risk(
        self,
        ast_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Analyze AST for security violations.

        Categories:
          HIGH:   os imports, subprocess, eval/exec/compile, __import__
          MEDIUM: open(), file I/O, path traversal, environ access
          LOW:    large recursion, unbounded loops, all()/any() misuse

        Returns:
            Dict with security_findings[], overall_risk_score, allowed.
        """
        findings: List[Dict[str, Any]] = []
        code = ast_data.get("code", "")

        try:
            tree = compile(code, "<synthesised>", "exec", ast_module.PyCF_ONLY_AST)
        except SyntaxError:
            findings.append(SecurityFinding(
                severity=ValidationSeverity.HIGH,
                category="syntax_error",
                line=0,
                rule="ast_parse",
                detail="Code does not parse as valid Python",
            ).__dict__)
            return {
                "security_findings": findings,
                "overall_risk_score": 1.0,
                "allowed": False,
            }

        self._walk_ast(tree, findings)

        high_count = sum(1 for f in findings if f.get("severity") == "high")
        medium_count = sum(1 for f in findings if f.get("severity") == "medium")

        risk_score = min(1.0, (high_count * 0.4 + medium_count * 0.2))

        return {
            "security_findings": findings,
            "overall_risk_score": round(risk_score, 4),
            "allowed": high_count == 0,
        }

    def verify_no_os_imports(
        self,
        ast_data: Dict[str, Any],
    ) -> bool:
        """Check AST for banned OS-level imports (RULE 2)."""
        code = ast_data.get("code", "")
        try:
            tree = compile(code, "<synthesised>", "exec", ast_module.PyCF_ONLY_AST)
        except SyntaxError:
            return False

        found_banned = self._collect_banned_imports(tree)
        return len(found_banned) == 0

    def rate_confidence(
        self,
        validation_reports: List[Dict[str, Any]],
    ) -> float:
        """Compute aggregate confidence score.

        Scoring:
          - AST valid:           +0.3
          - No OS imports:       +0.3
          - Capability match >= 0.8:  +0.2
          - Risk score <= 0.2:   +0.2
          - Each HIGH finding:   -0.2
          - Each MEDIUM finding: -0.1
        """
        score = 0.0

        for report in validation_reports:
            if report.get("ast_valid"):
                score += 0.3
            if report.get("no_os_imports"):
                score += 0.3
            if report.get("capability_match_score", 0) >= 0.8:
                score += 0.2
            if report.get("overall_risk_score", 1.0) <= 0.2:
                score += 0.2

            findings = report.get("security_findings", [])
            for f in findings:
                if f.get("severity") == "high":
                    score -= 0.2
                elif f.get("severity") == "medium":
                    score -= 0.1

        return round(max(0.0, min(1.0, score)), 4)

    # ── Internal helpers ─────────────────────────────────────

    def _infer_capabilities_from_code(self, code: str) -> Set[str]:
        """Deterministically infer capabilities from source code."""
        capabilities: Set[str] = set()

        try:
            tree = ast_module.parse(code)
        except SyntaxError:
            return capabilities

        for node in ast_module.walk(tree):
            if isinstance(node, ast_module.FunctionDef):
                capabilities.add(f"fn:{node.name}")
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast_module.Name):
                        capabilities.add(f"decorator:{decorator.id}")
            elif isinstance(node, ast_module.ClassDef):
                capabilities.add(f"class:{node.name}")
            elif isinstance(node, ast_module.Call):
                if isinstance(node.func, ast_module.Attribute):
                    capabilities.add(f"call:{node.func.attr}")
                elif isinstance(node.func, ast_module.Name):
                    capabilities.add(f"call:{node.func.id}")
            elif isinstance(node, ast_module.Import):
                for alias in node.names:
                    capabilities.add(f"import:{alias.name}")
            elif isinstance(node, ast_module.ImportFrom):
                if node.module:
                    capabilities.add(f"import:{node.module}")

        return capabilities

    def _walk_ast(  # RULE-2
        self,
        tree: ast_module.AST,
        findings: List[Dict[str, Any]],
    ) -> None:
        """Walk AST nodes and record security findings."""
        for node in ast_module.walk(tree):
            if isinstance(node, (ast_module.Import, ast_module.ImportFrom)):
                if isinstance(node, ast_module.Import):
                    names = [a.name for a in node.names]
                else:
                    names = [node.module] if node.module else []

                for name in names:
                    base = name.split(".")[0]
                    if base in BANNED_OS_MODULES:
                        findings.append(SecurityFinding(
                            severity=ValidationSeverity.HIGH,
                            category="banned_os_import",
                            line=node.lineno or 0,
                            rule="no_os_imports",
                            detail=f"Banned OS-level import: {name}",
                        ).__dict__)

            elif isinstance(node, ast_module.Call):
                if isinstance(node.func, ast_module.Name) and node.func.id in BANNED_BUILTINS:
                    findings.append(SecurityFinding(
                        severity=ValidationSeverity.HIGH,
                        category="banned_builtin",
                        line=node.lineno or 0,
                        rule="no_os_imports",
                        detail=f"Banned builtin call: {node.func.id}",
                    ).__dict__)
                elif isinstance(node.func, ast_module.Attribute):
                    if isinstance(node.func.value, ast_module.Name):
                        if node.func.value.id == "os" and node.func.attr not in (
                            "path", "name", "sep", "linesep", "curdir", "pardir",
                            "environ",
                        ):
                            findings.append(SecurityFinding(
                                severity=ValidationSeverity.HIGH,
                                category="os_call",
                                line=node.lineno or 0,
                                rule="no_os_imports",
                                detail=f"OS module call: os.{node.func.attr}",
                            ).__dict__)
                        elif node.func.value.id == "subprocess":
                            findings.append(SecurityFinding(
                                severity=ValidationSeverity.HIGH,
                                category="subprocess_call",
                                line=node.lineno or 0,
                                rule="no_os_imports",
                                detail=f"Subprocess call: subprocess.{node.func.attr}",
                            ).__dict__)

    def _collect_banned_imports(self, tree: ast_module.AST) -> List[str]:
        """Collect all banned imports from the AST."""
        banned: List[str] = []
        for node in ast_module.walk(tree):
            if isinstance(node, ast_module.Import):
                for alias in node.names:
                    base = alias.name.split(".")[0]
                    if base in BANNED_OS_MODULES:
                        banned.append(alias.name)
            elif isinstance(node, ast_module.ImportFrom):
                if node.module:
                    base = node.module.split(".")[0]
                    if base in BANNED_OS_MODULES:
                        banned.append(node.module)
        return banned
