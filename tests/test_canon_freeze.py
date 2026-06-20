"""Canon Freeze Tests — Enforce strict architectural boundaries.

Ref: RC16.7-D Canon Freeze & Dependency Enforcement
"""

import ast
import os
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CORE = os.path.join(ROOT, "core")


def _find_py_files(root: str) -> list:
    files = []
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if fn.endswith(".py") and not fn.startswith("test_"):
                files.append(os.path.join(dirpath, fn))
    return files


def _check_imports(filepath: str, forbidden_prefixes: list) -> list:
    """Check for imports, but skip TYPE_CHECKING blocks."""
    violations = []
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    try:
        tree = ast.parse(content, filename=filepath)
    except SyntaxError:
        return violations

    # Find all TYPE_CHECKING ranges
    type_checking_ranges = []
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            test = node.test
            is_type_checking = False
            if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
                is_type_checking = True
            elif isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING":
                is_type_checking = True
            elif isinstance(test, ast.Attribute) and isinstance(test.value, ast.Name):
                if test.value.id == "typing" and test.attr == "TYPE_CHECKING":
                    is_type_checking = True

            if is_type_checking and node.body:
                start = node.body[0].lineno
                end = node.body[-1].lineno
                type_checking_ranges.append((start, end))

    def _in_type_checking_block(lineno: int) -> bool:
        for start, end in type_checking_ranges:
            if start <= lineno <= end:
                return True
        return False

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if any(alias.name.startswith(prefix) for prefix in forbidden_prefixes):
                    if not _in_type_checking_block(node.lineno):
                        violations.append(
                            f"{filepath}:{node.lineno} imports {alias.name}"
                        )
        elif isinstance(node, ast.ImportFrom):
            if node.module and any(
                node.module.startswith(prefix) for prefix in forbidden_prefixes
            ):
                if not _in_type_checking_block(node.lineno):
                    violations.append(
                        f"{filepath}:{node.lineno} imports from {node.module}"
                    )
    return violations


class TestCanonFreeze:
    """Enforce strict architectural boundaries (Canon Freeze)."""

    def test_no_interface_imports_implementation(self):
        """LAW 2: Interfaces must not import runtime or control_plane implementations.

        TYPE_CHECKING imports are allowed (for Protocol type hints).
        """
        interfaces_dir = os.path.join(CORE, "interfaces")
        forbidden = ["core.runtime", "core.control_plane"]
        violations = []

        for filepath in _find_py_files(interfaces_dir):
            if not filepath.endswith("__init__.py"):
                violations.extend(_check_imports(filepath, forbidden))

        assert len(violations) == 0, (
            f"Interface imports implementation:\n" + "\n".join(violations)
        )

    def test_no_direct_control_plane_instantiation_in_runtime(self):
        """LAW 13: Runtime must not directly instantiate Control Plane managers (must use DI)."""
        runtime_dir = os.path.join(CORE, "runtime")
        violations = []

        for filepath in _find_py_files(runtime_dir):
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                if (
                    "TenantManager()" in content
                    or "OrganizationManager()" in content
                    or "ResourceManager()" in content
                    or "PolicyManager()" in content
                    or "ApprovalManager()" in content
                ):
                    violations.append(
                        f"{filepath} directly instantiates a Control Plane manager"
                    )

        assert len(violations) == 0, (
            f"Direct instantiation detected:\n" + "\n".join(violations)
        )

    def test_execution_engine_only_instantiated_in_composition_root(self):
        """LAW 13: ExecutionEngine must only be instantiated in CompositionRoot."""
        violations = []

        for filepath in _find_py_files(CORE):
            # Allow composition root and its factories
            if "composition/" in filepath or "test_" in filepath:
                continue
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                if "ExecutionEngine(" in content and "IExecutionEngine" not in content:
                    violations.append(
                        f"{filepath} instantiates ExecutionEngine directly"
                    )

        assert len(violations) == 0, (
            f"ExecutionEngine instantiated outside CompositionRoot:\n"
            + "\n".join(violations)
        )
