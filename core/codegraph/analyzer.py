from __future__ import annotations

import ast
import re
from typing import Dict, List, Optional, Set, Tuple

from .graph import EdgeType, Node, NodeType
from .parser import ParsedFile

# Patterns for DI / injection detection
_INJECT_PATTERN = re.compile(r"(self\._\w+\s*=\s*\w+|inject|container|provider|factory)")
_INTERFACE_PATTERN = re.compile(r"(Protocol|ABC|Interface|abstractmethod|@abstract)")


class AnalysisResult:
    """Intermediate representation from the analysis stage."""

    def __init__(self) -> None:
        self.import_edges: List[Tuple[str, str, EdgeType, float]] = []
        self.call_edges: List[Tuple[str, str, EdgeType, float]] = []
        self.class_relations: List[Tuple[str, str, EdgeType, float]] = []
        self.di_edges: List[Tuple[str, str, EdgeType, float]] = []
        self.interface_edges: List[Tuple[str, str, EdgeType, float]] = []


def analyze_parsed_file(
    parsed: ParsedFile,
    module_map: Dict[str, str],
) -> AnalysisResult:
    """Stage 2 — analyze a parsed file for semantic relations.

    Detection types:
    - imports (→ EdgeType.IMPORTS)
    - function calls (→ EdgeType.CALLS)
    - class inheritance (→ EdgeType.IMPLEMENTS / DEPENDS_ON)
    - DI patterns (→ EdgeType.INJECTS)
    - interface usage (→ EdgeType.IMPLEMENTS)
    """
    result = AnalysisResult()
    path = parsed.path

    # 1. Import edges
    for imp in parsed.raw_imports:
        target = _resolve_import_target(imp, module_map)
        if target:
            result.import_edges.append((path, target, EdgeType.IMPORTS, 1.0))

    # 2. Analyze AST body for deeper relations
    if parsed.ast_body is not None:
        _analyze_ast(parsed.ast_body, path, result)

    return result


def _resolve_import_target(imp: str, module_map: Dict[str, str]) -> Optional[str]:
    """Resolve an import name to a file path via module_map."""
    # Try exact match
    if imp in module_map:
        return module_map[imp]
    # Try prefix match (submodules)
    parts = imp.split(".")
    for i in range(len(parts), 0, -1):
        prefix = ".".join(parts[:i])
        if prefix in module_map:
            return module_map[prefix]
    return None


def _analyze_ast(tree: ast.Module, path: str, result: AnalysisResult) -> None:
    for node in ast.walk(tree):
        # Detect function calls
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                caller = _safe_name(node.func.value)
                if caller:
                    result.call_edges.append(
                        (path, caller, EdgeType.CALLS, 0.7)
                    )

        # Detect DI injection assignment patterns
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                    if target.value.id == "self" and target.attr.startswith("_"):
                        if isinstance(node.value, ast.Call):
                            func_name = _safe_name(node.value.func)
                            if func_name:
                                result.di_edges.append(
                                    (path, func_name, EdgeType.INJECTS, 0.9)
                                )


def _safe_name(node) -> Optional[str]:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def compute_complexity(parsed: ParsedFile) -> float:
    """Compute a deterministic complexity score based on symbol count."""
    score = 0.0
    score += len(parsed.classes) * 3.0
    score += len(parsed.functions) * 1.5
    score += len(parsed.raw_imports) * 0.5
    return min(score, 100.0)


def compute_risk_score(
    path: str,
    dep_count: int,
    reverse_dep_count: int,
) -> float:
    """Compute a deterministic risk score based on coupling."""
    base = 0.1
    base += dep_count * 0.05
    base += reverse_dep_count * 0.1
    return min(base, 1.0)
