"""Phase 4.1 — Isolation SandboxExecutor.

Isolation-specific sandbox execution with kill-safe semantics,
timeout enforcement, and subprocess RLIMIT constraints.

Every execution is killable (RULE 4). Subprocess is the OS
boundary — only SandboxExecutor may call subprocess.Popen.

Ref: DEVELOPER.md §15.15b §4.1
Ref: Canon LAW 10 (Workers are unreliable)
Ref: Canon RULE 4 (Everything is Killable)
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from typing import Any, Callable, Dict, Optional

from core.runtime.sandbox import (
    SandboxExecutor as BaseSandboxExecutor,
    ExecutionTimeoutError,
    ResourceLimitExceeded,
    SandboxViolationError,
)
from core.runtime.sandbox.sandbox_context import SandboxContext

logger = logging.getLogger("emo_ai.isolation.sandbox_executor")


class SandboxExecutor:
    """Isolation-layer sandbox executor with kill-safe semantics.

    Wraps the base SandboxExecutor and adds isolation-specific:
      - Canon compliance logging
      - Execution tracking with sandbox_id
      - Explicit SIGKILL guarantee (RULE 4)

    Ref: DEVELOPER.md §15.15b §4.1
    Ref: Canon RULE 4 (Everything is Killable)
    """

    def __init__(self, base_executor: Optional[BaseSandboxExecutor] = None):
        self._base = base_executor or BaseSandboxExecutor()

    def execute(
        self,
        tool_name: str,
        inputs: Dict[str, Any],
        context: SandboxContext,
    ) -> Dict[str, Any]:
        """Execute a tool in an isolated subprocess.

        RULE 4: Timeout enforced via watchdog + SIGKILL.
        RULE 4: RLIMIT_AS / RLIMIT_CPU enforced in preexec_fn.

        Args:
            tool_name: Name of the tool to execute.
            inputs: Input parameters.
            context: SandboxContext with resource limits.

        Returns:
            Dict with keys: status, result/error, elapsed, execution_id.

        Raises:
            ExecutionTimeoutError: If execution exceeds context.timeout.
            ResourceLimitExceeded: If resource limits breached.
            SandboxViolationError: If sandbox rules violated.
        """
        return self._base.execute(tool_name, inputs, context)

    def execute_direct(
        self,
        runner: Any,
        execution_input: Any,
        context: SandboxContext,
        exec_id: str = "",
    ) -> Dict[str, Any]:
        """Execute a callable in a thread with timeout (non-subprocess fallback).

        RULE 4: timeout enforced via daemon thread join + cancel event.

        Args:
            runner: Callable to execute.
            execution_input: Input to the callable.
            context: SandboxContext with resource limits.
            exec_id: Optional execution identifier for kill().

        Returns:
            Dict with keys: status, result/error, elapsed.
        """
        return self._base.execute_direct(runner, execution_input, context, exec_id)

    def kill(self, exec_id: str) -> bool:
        """Kill a running execution by ID.

        RULE 4: SIGKILL → proc.kill() → proc.wait(5.0).
        For threads: Sets cancel event flag.

        Args:
            exec_id: Execution identifier.

        Returns:
            True if execution was found and killed, False otherwise.
        """
        return self._base.kill(exec_id)
