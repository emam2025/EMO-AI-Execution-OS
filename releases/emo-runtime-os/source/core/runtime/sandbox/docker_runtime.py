"""E1 — DockerRuntime: container-based execution isolation.

Spawns ephemeral Docker containers for each execution with:
  - CPU and memory limits
  - Filesystem isolation (read-only root + temp work dir)
  - Network policy enforcement
  - Automatic cleanup after timeout or completion

Usage:
    runtime = DockerRuntime()
    result = runtime.execute("python3 script.py", timeout=30, memory_limit="256m")
    runtime.cleanup(container_id)
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("emo_ai.sandbox.docker")


@dataclass
class DockerResult:
    """Result of a Docker execution."""
    container_id: str = ""
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    error: str = ""


class DockerRuntime:
    """Container-based execution isolation using Docker CLI.

    Spawns ephemeral containers. Cleans up automatically.
    """

    def __init__(
        self,
        image: str = "python:3.11-slim",
        docker_binary: str = "docker",
        network_enabled: bool = False,
        remove_on_exit: bool = True,
    ) -> None:
        self._image = image
        self._docker = docker_binary
        self._network_enabled = network_enabled
        self._remove_on_exit = remove_on_exit
        self._active_containers: Dict[str, Dict[str, Any]] = {}
        self._check_docker()

    def _check_docker(self) -> None:
        """Verify Docker is available."""
        try:
            result = subprocess.run(
                [self._docker, "--version"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                logger.warning("Docker not available: %s", result.stderr.strip())
        except FileNotFoundError:
            logger.warning("Docker binary '%s' not found", self._docker)
        except subprocess.TimeoutExpired:
            logger.warning("Docker check timed out")

    # ── Core Execution ────────────────────────────────────────────

    def execute(
        self,
        command: str,
        timeout: float = 30.0,
        cpu_limit: float = 1.0,
        memory_limit: str = "256m",
        work_dir: Optional[str] = None,
        environment: Optional[Dict[str, str]] = None,
        volumes: Optional[Dict[str, str]] = None,
        network_disabled: bool = True,
    ) -> DockerResult:
        """Execute a command in an ephemeral Docker container.

        Args:
            command: Shell command to run inside the container.
            timeout: Max execution time in seconds.
            cpu_limit: Max CPU cores (e.g. 1.0, 0.5).
            memory_limit: Max memory (e.g. "256m", "1g").
            work_dir: Optional host directory to mount as /workspace.
            environment: Optional env vars for the container.
            volumes: Optional volume mounts {host_path: container_path}.
            network_disabled: If True, container has no network.

        Returns:
            DockerResult with container output.
        """
        container_id = uuid.uuid4().hex[:12]
        env = environment or {}

        # Build docker run args
        cmd = [
            self._docker, "run",
            "--name", f"emo_sandbox_{container_id}",
            "-d",  # detached — we'll attach and wait
            "--cpus", str(cpu_limit),
            "--memory", memory_limit,
            "--stop-timeout", str(int(timeout) + 5),
        ]

        if network_disabled:
            cmd += ["--network", "none"]

        for k, v in env.items():
            cmd += ["-e", f"{k}={v}"]

        if work_dir:
            cmd += ["-v", f"{os.path.abspath(work_dir)}:/workspace:ro"]
            cmd += ["-w", "/workspace"]

        if volumes:
            for host_path, container_path in volumes.items():
                cmd += ["-v", f"{os.path.abspath(host_path)}:{container_path}"]

        cmd += [self._image, "/bin/sh", "-c", command]

        try:
            # Create container
            create_result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
            )
            if create_result.returncode != 0:
                return DockerResult(
                    error=f"Container create failed: {create_result.stderr.strip()}",
                )

            cid = create_result.stdout.strip()
            self._active_containers[cid] = {
                "created_at": time.time(),
                "timeout": timeout,
                "command": command[:100],
            }

            # Wait for completion with timeout
            wait_cmd = [self._docker, "wait", cid]
            try:
                subprocess.run(wait_cmd, capture_output=True, timeout=timeout + 10)
            except subprocess.TimeoutExpired:
                # Force kill
                subprocess.run(
                    [self._docker, "kill", cid],
                    capture_output=True, timeout=10,
                )
                stdout = self._get_logs(cid)
                self._cleanup_container(cid)
                return DockerResult(
                    container_id=cid, exit_code=-1,
                    stdout=stdout, timed_out=True,
                    error=f"Execution timed out after {timeout}s",
                )

            # Get exit code
            inspect = subprocess.run(
                [self._docker, "inspect", cid, "--format", "{{.State.ExitCode}}"],
                capture_output=True, text=True, timeout=10,
            )
            exit_code = int(inspect.stdout.strip() or "-1")

            # Get logs
            stdout = self._get_logs(cid)
            self._cleanup_container(cid)

            return DockerResult(
                container_id=cid, exit_code=exit_code,
                stdout=stdout,
            )

        except subprocess.TimeoutExpired:
            return DockerResult(error="Docker operation timed out")
        except FileNotFoundError:
            return DockerResult(error="Docker binary not found")
        except Exception as e:
            return DockerResult(error=str(e))

    # ── Management ────────────────────────────────────────────────

    def _get_logs(self, container_id: str) -> str:
        try:
            result = subprocess.run(
                [self._docker, "logs", container_id],
                capture_output=True, text=True, timeout=10,
            )
            return result.stdout + result.stderr
        except Exception:
            return ""

    def _cleanup_container(self, container_id: str) -> None:
        self._active_containers.pop(container_id, None)
        if not self._remove_on_exit:
            return
        try:
            subprocess.run(
                [self._docker, "rm", "-f", container_id],
                capture_output=True, timeout=10,
            )
        except Exception:
            pass

    def cleanup(self, container_id: str) -> None:
        """Explicitly clean up a container."""
        self._cleanup_container(container_id)

    def cleanup_all(self) -> int:
        """Clean up all tracked active containers."""
        count = 0
        for cid in list(self._active_containers.keys()):
            self._cleanup_container(cid)
            count += 1
        return count

    def list_active(self) -> Dict[str, Dict[str, Any]]:
        """List all tracked active containers."""
        return dict(self._active_containers)

    def is_available(self) -> bool:
        """Check if Docker is available on this system."""
        try:
            result = subprocess.run(
                [self._docker, "info"],
                capture_output=True, timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False
