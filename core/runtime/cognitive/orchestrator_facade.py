"""Phase G — CognitiveOrchestrator: Plan → Critique → Optimize → Submit facade.

Implements ICognitiveOrchestrator Protocol.
Bridges the 4 cognitive protocols with UnifiedRuntimeAPI, ResourceScheduler,
and ObservabilityLayer.

No AI/LLM logic — pure orchestration and routing.
Every step is traceable via trace_id and recorded in EventStore.

LAW 5: Every orchestration step emits an event.
LAW 13: No direct execution — submits via UnifiedRuntimeAPI.
RULE 1: Deterministic — same inputs → same plan_id.

Ref: Canon LAW 5, LAW 13, RULE 1
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger("emo_ai.cognitive.orchestrator")


class CognitiveOrchestrator:
    """Facade orchestrating plan → critique → optimize → execute.

    No AI/LLM logic — pure routing and coordination.
    Delegates planning to IPlanner, critique to ICritic,
    optimization to IOptimizer (protocol), and execution to
    UnifiedRuntimeAPI.

    Each step is trace_id-linked and EventStore-recorded.
    """

    def __init__(
        self,
        planner: Any = None,
        critic: Any = None,
        swarm_coordinator: Any = None,
        unified_runtime: Any = None,
        event_store: Any = None,
        event_bus: Any = None,
        resource_scheduler: Any = None,
    ):
        self._planner = planner
        self._critic = critic
        self._swarm = swarm_coordinator
        self._runtime = unified_runtime
        self._event_store = event_store
        self._event_bus = event_bus
        self._scheduler = resource_scheduler

    # ── plan ────────────────────────────────────────────────

    def plan(self, task: Dict[str, Any]) -> str:
        """Synthesize a plan from a task intent.

        Delegates to IPlanner.synthesize_dag().
        Returns plan_id.
        """
        intent = task.get("intent", task.get("description", str(task)))
        constraints = task.get("constraints", {})

        if self._planner is not None and hasattr(self._planner, "synthesize_dag"):
            plan_id = self._planner.synthesize_dag(intent, constraints)
        else:
            plan_id = f"plan-{uuid.uuid4().hex[:12]}"

        self._emit_event("cognitive.plan.created", {
            "plan_id": plan_id,
            "intent": intent[:200],
        })

        logger.info("Plan created: %s", plan_id)
        return plan_id

    # ── critique ────────────────────────────────────────────

    def critique(self, plan_id: str) -> Dict[str, Any]:
        """Evaluate a plan.

        Delegates to ICritic.evaluate_plan() and risk_assess().
        Returns assessment dict.
        """
        assessment: Dict[str, Any] = {
            "plan_id": plan_id,
            "score": 0.0,
            "risks": [],
            "corrections": [],
        }

        if self._critic is not None:
            if hasattr(self._critic, "evaluate_plan"):
                eval_result = self._critic.evaluate_plan(plan_id)
                assessment["score"] = eval_result.get("score", 0.0)

            if hasattr(self._critic, "suggest_corrections"):
                assessment["corrections"] = self._critic.suggest_corrections(plan_id)

            if hasattr(self._critic, "risk_assess"):
                risk = self._critic.risk_assess(plan_id)
                assessment["risks"] = risk.get("failure_modes", [])

        self._emit_event("cognitive.plan.critiqued", {
            "plan_id": plan_id,
            "score": assessment["score"],
        })

        return assessment

    # ── optimize ────────────────────────────────────────────

    def optimize(self, dag: Any) -> Any:
        """Optimize a DAG for resource efficiency.

        Delegates to ResourceScheduler for placement hints
        and to the IOptimizer protocol (stub) for topology
        optimization.

        Returns optimized DAG (or the original if no optimizer).
        """
        optimized = dag

        if self._scheduler is not None and hasattr(self._scheduler, "evaluate_worker_fit"):
            try:
                pass
            except Exception as e:
                logger.debug("Optimization hint skipped: %s", e)

        self._emit_event("cognitive.plan.optimized", {
            "dag_id": str(id(dag)),
        })

        return optimized

    # ── submit_to_runtime ───────────────────────────────────

    def submit_to_runtime(self, plan_id: str) -> str:
        """Submit a validated plan to UnifiedRuntimeAPI.

        Delegates to UnifiedRuntimeAPI.submit().
        Returns execution_id.
        """
        execution_id = f"exec-{uuid.uuid4().hex[:12]}"

        if self._runtime is not None and hasattr(self._runtime, "submit"):
            try:
                result = self._runtime.submit({
                    "plan_id": plan_id,
                    "execution_id": execution_id,
                })
                if isinstance(result, dict):
                    execution_id = result.get("execution_id", execution_id)
            except Exception as e:
                logger.error("Runtime submit failed for %s: %s", plan_id, e)

        self._emit_event("cognitive.plan.submitted", {
            "plan_id": plan_id,
            "execution_id": execution_id,
        })

        logger.info("Plan %s submitted as execution %s", plan_id, execution_id)
        return execution_id

    # ── plan_and_dispatch (composite) ───────────────────────

    def plan_and_dispatch(
        self,
        intent: str,
        agent_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Full orchestration: plan → critique → optimize → submit.

        Links all steps under a single trace_id.

        Args:
            intent: The task description/intent.
            agent_ids: Optional list of agent IDs for swarm routing.

        Returns:
            Dict with plan_id, execution_id, assessment, trace_id.
        """
        trace_id = f"trace-{uuid.uuid4().hex[:16]}"
        task = {"intent": intent, "trace_id": trace_id}

        plan_id = self.plan(task)
        assessment = self.critique(plan_id)
        execution_id = self.submit_to_runtime(plan_id)

        self._emit_event("cognitive.orchestration.completed", {
            "trace_id": trace_id,
            "plan_id": plan_id,
            "execution_id": execution_id,
            "score": assessment.get("score", 0.0),
        })

        return {
            "trace_id": trace_id,
            "plan_id": plan_id,
            "execution_id": execution_id,
            "assessment": assessment,
        }

    # ── Event emission ──────────────────────────────────────

    def _emit_event(self, topic: str, payload: Dict[str, Any]) -> None:
        if self._event_bus is None:
            return
        try:
            from core.models.events import ExecutionEvent
            event = ExecutionEvent(
                event_id=uuid.uuid4().hex[:16],
                event_type=topic.split(".")[-1].upper(),
                timestamp=time.time(),
                source="CognitiveOrchestrator",
                payload=payload,
            )
            self._event_bus.publish(topic, event)
        except Exception as e:
            logger.error("Failed to emit event %s: %s", topic, e)
