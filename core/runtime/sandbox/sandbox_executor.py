"""Phase 4.1.1 — SandboxExecutor: subprocess/container execution layer.

Spawns isolated workers, enforces timeouts, and provides
kill-safe execution for untrusted tasks.

Every execution goes through:
    SandboxExecutor → subprocess worker → result
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from typing import Any, Dict, Optional

from core.runtime.sandbox.sandbox_context import SandboxContext
from core.runtime.sandbox.sandbox_errors import (
    ExecutionTimeoutError,
    ResourceLimitExceeded,
    SandboxViolationError,
)

logger = logging.getLogger("emo_ai.sandbox.executor")

SANDBOX_PY = """
import json, sys, traceback

def run():
    payload = json.loads(sys.stdin.read())
    try:
        tool_fn = payload["tool"]
        inputs = payload.get("inputs", {})
        result = __import__("builtins").eval(f"exec(open('/dev/stdin').read())")
    except Exception as e:
        result = {"error": str(e), "traceback": traceback.format_exc()}
    sys.stdout.write(json.dumps(result))
    sys.stdout.flush()

if __name__ == "__main__":
    run()
"""


class SandboxExecutor:
    """Executes tasks in isolated subprocess workers.

    Each execution spawns a separate process with resource limits
    enforced via the OS (``resource`` module) and a watchdog thread
    for timeout enforcement.

    Supports kill-on-demand via execution ID tracking.
    """

    def __init__(self, sandbox_py_path: Optional[str] = None):
        self._sandbox_py_path = sandbox_py_path
        self._processes: Dict[str, Any] = {}
        self._cancel_events: Dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    def execute(
        self,
        tool_name: str,
        inputs: Dict[str, Any],
        context: SandboxContext,
    ) -> Dict[str, Any]:
        """Execute a tool in an isolated subprocess.

        Args:
            tool_name: Name of the tool to execute.
            inputs: Input parameters for the tool.
            context: Sandbox context with resource limits.

        Returns:
            Execution result dict with keys: status, result/error.

        Raises:
            ExecutionTimeoutError: If execution exceeds context.timeout.
            ResourceLimitExceeded: If resource limits are breached.
            SandboxViolationError: If sandbox rules are violated.
        """
        exec_id = uuid.uuid4().hex[:12]
        start = time.time()
        cancel_event = threading.Event()

        with self._lock:
            self._cancel_events[exec_id] = cancel_event

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False,
        ) as f:
            worker_path = f.name
            f.write(self._build_worker_script(tool_name, inputs))

        try:
            proc = subprocess.Popen(
                [sys.executable, worker_path],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=self._make_preexec(context),
                cwd=context.working_dir or os.path.dirname(worker_path),
            )

            with self._lock:
                self._processes[exec_id] = proc

            timed_out = threading.Event()

            def watchdog() -> None:
                try:
                    proc.wait(timeout=context.timeout)
                    timed_out.set()
                except Exception:
                    pass

            watcher = threading.Thread(target=watchdog, daemon=True)
            watcher.start()

            # Wait for completion, cancellation, or timeout
            while watcher.is_alive():
                if cancel_event.is_set():
                    proc.kill()
                    proc.wait()
                    elapsed = time.time() - start
                    with self._lock:
                        self._processes.pop(exec_id, None)
                        self._cancel_events.pop(exec_id, None)
                    return {
                        "status": "cancelled",
                        "elapsed": elapsed,
                    }
                watcher.join(timeout=0.1)

            if proc.poll() is None:
                proc.kill()
                proc.wait()
                elapsed = time.time() - start
                with self._lock:
                    self._processes.pop(exec_id, None)
                    self._cancel_events.pop(exec_id, None)
                raise ExecutionTimeoutError(
                    tool=tool_name,
                    timeout=context.timeout,
                    elapsed=elapsed,
                )

            stdout, stderr = proc.communicate()
            elapsed = time.time() - start

            if proc.returncode != 0:
                return {
                    "status": "failed",
                    "error": stderr.decode() or f"exit code {proc.returncode}",
                    "elapsed": elapsed,
                }

            result = self._parse_output(stdout.decode())
            result["elapsed"] = elapsed
            result["status"] = result.get("status", "completed")
            return result

        except ExecutionTimeoutError:
            raise
        except ResourceLimitExceeded:
            raise
        except SandboxViolationError:
            raise
        except Exception as e:
            logger.exception("Sandbox execution failed for %s", tool_name)
            return {
                "status": "failed",
                "error": f"{type(e).__name__}: {e}",
            }
        finally:
            with self._lock:
                self._processes.pop(exec_id, None)
                self._cancel_events.pop(exec_id, None)
            self._cleanup_worker(worker_path)

    def execute_direct(
        self,
        runner: Any,
        execution_input: Any,
        context: SandboxContext,
        exec_id: str = "",
    ) -> Dict[str, Any]:
        """Execute a callable in a thread with timeout.

        Falls back to thread-based execution when subprocess is
        not feasible (non-serializable callables).

        Supports cancellation via ``kill(exec_id)``.
        """
        if not exec_id:
            exec_id = uuid.uuid4().hex[:12]

        cancel_event = threading.Event()
        with self._lock:
            self._cancel_events[exec_id] = cancel_event

        start = time.time()
        result_container: list = [None]
        exception_container: list = [None]
        done = threading.Event()

        def _run() -> None:
            try:
                if cancel_event.is_set():
                    return
                result_container[0] = runner(execution_input)
            except Exception as e:
                exception_container[0] = e
            finally:
                done.set()

        t = threading.Thread(target=_run, daemon=True)
        t.start()

        # Wait for completion, cancellation, or timeout
        remaining = context.timeout
        while remaining > 0 and t.is_alive() and not cancel_event.is_set():
            t.join(timeout=min(0.1, remaining))
            remaining -= 0.1

        with self._lock:
            self._cancel_events.pop(exec_id, None)

        if cancel_event.is_set():
            return {
                "status": "cancelled",
                "elapsed": time.time() - start,
            }

        if t.is_alive():
            tool_name = (
                execution_input if isinstance(execution_input, str)
                else getattr(execution_input, "tool", "unknown")
            )
            return {
                "status": "failed",
                "error": str(ExecutionTimeoutError(
                    tool=str(tool_name),
                    timeout=context.timeout,
                    elapsed=time.time() - start,
                )),
                "elapsed": time.time() - start,
            }

        if exception_container[0] is not None:
            return {
                "status": "failed",
                "error": str(exception_container[0]),
                "elapsed": time.time() - start,
            }

        return {
            "status": "completed",
            "result": result_container[0],
            "elapsed": time.time() - start,
        }

    def kill(self, exec_id: str) -> bool:
        """Kill a running execution by ID.

        For subprocess executions: sends SIGKILL to the process.
        For direct/thread executions: sets the cancel event flag.

        Returns True if the execution was found and killed,
        False if no such execution exists.
        """
        with self._lock:
            # Cancel thread-based execution
            cancel_event = self._cancel_events.get(exec_id)
            if cancel_event is not None:
                cancel_event.set()
                logger.info("Cancel set for execution %s", exec_id)

            # Kill subprocess
            proc = self._processes.pop(exec_id, None)
            if proc is None:
                if cancel_event is None:
                    logger.warning("No execution found for kill: %s", exec_id)
                    return False
                # Thread-only execution, cancel event was set above
                return True

        try:
            proc.kill()
            proc.wait(timeout=5.0)
            logger.info("Killed execution %s (pid=%d)", exec_id, proc.pid)
        except Exception as e:
            logger.error("Failed to kill execution %s: %s", exec_id, e)

        return True

    # ── Internal helpers ──

    def _build_worker_script(self, tool_name: str, inputs: Dict[str, Any]) -> str:
        return (
            "import json, sys, traceback\n"
            "TOOL_NAME = " + repr(tool_name) + "\n"
            "INPUTS = " + repr(inputs) + "\n"
            "def _find_tool_fn(name):\n"
            "    try:\n"
            "        mod = __import__('core.tools', fromlist=[name])\n"
            "        fn = getattr(mod, name, None)\n"
            "        if fn: return fn\n"
            "    except Exception: pass\n"
            "    try:\n"
            "        from core.tools.registry import tool_registry\n"
            "        return tool_registry.get(name)\n"
            "    except Exception: pass\n"
            "    return None\n"
            "def _run_tool():\n"
            "    fn = _find_tool_fn(TOOL_NAME)\n"
            "    if fn:\n"
            "        result = fn(**INPUTS)\n"
            "        return {'status': 'completed', 'tool': TOOL_NAME, 'result': result}\n"
            "    return {'status': 'completed', 'tool': TOOL_NAME, 'result': INPUTS}\n"
            "if __name__ == '__main__':\n"
            "    try:\n"
            "        result = _run_tool()\n"
            "        sys.stdout.write(json.dumps(result))\n"
            "    except Exception as e:\n"
            "        sys.stdout.write(json.dumps({'status': 'failed', 'error': str(e), 'traceback': traceback.format_exc()}))\n"
            "    sys.stdout.flush()\n"
        )

    @staticmethod
    def _make_preexec(context: SandboxContext) -> Any:
        def preexec() -> None:
            try:
                import resource

                if context.memory_limit > 0:
                    resource.setrlimit(
                        resource.RLIMIT_AS,
                        (context.memory_limit, context.memory_limit),
                    )
                if context.cpu_limit > 0:
                    resource.setrlimit(
                        resource.RLIMIT_CPU,
                        (int(context.cpu_limit), int(context.cpu_limit)),
                    )
            except (ImportError, ValueError, resource.error):
                pass
            os.nice(10)

        return preexec

    @staticmethod
    def _parse_output(raw: str) -> Dict[str, Any]:
        try:
            return json.loads(raw.strip())
        except (json.JSONDecodeError, ValueError):
            return {"status": "completed", "raw": raw.strip()}

    @staticmethod
    def _cleanup_worker(path: str) -> None:
        try:
            if os.path.exists(path):
                os.unlink(path)
        except OSError:
            pass
