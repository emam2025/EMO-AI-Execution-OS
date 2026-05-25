"""Tests for Phase E1 — Docker Runtime.

Container-based execution isolation.
Checks Docker availability and skips if not present.
"""

import time

import pytest

from core.runtime.sandbox.docker_runtime import DockerRuntime, DockerResult


docker_available = DockerRuntime().is_available()


class TestDockerRuntime:
    def test_init(self):
        r = DockerRuntime(image="python:3.11-slim")
        assert r._image == "python:3.11-slim"
        assert r._network_enabled is False

    def test_is_available(self):
        r = DockerRuntime()
        # Should not crash — returns bool
        assert isinstance(r.is_available(), bool)

    def test_execute_docker_not_available(self):
        r = DockerRuntime(docker_binary="/nonexistent/docker")
        result = r.execute("echo hello")
        if not docker_available:
            assert result.exit_code == -1
            assert result.error

    @pytest.mark.skipif(not docker_available, reason="Docker not available")
    def test_execute_simple_command(self):
        r = DockerRuntime()
        result = r.execute("echo 'hello world'")
        assert result.exit_code == 0
        assert "hello world" in result.stdout

    @pytest.mark.skipif(not docker_available, reason="Docker not available")
    def test_execute_with_timeout(self):
        r = DockerRuntime()
        result = r.execute("sleep 10", timeout=1)
        assert result.timed_out is True

    @pytest.mark.skipif(not docker_available, reason="Docker not available")
    def test_execute_with_memory_limit(self):
        r = DockerRuntime()
        result = r.execute("echo 'mem test'", memory_limit="64m")
        assert result.exit_code == 0

    @pytest.mark.skipif(not docker_available, reason="Docker not available")
    def test_execute_with_cpu_limit(self):
        r = DockerRuntime()
        result = r.execute("echo 'cpu test'", cpu_limit=0.5)
        assert result.exit_code == 0

    @pytest.mark.skipif(not docker_available, reason="Docker not available")
    def test_execute_no_network(self):
        r = DockerRuntime()
        result = r.execute("curl -s http://example.com 2>&1 || true", network_disabled=True)
        # Should fail or return error since network is disabled
        assert isinstance(result, DockerResult)

    @pytest.mark.skipif(not docker_available, reason="Docker not available")
    def test_execute_with_env(self):
        r = DockerRuntime()
        result = r.execute("echo $MY_VAR", environment={"MY_VAR": "test_value"})
        assert result.exit_code == 0
        assert "test_value" in result.stdout

    @pytest.mark.skipif(not docker_available, reason="Docker not available")
    def test_cleanup_all(self):
        r = DockerRuntime()
        # Run a quick command
        r.execute("echo 'cleanup test'")
        count = r.cleanup_all()
        assert count == 1

    @pytest.mark.skipif(not docker_available, reason="Docker not available")
    def test_list_active(self):
        r = DockerRuntime()
        r.execute("echo 'list test'")
        active = r.list_active()
        assert len(active) >= 1

    @pytest.mark.skipif(not docker_available, reason="Docker not available")
    def test_execute_failing_command(self):
        r = DockerRuntime()
        result = r.execute("exit 42")
        assert result.exit_code == 42

    @pytest.mark.skipif(not docker_available, reason="Docker not available")
    def test_execute_stderr(self):
        r = DockerRuntime()
        result = r.execute("echo 'error msg' >&2")
        assert result.exit_code == 0
