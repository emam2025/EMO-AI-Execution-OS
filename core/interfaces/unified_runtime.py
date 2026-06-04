"""Phase F1 — IUnifiedRuntime Protocol.

Defines the contract for the Unified Runtime API (7 lifecycle methods).
All programmatic control goes through this interface.

Ref: DEVELOPER.md §15.2
Ref: Canon LAW 1, LAW 3, LAW 4, LAW 5, LAW 8, LAW 12, LAW 13
Ref: Canon RULE 1, RULE 4
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Protocol

from core.runtime.api.unified_runtime_api import (
    CancellationReceipt,
    ExecutionStatus,
    ExecutionTicket,
    LiveStateStream,
    ReplayTicket,
    ScalingReceipt,
    WorkerRegistration,
    ExecutionContext,
    SubmissionOptions,
    ScalingPolicy,
)


class IUnifiedRuntime(Protocol):
    """Protocol for programmatic runtime control.

    All 7 lifecycle methods route through DI-ed D8 services:
      IsolationRuntime → ServiceMesh → EventStore.

    LAW 13: No direct execution — routes through IsolationRuntime.
    LAW 12: trace_id flows through every method.
    RULE 1: No direct D8 service construction.
    """

    def submit(
        self,
        dag: Any,
        context: Optional[ExecutionContext] = None,
        options: Optional[SubmissionOptions] = None,
    ) -> ExecutionTicket:
        """Submit a DAG for execution.

        LAW 1: DAG validation before scheduling.
        LAW 3: Lease-aware execution.
        """

    def resume(
        self,
        ticket_id: str,
        from_checkpoint: Optional[str] = None,
    ) -> ExecutionStatus:
        """Resume execution from checkpoint.

        LAW 4: Replay-safe resume.
        LAW 8: Recoverable state transition.
        """

    def cancel(
        self,
        ticket_id: str,
        reason: str = "",
        force: bool = False,
    ) -> CancellationReceipt:
        """Cancel a running execution.

        LAW 10: Workers are unreliable.
        RULE 4: Everything is killable.
        """

    def observe(
        self,
        ticket_id: str,
        stream: bool = False,
    ) -> LiveStateStream:
        """Observe current execution state.

        LAW 5: Every execution MUST be observable.
        LAW 12: trace_id correlation in all responses.
        """

    def replay(
        self,
        execution_id: str,
        deterministic: bool = True,
    ) -> ReplayTicket:
        """Deterministically replay an execution from its trace.

        LAW 7: Logic SHOULD be deterministic.
        """

    def scale(
        self,
        target_worker_count: int,
        policy: ScalingPolicy = ScalingPolicy.BALANCED,
    ) -> ScalingReceipt:
        """Scale the distributed worker pool.

        LAW 10: Workers are unreliable.
        """

    def register_worker(
        self,
        worker_manifest: Dict[str, Any],
    ) -> WorkerRegistration:
        """Register a new distributed worker.
        """
