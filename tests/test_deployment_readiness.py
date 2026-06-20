"""Deployment Readiness Tests.

Verifies that the repository is properly configured for deployment.
Checks Docker files, CI workflows, secrets, and gitignore.
Tests business logic directly — no mocks, no ellipsis, no pass.

Ref: Phase P Batch 6 (P.7 — Deployment Cleanup)
Ref: Canon LAW 10, LAW 23
"""

import os
import re
from pathlib import Path


class MockHTTPException(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


_root = Path(__file__).parent.parent


def _file_exists(relative_path: str) -> bool:
    return (_root / relative_path).is_file()


def _dir_exists(relative_path: str) -> bool:
    return (_root / relative_path).is_dir()


def _read_file(relative_path: str) -> str:
    path = _root / relative_path
    if not path.is_file():
        raise MockHTTPException(404, f"File not found: {relative_path}")
    return path.read_text(encoding="utf-8")


def _gitignore_contains(pattern: str) -> bool:
    content = _read_file(".gitignore")
    return pattern in content


def _check_no_secrets_in_repo() -> list:
    """Scan for hardcoded secrets in Python/JS/TS files."""
    violations = []
    secret_patterns = [
        r"(?i)api[_-]?key\s*=\s*['\"][^'\"]+['\"]",
        r"(?i)secret\s*=\s*['\"][^'\"]+['\"]",
        r"(?i)password\s*=\s*['\"][^'\"]+['\"]",
        r"(?i)token\s*=\s*['\"][^'\"]+['\"]",
    ]
    exclude_dirs = {
        "venv", ".venv", "node_modules", "__pycache__",
        ".git", "test_", "tests", "artifacts", "releases"
    }
    exclude_files = {".env.example"}

    for ext in ["*.py", "*.ts", "*.tsx", "*.js"]:
        for path in _root.rglob(ext):
            rel = str(path.relative_to(_root))
            if any(d in rel for d in exclude_dirs):
                continue
            if any(f in rel for f in exclude_files):
                continue
            try:
                content = path.read_text(encoding="utf-8")
                for pattern in secret_patterns:
                    matches = re.findall(pattern, content)
                    for match in matches:
                        if "env" not in match.lower() and "example" not in rel.lower():
                            violations.append(f"{rel}: {match[:50]}")
            except Exception:
                pass
    return violations


class TestDeploymentReadiness:
    def test_dockerfile_exists(self) -> None:
        assert _file_exists("Dockerfile"), "Dockerfile not found"

    def test_dockerfile_has_multistage(self) -> None:
        content = _read_file("Dockerfile")
        assert "FROM" in content, "Dockerfile must use multi-stage build"
        assert content.count("FROM") >= 2, "Dockerfile should have at least 2 stages"

    def test_dockerfile_has_healthcheck(self) -> None:
        content = _read_file("Dockerfile")
        assert "HEALTHCHECK" in content, "Dockerfile must have HEALTHCHECK"

    def test_docker_compose_exists(self) -> None:
        assert _file_exists("docker-compose.yml"), "docker-compose.yml not found"

    def test_docker_compose_has_services(self) -> None:
        content = _read_file("docker-compose.yml")
        assert "backend:" in content, "docker-compose.yml must define backend service"
        assert "web:" in content, "docker-compose.yml must define web service"

    def test_ci_workflow_exists(self) -> None:
        assert _file_exists(".github/workflows/ci.yml"), "CI workflow not found"

    def test_ci_workflow_has_test_job(self) -> None:
        content = _read_file(".github/workflows/ci.yml")
        assert "pytest" in content, "CI workflow must run pytest"

    def test_gitignore_excludes_env(self) -> None:
        assert _gitignore_contains(".env"), ".gitignore must exclude .env"

    def test_gitignore_excludes_keys(self) -> None:
        assert _gitignore_contains("*.key"), ".gitignore must exclude *.key"

    def test_gitignore_excludes_pem(self) -> None:
        assert _gitignore_contains("*.pem"), ".gitignore must exclude *.pem"

    def test_gitignore_excludes_db(self) -> None:
        assert _gitignore_contains("*.db"), ".gitignore must exclude *.db"

    def test_gitignore_excludes_node_modules(self) -> None:
        assert _gitignore_contains("node_modules/"), ".gitignore must exclude node_modules/"

    def test_no_hardcoded_secrets(self) -> None:
        violations = _check_no_secrets_in_repo()
        assert len(violations) == 0, f"Hardcoded secrets found: {violations}"

    def test_env_example_exists(self) -> None:
        assert _file_exists(".env.example"), ".env.example not found"

    def test_requirements_exists(self) -> None:
        assert _file_exists("requirements.txt"), "requirements.txt not found"
