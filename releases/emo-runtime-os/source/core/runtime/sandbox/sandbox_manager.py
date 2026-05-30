"""Phase 4.1.3 — SandboxManager: lifecycle control for sandboxed execution.

Manages creation, destruction, and optional pooling of sandbox
executors.
"""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Dict, Optional

from core.runtime.sandbox.sandbox_context import SandboxContext
from core.runtime.sandbox.sandbox_executor import SandboxExecutor
from core.runtime.sandbox.sandbox_errors import SandboxViolationError

logger = logging.getLogger("emo_ai.sandbox.manager")


class SandboxManager:
    """Manages sandbox lifecycle.

    Responsibilities:
      - Create sandbox executors with given contexts.
      - Track active sandboxes.
      - Clean up sandboxes on shutdown.
    """

    def __init__(self, pool_size: int = 4):
        self._pool_size = pool_size
        self._active: Dict[str, SandboxExecutor] = {}
        self._contexts: Dict[str, SandboxContext] = {}
        self._lock = threading.Lock()
        self._shutdown_flag = False

    def create_sandbox(
        self,
        context: Optional[SandboxContext] = None,
    ) -> str:
        """Create a new sandbox and return its ID."""
        context = context or SandboxContext()
        sandbox_id = uuid.uuid4().hex[:16]
        executor = SandboxExecutor()
        with self._lock:
            if self._shutdown_flag:
                raise SandboxViolationError(
                    message="Cannot create sandbox after shutdown",
                    sandbox_id=sandbox_id,
                )
            self._active[sandbox_id] = executor
            self._contexts[sandbox_id] = context
        logger.info("Created sandbox %s", sandbox_id)
        return sandbox_id

    def get_executor(self, sandbox_id: str) -> SandboxExecutor:
        """Get the executor for a sandbox by ID."""
        executor = self._active.get(sandbox_id)
        if executor is None:
            raise SandboxViolationError(
                message=f"Sandbox {sandbox_id} not found",
                sandbox_id=sandbox_id,
            )
        return executor

    def get_context(self, sandbox_id: str) -> SandboxContext:
        """Get the context for a sandbox by ID."""
        ctx = self._contexts.get(sandbox_id)
        if ctx is None:
            raise SandboxViolationError(
                message=f"Sandbox context {sandbox_id} not found",
                sandbox_id=sandbox_id,
            )
        return ctx

    def destroy_sandbox(self, sandbox_id: str) -> bool:
        """Destroy a sandbox and release its resources."""
        with self._lock:
            executor = self._active.pop(sandbox_id, None)
            self._contexts.pop(sandbox_id, None)
        if executor is None:
            return False
        logger.info("Destroyed sandbox %s", sandbox_id)
        return True

    def active_count(self) -> int:
        """Return the number of active sandboxes."""
        with self._lock:
            return len(self._active)

    def shutdown(self) -> None:
        """Destroy all active sandboxes."""
        with self._lock:
            self._shutdown_flag = True
            sandbox_ids = list(self._active.keys())
        for sid in sandbox_ids:
            self.destroy_sandbox(sid)
        logger.info("SandboxManager shutdown complete")
