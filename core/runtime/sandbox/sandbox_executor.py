"""SandboxExecutor — Subprocess Isolation with Resource Limits.

Executes Python scripts in isolated subprocesses with enforced CPU
and memory limits via resource.setrlimit(). Kill-safe cleanup via
finally block. Publishes telemetry events via IEventBus.

Ref: Phase E.1.2 — Sandboxed Executor (Subprocess Isolation)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import resource
import subprocess
import sys
import tempfile
import time
from typing import TYPE_CHECKING, Any, Optional

from core.models.sandbox import SandboxContext, SandboxResult

if TYPE_CHECKING:
    from core.interfaces.event_bus import IEventBus

logger = logging.getLogger(__name__)


class ResourceLimitExceeded(Exception):
    """Raised when a subprocess exceeds its resource limits."""


class SandboxExecutor:
    """Subprocess-only sandbox executor with resource limits.

    Each execution spawns a separate subprocess running a Python script.
    No threading is used. Resource limits (CPU, memory) are enforced
    via resource.setrlimit() in the child process via preexec_fn.
    """

    def __init__(self, event_bus: Optional[IEventBus] = None) -> None:
        self._event_bus = event_bus

    def execute(
        self,
        script: str,
        context: SandboxContext,
    ) -> SandboxResult:
        """Execute a Python script in an isolated subprocess.

        Args:
            script: Python source code to execute in the subprocess.
            context: Sandbox context with resource limits.

        Returns:
            SandboxResult with output, exit code, and telemetry.
        """
        self._publish_event(
            "EXECUTION_STARTED",
            {
                "tool_id": context.tool_id,
                "timeout_seconds": context.timeout_seconds,
                "max_memory_mb": context.max_memory_mb,
                "max_cpu_seconds": context.max_cpu_seconds,
            },
        )

        worker_path: Optional[str] = None
        proc: Optional[subprocess.Popen] = None
        start_time = time.time()

        try:
            worker_path = self._write_script(script)
            proc = self._spawn_subprocess(worker_path, context)

            try:
                stdout_bytes, stderr_bytes = proc.communicate(
                    timeout=context.timeout_seconds
                )
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                duration = time.time() - start_time
                self._publish_event(
                    "EXECUTION_FAILED",
                    {"tool_id": context.tool_id, "reason": "timeout", "duration_seconds": duration},
                )
                self._publish_event(
                    "RESOURCE_LIMIT_EXCEEDED",
                    {"tool_id": context.tool_id, "limit_type": "timeout", "timeout_seconds": context.timeout_seconds},
                )
                return SandboxResult(
                    success=False,
                    error=f"Execution timed out after {context.timeout_seconds}s",
                    exit_code=-1,
                    duration_seconds=duration,
                    timed_out=True,
                    killed=True,
                )

            duration = time.time() - start_time
            stdout = stdout_bytes.decode(errors="replace") if stdout_bytes else ""
            stderr = stderr_bytes.decode(errors="replace") if stderr_bytes else ""

            if proc.returncode != 0:
                self._publish_event(
                    "EXECUTION_FAILED",
                    {"tool_id": context.tool_id, "exit_code": proc.returncode, "duration_seconds": duration},
                )
                return SandboxResult(
                    success=False,
                    output=stdout,
                    error=stderr or f"Exit code {proc.returncode}",
                    exit_code=proc.returncode,
                    duration_seconds=duration,
                )

            result = self._parse_output(stdout)
            self._publish_event(
                "EXECUTION_COMPLETED",
                {"tool_id": context.tool_id, "exit_code": 0, "duration_seconds": duration},
            )
            return SandboxResult(
                success=True,
                output=result.get("result", stdout),
                exit_code=0,
                duration_seconds=duration,
            )

        except ResourceLimitExceeded:
            self._publish_event(
                "RESOURCE_LIMIT_EXCEEDED",
                {"tool_id": context.tool_id, "limit_type": "memory", "max_memory_mb": context.max_memory_mb},
            )
            raise

        except Exception as e:
            duration = time.time() - start_time
            self._publish_event(
                "EXECUTION_FAILED",
                {"tool_id": context.tool_id, "error": str(e), "duration_seconds": duration},
            )
            return SandboxResult(
                success=False,
                error=f"{type(e).__name__}: {e}",
                exit_code=-1,
                duration_seconds=duration,
            )

        finally:
            if proc is not None and proc.poll() is None:
                try:
                    proc.kill()
                    proc.wait(timeout=5.0)
                except Exception:
                    pass
            if worker_path is not None:
                self._cleanup_worker(worker_path)

    def _spawn_subprocess(
        self, worker_path: str, context: SandboxContext
    ) -> subprocess.Popen:
        """Spawn a subprocess with resource limits."""
        memory_bytes = context.max_memory_mb * 1024 * 1024
        cpu_seconds = int(context.max_cpu_seconds)

        def preexec_fn() -> None:
            try:
                if memory_bytes > 0:
                    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
                if cpu_seconds > 0:
                    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
            except (ValueError, OSError):
                pass

        return subprocess.Popen(
            [sys.executable, worker_path],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=preexec_fn,
        )

    @staticmethod
    def _write_script(script: str) -> str:
        """Write a script to a temp file for subprocess execution."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(script)
            return f.name

    @staticmethod
    def _parse_output(raw: str) -> dict:
        try:
            return json.loads(raw.strip())
        except (json.JSONDecodeError, ValueError):
            return {"status": "completed", "result": raw.strip()}

    @staticmethod
    def _cleanup_worker(path: str) -> None:
        try:
            if os.path.exists(path):
                os.unlink(path)
        except OSError:
            pass

    def _publish_event(self, event_type: str, payload: dict) -> None:
        """Publish a telemetry event via IEventBus."""
        if self._event_bus is None:
            return
        try:
            from core.models.event import EventTopic, ExecutionEvent

            topic_map = {
                "EXECUTION_STARTED": EventTopic.EXECUTION_STARTED,
                "EXECUTION_COMPLETED": EventTopic.EXECUTION_COMPLETED,
                "EXECUTION_FAILED": EventTopic.EXECUTION_FAILED,
                "RESOURCE_LIMIT_EXCEEDED": EventTopic.RESOURCE_LIMIT_EXCEEDED,
            }
            topic = topic_map.get(event_type)
            if topic is None:
                return

            event = ExecutionEvent(
                topic=topic,
                payload=payload,
                trace_id=f"sandbox-{payload.get('tool_id', 'unknown')}",
            )
            loop = asyncio.get_running_loop()
            loop.create_task(self._event_bus.publish(topic, event))
        except RuntimeError:
            pass
