#!/usr/bin/env python3
"""LAW 13 AST Enforcer — Permanent CompositionRoot Gate.

Scans ``core/``, ``scripts/``, and ``routers/`` for direct
``ExecutionEngine(`` or ``UnifiedRuntime(`` calls that bypass
``core/composition/root.py``, the only permitted instantiation site.

Exit codes:
    0 — no violations found
    1 — violations found (CI fail / pre-commit reject)

Usage:
    python scripts/enforce/law13_ast_check.py
"""

import ast
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

BANNED_PATTERNS = ("ExecutionEngine", "UnifiedRuntime")
EXEMPTED_FILE = "core/composition/root.py"
SKIP_DIRS = {"__pycache__", ".git", ".venv", "venv", "node_modules"}


class Law13Visitor(ast.NodeVisitor):
    """Finds direct calls to ExecutionEngine(...) or UnifiedRuntime(...)."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.violations: list[tuple[int, str]] = []

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id in BANNED_PATTERNS:
            self.violations.append((node.lineno, node.func.id))
        self.generic_visit(node)


def scan_file(filepath: Path) -> list[tuple[int, str]]:
    """Return list of (lineno, pattern) for every violation in *filepath*."""
    try:
        tree = ast.parse(filepath.read_text(), filename=str(filepath))
    except SyntaxError:
        return []  # skip non-Python or broken files

    visitor = Law13Visitor(str(filepath))
    visitor.visit(tree)
    return visitor.violations


def main() -> int:
    scan_dirs = [PROJECT_ROOT / "core", PROJECT_ROOT / "scripts", PROJECT_ROOT / "routers"]
    all_violations: list[tuple[str, int, str]] = []

    for scan_dir in scan_dirs:
        if not scan_dir.is_dir():
            continue
        for py_file in sorted(scan_dir.rglob("*.py")):
            # Skip exempted file
            if EXEMPTED_FILE in str(py_file):
                continue
            # Skip hidden/skip dirs
            if any(seg.startswith(".") or seg in SKIP_DIRS for seg in py_file.relative_to(PROJECT_ROOT).parts):
                continue
            violations = scan_file(py_file)
            for lineno, pattern in violations:
                rel = py_file.relative_to(PROJECT_ROOT)
                all_violations.append((str(rel), lineno, pattern))

    if all_violations:
        print("❌ LAW 13 VIOLATIONS FOUND — direct ExecutionEngine/UnifiedRuntime calls outside CompositionRoot:")
        print()
        for rel, lineno, pattern in sorted(all_violations):
            print(f"  {rel}:{lineno}  {pattern}(")
        print()
        print("⛔  Fix: inject via CompositionRoot instead of direct instantiation.")
        return 1

    print("✅ LAW 13 OK — no direct ExecutionEngine/UnifiedRuntime calls outside CompositionRoot.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
