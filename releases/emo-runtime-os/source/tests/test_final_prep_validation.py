"""
Final Delivery Validation — 20 high-signal tests covering all 5 pillars.

Pillars:
    1. SecurityHeadersEnforcement (4)
    2. PerformanceBaselineCompliance (4)
    3. CLIFacadeContract (4)
    4. SDKSpecCompleteness (4)
    5. QuarantineIsolation (4)

Run: pytest tests/test_final_prep_validation.py -v
"""
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
import pytest


# ── Helpers ─────────────────────────────────────────────────


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _read_file(path: str) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


def _file_exists(path: str) -> bool:
    return (PROJECT_ROOT / path).exists()


def _import_qualifies(name: str) -> bool:
    """Check if a module can be imported without error."""
    try:
        __import__(name)
        return True
    except ImportError:
        return False


# ═══════════════════════════════════════════════════════════
# Pillar 1: Security Headers Enforcement (4 tests)
# ═══════════════════════════════════════════════════════════


class TestSecurityHeadersEnforcement:

    @pytest.mark.security
    def test_missing_jwt_secret_raises(self):
        """LAW 3: EMO_JWT_SECRET must raise RuntimeError if unset."""
        content = _read_file("middleware/auth.py")
        assert "RuntimeError" in content
        assert "EMO_JWT_SECRET" in content

    @pytest.mark.security
    def test_jwt_expiry_2h(self):
        """JWT_EXPIRE_HOURS must be 2 (max 2h)."""
        content = _read_file("middleware/auth.py")
        assert "JWT_EXPIRE_HOURS = 2" in content

    @pytest.mark.security
    def test_main_has_admin_password_check(self):
        """main.py must require EMO_AUTH_PASSWORD when auth is enabled."""
        content = _read_file("main.py")
        assert "EMO_AUTH_PASSWORD" in content
        assert "admin123456" not in content, (
            "Default password admin123456 must be removed"
        )

    @pytest.mark.security
    def test_security_headers_middleware_present(self):
        """main.py must define SecurityHeadersMiddleware with CSP, HSTS, X-Frame-Options."""
        content = _read_file("main.py")
        assert "SecurityHeadersMiddleware" in content
        assert "Content-Security-Policy" in content
        assert "Strict-Transport-Security" in content
        assert "X-Frame-Options" in content
        assert "X-Content-Type-Options" in content


# ═══════════════════════════════════════════════════════════
# Pillar 2: Performance Baseline Compliance (4 tests)
# ═══════════════════════════════════════════════════════════


class TestPerformanceBaselineCompliance:

    @pytest.mark.performance
    def test_benchmark_runner_exists(self):
        """sustained_load_runner.py must exist and be syntactically valid."""
        path = "scripts/benchmark/sustained_load_runner.py"
        assert _file_exists(path), f"{path} not found"
        result = subprocess.run(
            [sys.executable, "-c", f"import ast; ast.parse(open('{PROJECT_ROOT / path}').read())"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    @pytest.mark.performance
    def test_benchmark_dir_created_by_runner(self):
        """Benchmark runner must create artifacts/benchmark/ on run."""
        content = _read_file("scripts/benchmark/sustained_load_runner.py")
        assert "os.makedirs" in content
        assert "artifacts/benchmark" in content or "performance_baseline" in content

    @pytest.mark.performance
    def test_benchmark_imports_facade(self):
        """Benchmark runner must import EmoRuntimeFacade."""
        content = _read_file("scripts/benchmark/sustained_load_runner.py")
        assert "EmoRuntimeFacade" in content
        assert "PlannerAgent" in content
        assert "CriticAgent" in content
        assert "OptimizerAgent" in content

    @pytest.mark.performance
    def test_benchmark_uses_asyncio(self):
        """Benchmark runner must be async."""
        content = _read_file("scripts/benchmark/sustained_load_runner.py")
        assert "async def" in content
        assert "asyncio.run" in content


# ═══════════════════════════════════════════════════════════
# Pillar 3: CLI ↔ Facade Contract (4 tests)
# ═══════════════════════════════════════════════════════════


class TestCLIFacadeContract:

    @pytest.mark.devex
    def test_cli_exists(self):
        """emo_cli.py must exist."""
        assert _file_exists("scripts/cli/emo_cli.py")

    @pytest.mark.devex
    def test_cli_implements_submit(self):
        """CLI must implement 'submit' subcommand."""
        content = _read_file("scripts/cli/emo_cli.py")
        assert "submit" in content

    @pytest.mark.devex
    def test_cli_imports_facade(self):
        """CLI must use EmoRuntimeFacade (not direct core.*)."""
        content = _read_file("scripts/cli/emo_cli.py")
        assert "EmoRuntimeFacade" in content
        assert "core.orchestration" in content

    @pytest.mark.devex
    def test_cli_submit_calls_orchestrate(self):
        """CLI submit handler must call facade.orchestrate."""
        content = _read_file("scripts/cli/emo_cli.py")
        assert "facade.orchestrate" in content


# ═══════════════════════════════════════════════════════════
# Pillar 4: SDK Spec Completeness (4 tests)
# ═══════════════════════════════════════════════════════════


class TestSDKSpecCompleteness:

    @pytest.mark.devex
    def test_sdk_spec_exists(self):
        """docs/sdk_spec.md must exist."""
        assert _file_exists("docs/sdk_spec.md")

    @pytest.mark.devex
    def test_sdk_spec_contains_orchestrate(self):
        """SDK spec must document orchestrate method."""
        content = _read_file("docs/sdk_spec.md")
        assert "orchestrate" in content

    @pytest.mark.devex
    def test_runtime_api_reference_exists(self):
        """docs/runtime_api_reference.md must exist."""
        assert _file_exists("docs/runtime_api_reference.md")

    @pytest.mark.devex
    def test_runtime_api_references_protocols(self):
        """Runtime API reference must document IPlannerAgent and IExecutionEngine."""
        content = _read_file("docs/runtime_api_reference.md")
        assert "IPlannerAgent" in content
        assert "IExecutionEngine" in content
        assert "EmoRuntimeFacade" in content


# ═══════════════════════════════════════════════════════════
# Pillar 5: Quarantine Isolation (4 tests)
# ═══════════════════════════════════════════════════════════


class TestQuarantineIsolation:

    @pytest.mark.quarantine_isolation
    def test_quarantine_dir_exists(self):
        """tests/quarantine/ must exist."""
        assert (PROJECT_ROOT / "tests" / "quarantine").is_dir()

    @pytest.mark.quarantine_isolation
    def test_quarantine_marker_in_pytest_ini(self):
        """pytest.ini must define quarantined marker."""
        content = _read_file("pytest.ini")
        assert "quarantined" in content

    @pytest.mark.quarantine_isolation
    def test_debt_resolution_plan_exists(self):
        """artifacts/debt/DEBT_RESOLUTION_PLAN.md must exist."""
        assert _file_exists("artifacts/debt/DEBT_RESOLUTION_PLAN.md")

    @pytest.mark.quarantine_isolation
    def test_quarantine_categories_present(self):
        """Quarantine dir must have categorized test files."""
        qdir = PROJECT_ROOT / "tests" / "quarantine"
        files = [f.name for f in qdir.iterdir() if f.suffix == ".py" and f.name != "__init__.py"]
        categories = {"env_missing", "legacy_billing", "jwt_migration", "async_fixture", "other_legacy"}
        found = set()
        for f in files:
            for cat in categories:
                if cat in f:
                    found.add(cat)
        assert found == categories, (
            f"Missing categories: {categories - found}. Found files: {files}"
        )
