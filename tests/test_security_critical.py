"""Phase SEC-001 — Critical security fixes verification.

EXEC-DIRECTIVE-SEC-001 acceptance tests:
  1. EMO_JWT_SECRET without env var → RuntimeError
  2. sandbox_executor contains zero eval/exec calls
  3. .gitignore excludes *.db
"""

import importlib
import inspect
import os
import subprocess
import sys

import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Use venv python for subprocess tests (system python lacks project deps)
_VENV_PYTHON = os.path.join(PROJECT_ROOT, "venv", "bin", "python3")


def test_jwt_secret_required():
    """Verify importing middleware/auth without EMO_JWT_SECRET raises RuntimeError."""
    python = _VENV_PYTHON if os.path.exists(_VENV_PYTHON) else sys.executable
    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "import os\n"
        "os.environ.pop('EMO_JWT_SECRET', None)\n"
        "try:\n"
        "    import middleware.auth\n"
        "    print('ERROR: no exception raised')\n"
        "except RuntimeError as e:\n"
        "    print(f'OK: {e}')\n" % PROJECT_ROOT
    )
    env = {k: v for k, v in os.environ.items() if k != "EMO_JWT_SECRET"}
    env.setdefault("PYTHONPATH", PROJECT_ROOT)
    result = subprocess.run(
        [python, "-c", code],
        capture_output=True, text=True,
        env=env,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "OK:" in result.stdout, f"Expected RuntimeError, got: {result.stdout}"


def test_sandbox_executor_no_eval_exec():
    """Verify sandbox_executor source has zero eval/exec calls in code AST."""
    import ast

    module_path = os.path.join(
        PROJECT_ROOT, "core", "runtime", "sandbox", "sandbox_executor.py"
    )
    with open(module_path) as f:
        tree = ast.parse(f.read())

    bad_names = {"eval", "exec", "__import__"}

    class EvalExecFinder(ast.NodeVisitor):
        def __init__(self):
            self.found = []

        def visit_Call(self, node):
            if isinstance(node.func, ast.Name) and node.func.id in bad_names:
                self.found.append((node.func.id, node.lineno))
            if isinstance(node.func, ast.Attribute):
                if (isinstance(node.func.value, ast.Attribute)
                        and isinstance(node.func.value.value, ast.Name)
                        and node.func.value.value.id == "builtins"
                        and node.func.attr in bad_names):
                    self.found.append((f"builtins.{node.func.attr}", node.lineno))
            self.generic_visit(node)

        def visit_Attribute(self, node):
            if (isinstance(node.value, ast.Name)
                    and node.value.id == "builtins"
                    and node.attr in bad_names):
                self.found.append((f"builtins.{node.attr}", node.lineno))
            self.generic_visit(node)

    finder = EvalExecFinder()
    finder.visit(tree)
    assert not finder.found, (
        f"Found banned functions: {finder.found}"
    )


def test_gitignore_excludes_db():
    """Verify .gitignore excludes *.db pattern."""
    with open(os.path.join(PROJECT_ROOT, ".gitignore")) as f:
        content = f.read()
    assert "*.db" in content


def test_db_files_untracked():
    """Verify no *.db files remain tracked by git."""
    result = subprocess.run(
        ["git", "ls-files", "*.db"],
        capture_output=True, text=True,
        cwd=PROJECT_ROOT,
    )
    tracked = [f for f in result.stdout.strip().split("\n") if f.strip()]
    assert not tracked, f"DB files still tracked: {tracked}"
