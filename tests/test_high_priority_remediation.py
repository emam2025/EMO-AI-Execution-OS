"""HIGH-001A — High-Priority Remediation Integration Tests.

Covers all 4 fixes across boundaries:
  1. SQL injection hardening (frozenset whitelist)
  2. LAW 13 permanent enforcement (AST scanner)
  3. JWT lifecycle (2h expiry, refresh rotation)
  4. /api/status auth protection

Total: 18 tests expected after including files:
  - test_sql_injection_prevention.py  (7 tests)
  - test_law13_ast_enforcement.py     (4 tests)
  - test_jwt_lifecycle_security.py   (8 tests)
  - test_status_endpoint_auth_protection.py (4 tests)
"""

import os
import subprocess
import sys

import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("EMO_JWT_SECRET", "test-high-priority-secret")


class TestRemediationIntegration:
    """Cross-cutting integration checks.

    These tests verify that the enforcement mechanisms are wired
    end-to-end and that the fixes compose correctly.
    """

    def test_all_security_test_files_exist(self):
        files = [
            "test_sql_injection_prevention.py",
            "test_law13_ast_enforcement.py",
            "test_jwt_lifecycle_security.py",
            "test_status_endpoint_auth_protection.py",
        ]
        for f in files:
            path = os.path.join(PROJECT_ROOT, "tests", f)
            assert os.path.exists(path), f"Missing test file: {f}"

    def test_law13_ast_scanner_executable(self):
        scanner = os.path.join(
            PROJECT_ROOT, "scripts", "enforce", "law13_ast_check.py"
        )
        assert os.path.exists(scanner), "LAW 13 scanner missing"
        result = subprocess.run(
            [sys.executable, scanner],
            capture_output=True, text=True,
            cwd=PROJECT_ROOT,
        )
        assert result.returncode in (0, 1)
        assert "LAW 13" in result.stdout

    def test_pre_commit_hook_exists(self):
        hook = os.path.join(PROJECT_ROOT, ".githooks", "pre-commit")
        assert os.path.exists(hook), "Pre-commit hook missing"
        with open(hook) as f:
            content = f.read()
        assert "law13_ast_check" in content

    def test_ci_workflow_exists(self):
        workflow = os.path.join(
            PROJECT_ROOT, ".github", "workflows", "law13-enforce.yml"
        )
        assert os.path.exists(workflow), "CI workflow missing"
        with open(workflow) as f:
            content = f.read()
        assert "law13_ast_check" in content

    def test_invalid_column_error_is_security_error(self):
        from core.db import InvalidColumnError, SecurityError
        assert issubclass(InvalidColumnError, SecurityError)

    def test_jwt_expiry_constant_updated(self):
        from middleware.auth import JWT_EXPIRE_HOURS
        assert JWT_EXPIRE_HOURS == 2

    def test_refresh_store_has_used_flag(self):
        from middleware.auth import generate_refresh_token, _refresh_store
        import hashlib
        uid = "integration-test-user"
        raw = generate_refresh_token(uid)
        h = hashlib.sha256(f"{raw}:{uid}".encode()).hexdigest()
        entry = _refresh_store.get(h)
        assert entry is not None
        assert "used" in entry
        assert entry["used"] is False  # not yet validated

    def test_core_db_security_logger_exists(self):
        """Verify core/db.py has a security logger for SIEM-ready audit."""
        from core.db import logger
        assert logger is not None
        assert hasattr(logger, "warning")
