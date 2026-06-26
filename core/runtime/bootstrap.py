"""3.9 — Composition Root Finalization.

This module is the ONLY valid entry point for the EMO AI Runtime.
All production code MUST use ``EmoRuntime`` to bootstrap the system.
Direct use of ``CompositionRoot`` or ``ExecutionEngine`` is prohibited
in production code (test code is exempt).

Lifecycle::

    # Context manager (preferred)
    with EmoRuntime(config={...}) as runtime:
        runtime.execute(dag)

    # Manual
    runtime = EmoRuntime(config={...})
    runtime.build()
    runtime.start()
    engine = runtime.engine
    engine.execute(dag)
    runtime.shutdown()

    # Access runtime intelligence
    runtime.intelligence.explain_execution(exec_id)

Boot Contract (validated at ``build()``):
    - tool_registry must contain at least one tool (if provided)
    - optimizer recommended but optional
    - contract_validator recommended but optional
    - Canon enforcement is always active
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from core.composition.root import CompositionRoot
from core.interfaces.execution_engine import IExecutionEngine
from core.models.dag import DependencyGraph, PlanNode, ToolSpec
from core.runtime.os import RuntimeOS
from core.runtime_intelligence import RuntimeIntelligence

logger = logging.getLogger("emo_ai.bootstrap")

BOOT_VERSION = "3.9.0"

DEFAULT_CONFIG: Dict[str, Any] = {
    "worker_pool_size": 4,
}


class BootContractError(Exception):
    """Raised when the boot contract validation fails."""


class EmoRuntime:
    """Single entry point for the EMO AI Runtime.

    Wraps ``CompositionRoot`` with lifecycle management and boot
    contract validation. This is the ONLY class that production code
    should use to create an execution runtime.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._config = {**DEFAULT_CONFIG, **(config or {})}
        self._root: Optional[CompositionRoot] = None
        self._os: Optional[RuntimeOS] = None
        self._facade: Optional["EmoRuntimeFacade"] = None
        self._built = False
        self._started = False

    # ── Lifecycle ────────────────────────────────────────────────

    def build(self) -> EmoRuntime:
        """Wire the full dependency graph and validate boot contract.

        Returns self for chaining.
        """
        cfg = self._config

        self._root = CompositionRoot(
            tool_registry=cfg.get("tool_registry"),
            memory=cfg.get("memory"),
            worker_pool_size=cfg.get("worker_pool_size", 4),
            cache=cfg.get("cache"),
            service_registry=cfg.get("service_registry"),
            optimizer=cfg.get("optimizer"),
            cost_tracker=cfg.get("cost_tracker"),
            size_limiter=cfg.get("size_limiter"),
            checkpoint_manager=cfg.get("checkpoint_manager"),
            contract_validator=cfg.get("contract_validator"),
            compliance_validator=cfg.get("compliance_validator"),
            event_bus=cfg.get("event_bus"),
            event_store=cfg.get("event_store"),
            codegraph=cfg.get("codegraph"),
        )

        self._os = RuntimeOS(
            engine=self._build_engine_for_os(),
        )
        self._validate_boot_contract()
        self._built = True
        return self

    def _build_engine_for_os(self) -> IExecutionEngine:
        """Build engine for RuntimeOS wiring (internal)."""
        return self._root.build_execution_engine()

    def start(self) -> EmoRuntime:
        """Start background services.

        Returns self for chaining.
        """
        if not self._built:
            self.build()
        if self._started:
            return self
        self._root.start()
        if self._os:
            self._os.start()
        self._started = True
        return self

    def shutdown(self) -> None:
        """Gracefully stop all background services."""
        if not self._started:
            return
        if self._os:
            self._os.shutdown()
        self._root.shutdown()
        self._started = False

    # ── Context manager ──────────────────────────────────────────

    def __enter__(self) -> EmoRuntime:
        self.build().start()
        return self

    def __exit__(self, *args) -> None:
        self.shutdown()

    # ── Properties ───────────────────────────────────────────────

    @property
    def engine(self) -> IExecutionEngine:
        if self._root is None:
            raise RuntimeError("EmoRuntime not built. Call .build() first.")
        return self._root.build_execution_engine()

    @property
    def intelligence(self) -> RuntimeIntelligence:
        if self._root is None:
            raise RuntimeError("EmoRuntime not built. Call .build() first.")
        return self._root.runtime_intelligence

    @property
    def root(self) -> CompositionRoot:
        if self._root is None:
            raise RuntimeError("EmoRuntime not built. Call .build() first.")
        return self._root

    @property
    def os(self) -> RuntimeOS:
        if self._os is None:
            raise RuntimeError("EmoRuntime not built. Call .build() first.")
        return self._os

    @property
    def is_started(self) -> bool:
        return self._started

    @property
    def is_built(self) -> bool:
        return self._built

    @property
    def facade(self) -> "EmoRuntimeFacade":
        if not self._built:
            self.build()
        from core.runtime.facade import EmoRuntimeFacade
        if not hasattr(self, "_facade") or self._facade is None:
            self._facade = EmoRuntimeFacade(
                unified_runtime=self.unified_runtime,
                event_bus=self._root.event_bus if self._root else None,
            )
        return self._facade

    @property
    def unified_runtime(self) -> Any:
        if self._root is None:
            raise RuntimeError("EmoRuntime not built. Call .build() first.")
        return self._root.unified_runtime

    async def initialize(self) -> None:
        """Async initialize: build + start the runtime."""
        self.build().start()

    # ── Convenience ──────────────────────────────────────────────

    def execute(
        self,
        dag: DependencyGraph,
        session_id: Optional[str] = None,
        strategy: str = "balanced",
        tool_runner: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """Execute a DAG. Sugar for ``self.engine.execute(...)``."""
        return self.engine.execute(
            dag=dag,
            session_id=session_id,
            strategy=strategy,
            tool_runner=tool_runner,
        )

    def plan(self, nodes: list[PlanNode]) -> DependencyGraph:
        """Convert plan nodes into execution graph."""
        return self.engine.plan(nodes)

    def cancel(self, execution_id: str) -> bool:
        """Cancel running execution."""
        return self.engine.cancel(execution_id)

    def status(self, execution_id: str) -> str:
        """Get execution status."""
        return self.engine.status(execution_id)

    def register_tool(self, spec: ToolSpec) -> None:
        """Register a tool specification."""
        self.engine.register_tool(spec)

    # ── Boot contract ────────────────────────────────────────────

    def _validate_boot_contract(self) -> None:
        """Validate the boot contract.

        Currently issues warnings for missing recommended services;
        can be promoted to hard errors in the future.
        """
        cfg = self._config
        registry = cfg.get("tool_registry")
        if registry is not None and len(registry) == 0:
            logger.warning(
                "Boot contract: tool_registry is empty "
                "(no tools registered)"
            )
        if cfg.get("optimizer") is None:
            logger.info(
                "Boot contract: no DAG optimizer provided "
                "(using default chain scheduling)"
            )
        if cfg.get("contract_validator") is None:
            logger.info(
                "Boot contract: no contract validator — "
                "tool contracts will not be checked"
            )
