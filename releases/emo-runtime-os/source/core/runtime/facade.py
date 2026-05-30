"""EmoRuntimeFacade — narrow gateway between HTTP routers and the core runtime.

LAW 13: Routers MUST NOT import from core.* (except core.runtime.* and
core.composition.*).  This facade is the primary surface for router-to-runtime
communication.

Extended in Phase L with memory-aware methods (LAW 6, 8, 11, 14, 15).
Extended in Phase G with orchestration-aware methods (LAW 1, 9, 11).

Methods (IEmoRuntimeFacade protocol):
    submit(task_data, **kwargs) -> dict   — Submit a DAG or task for execution.
    query(query_data, **kwargs) -> dict    — Ask a question / run a query.
    observe(filter, **kwargs) -> dict      — Read runtime state, metrics, traces.
    health() -> dict                       — Lightweight health check.
    admin(action, payload) -> dict         — Administrative / special operations.
    memory_store(layer, key, payload, tenant_id, ...) -> dict  — Phase L
    memory_retrieve(layer, query, tenant_id, ...) -> dict      — Phase L
    memory_prune(layer, policy, tenant_id, ...) -> dict        — Phase L
    compile_context(trace_id, tenant_id, ...) -> dict          — Phase L
    orchestrate(intent, tenant_id, ...) -> dict                — Phase G
    orchestration_health() -> dict                             — Phase G

Return values are plain dicts, never core.* domain types.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from core.interfaces.event_bus import IEventBus


@runtime_checkable
class IEmoRuntimeFacade(Protocol):
    """Protocol for the router-facing runtime facade.

    All methods accept and return plain dicts.  No core.* types leak.
    """

    def submit(self, task_data: dict, **kwargs: Any) -> dict: ...
    def query(self, query_data: dict, **kwargs: Any) -> dict: ...
    def observe(self, filter: Optional[dict] = None, **kwargs: Any) -> dict: ...
    def health(self) -> dict: ...
    def admin(self, action: str, payload: Optional[dict] = None) -> dict: ...

    # ── Phase L: Cognitive Memory ────────────────────────────────

    def memory_store(self, layer: str, key: str, payload: dict,
                     tenant_id: str, **kwargs: Any) -> dict: ...
    def memory_retrieve(self, layer: str, query: dict,
                        tenant_id: str, **kwargs: Any) -> dict: ...
    def memory_prune(self, layer: str, policy: str,
                     tenant_id: str, **kwargs: Any) -> dict: ...
    def compile_context(self, trace_id: str, tenant_id: str,
                        **kwargs: Any) -> dict: ...

    # ── Phase G: Cognitive Orchestration ─────────────────────────

    async def orchestrate(self, intent: str, tenant_id: str,
                          context_window: Optional[dict] = None,
                          constraints: Optional[dict] = None,
                          **kwargs: Any) -> dict: ...
    def orchestration_health(self) -> dict: ...


class EmoRuntimeFacade:
    """Concrete implementation of IEmoRuntimeFacade.

    Wraps UnifiedRuntime, ExecutionMemory, AI agent, SDKClient, event bus,
    and intelligence stack.  All return values are plain dicts.
    """

    def __init__(
        self,
        unified_runtime: Any = None,
        execution_memory: Any = None,
        sdk_client: Any = None,
        event_bus: Optional[IEventBus] = None,
        metrics_store: Any = None,
        graph_query: Any = None,
        graph_retrieval: Any = None,
        hybrid_retriever: Any = None,
        intent_classifier: Any = None,
        replayer: Any = None,
        agent: Any = None,
        context_engine: Any = None,
        runtime_intelligence: Any = None,
        # Phase L — Cognitive Memory Layer
        memory_hierarchy: Any = None,
        context_compiler: Any = None,
        skill_graph_manager: Any = None,
        memory_state_machine: Any = None,
        cognitive_trace_correlator: Any = None,
        # Phase G — Cognitive Orchestration Layer
        planner_agent: Any = None,
        critic_agent: Any = None,
        optimizer_agent: Any = None,
        orchestration_state_machine: Any = None,
        orchestration_trace_correlator: Any = None,
    ) -> None:
        self._runtime = unified_runtime
        self._memory = execution_memory
        self._sdk = sdk_client
        self._event_bus = event_bus
        self._metrics = metrics_store
        self._gq = graph_query
        self._gre = graph_retrieval
        self._retriever = hybrid_retriever
        self._classifier = intent_classifier
        self._replay = replayer
        self._agent = agent
        self._context_engine = context_engine
        self._intelligence = runtime_intelligence
        # Phase L
        self._mem_hierarchy = memory_hierarchy
        self._ctx_compiler = context_compiler
        self._skill_graph = skill_graph_manager
        self._mem_sm = memory_state_machine
        self._cog_trace = cognitive_trace_correlator
        # Phase G — Cognitive Orchestration
        self._planner = planner_agent
        self._critic = critic_agent
        self._optimizer = optimizer_agent
        self._orch_sm = orchestration_state_machine
        self._orch_trace = orchestration_trace_correlator

    # ── IEmoRuntimeFacade ─────────────────────────────────────────

    def submit(self, task_data: dict, **kwargs: Any) -> dict:
        """Submit a task to the unified runtime or SDK."""
        try:
            query_text = task_data.get("query") or task_data.get("dag")
            context = task_data.get("context", {})
            dag_id = task_data.get("dag_id")
            namespace = task_data.get("namespace", "default")

            if self._runtime is not None:
                if hasattr(self._runtime, "execute"):
                    result = self._runtime.execute(query_text)
                    return self._coerce_result(result)
                result = self._runtime.submit(
                    dag=query_text,
                    context=context,
                    dag_id=dag_id,
                    namespace=namespace,
                )
                return self._coerce_result(result)

            if self._sdk is not None:
                result = self._sdk.submit_dag(
                    dag=query_text,
                    context=context,
                    namespace=namespace,
                )
                return self._coerce_result(result)

            return {"status": "error", "message": "No runtime available"}
        except Exception as exc:
            return {"status": "error", "message": f"submit failed: {exc}"}

    def query(self, query_data: dict, **kwargs: Any) -> dict:
        """Execute a query through the available intelligence stack."""
        try:
            query_text = query_data.get("query", "")
            context = query_data.get("context", {})
            mode = query_data.get("mode", "auto")
            intent = query_data.get("intent")

            if mode == "plan":
                if self._runtime is not None and hasattr(self._runtime, "planner"):
                    plan = self._runtime.planner.plan(query_text)
                    dag_dict = plan.dag.to_dict() if plan.dag and hasattr(plan.dag, "to_dict") else {}
                    return {
                        "query": query_text,
                        "intent": getattr(plan, "intent", None),
                        "target": getattr(plan, "target", None),
                        "target_type": getattr(plan, "target_type", None),
                        "confidence": getattr(plan, "confidence", None),
                        "dag": dag_dict,
                    }
                return {"status": "error", "message": "Planner not available"}

            if mode in ("explain", "impact", "why", "refactor"):
                if self._agent is None:
                    return {"status": "error", "message": "Agent not available"}
                symbol_id = query_data.get("symbol_id")
                if symbol_id is None:
                    return {"status": "error", "message": "symbol_id required"}
                fn_map = {
                    "explain": getattr(self._agent, "explain", None),
                    "impact": getattr(self._agent, "impact", None),
                    "why": getattr(self._agent, "why", None),
                    "refactor": getattr(self._agent, "suggest_refactor", None),
                }
                fn = fn_map.get(mode)
                if fn is None:
                    return {"status": "error", "message": f"Unknown mode '{mode}'"}
                result = fn(symbol_id)
                return self._coerce_result(result)

            if self._classifier is not None and intent is None:
                intent = self._classifier.classify(query_text)

            if self._retriever is not None:
                results = self._retriever.retrieve(
                    query=query_text,
                    intent=intent,
                    context=context,
                    mode=mode,
                )
                return self._coerce_result(results)

            if self._agent is not None:
                response = self._agent.process(query_text, context=context)
                return self._coerce_result(response)

            return {"status": "error", "message": "No query capability available"}
        except Exception as exc:
            return {"status": "error", "message": f"query failed: {exc}"}

    def observe(self, filter: Optional[dict] = None, **kwargs: Any) -> dict:
        """Read runtime state, metrics, traces, or component data."""
        try:
            filter = filter or {}
            target = filter.get("target", "health")

            if target == "trace_sessions":
                if self._replay is not None:
                    limit = filter.get("limit", 20)
                    has_trace = filter.get("has_trace", True)
                    sessions = self._replay.available_sessions(limit=limit, has_trace=has_trace)
                    return {"sessions": sessions, "total": len(sessions)}
                return {"status": "error", "message": "Replay not available"}

            if target == "trace_session":
                session_id = filter.get("session_id")
                if session_id is None:
                    return {"status": "error", "message": "session_id required"}
                sess = None
                if self._memory is not None and hasattr(self._memory, "get_session"):
                    sess = self._memory.get_session(session_id)
                trace = None
                if self._memory is not None and hasattr(self._memory, "get_dag_trace"):
                    trace = self._memory.get_dag_trace(session_id)
                if sess is None:
                    return {"status": "error", "message": f"Session {session_id} not found"}
                return {
                    "session": {
                        "session_id": getattr(sess, "session_id", session_id),
                        "query": getattr(sess, "query", None),
                        "strategy": getattr(sess, "strategy", None),
                        "status": getattr(sess, "status", None),
                        "started_at": getattr(sess, "started_at", None),
                        "completed_at": getattr(sess, "completed_at", None),
                    },
                    "dag_trace": trace,
                    "has_trace": trace is not None,
                }

            if target == "trace_replay":
                session_id = filter.get("session_id")
                if session_id is None or self._replay is None:
                    return {"status": "error", "message": "session_id or replay required"}
                narrative = self._replay.step_through(session_id)
                return {"session_id": session_id, "steps": narrative}

            if target == "trace_visualize":
                session_id = filter.get("session_id")
                if session_id is None or self._replay is None:
                    return {"status": "error", "message": "session_id or replay required"}
                viz = self._replay.visualize(session_id)
                return {"session_id": session_id, "visualization": viz}

            if target == "trace_compare":
                session_a = filter.get("session_a")
                session_b = filter.get("session_b")
                if session_a is None or session_b is None or self._replay is None:
                    return {"status": "error", "message": "Two session_ids and replay required"}
                comp = self._replay.compare(session_a, session_b)
                return self._coerce_result(comp)

            if target == "metrics" and self._metrics is not None:
                scope = filter.get("scope", "global")
                since = filter.get("since")
                metrics = self._metrics.query(scope=scope, since=since)
                return self._coerce_result(metrics)

            if target == "memory" and self._memory is not None:
                key = filter.get("key")
                if key is not None:
                    value = self._memory.get(key)
                    return {"key": key, "value": value}
                snapshot = self._memory.snapshot() if hasattr(self._memory, "snapshot") else {}
                return self._coerce_result(snapshot)

            if target == "execute" and self._runtime is not None:
                query_text = filter.get("query")
                if query_text:
                    result = self._runtime.execute(query_text)
                    return self._coerce_result(result)

            if self._runtime is not None and hasattr(self._runtime, "observe"):
                state = self._runtime.observe(filter)
                return self._coerce_result(state)

            return {"status": "error", "message": f"Unknown observe target: {target}"}
        except Exception as exc:
            return {"status": "error", "message": f"observe failed: {exc}"}

    def health(self) -> dict:
        """Lightweight health check."""
        status = "ok"
        components = {}

        if self._runtime is not None:
            try:
                rt_health = self._runtime.health() if hasattr(self._runtime, "health") else {}
                components["runtime"] = self._coerce_result(rt_health)
            except Exception as exc:
                components["runtime"] = {"status": "error", "detail": str(exc)}
                status = "degraded"

        if self._event_bus is not None:
            components["event_bus"] = {"status": "connected"}
        if self._metrics is not None:
            components["metrics"] = {"status": "available"}
        if self._agent is not None:
            components["agent"] = {"status": "available"}
        if self._replay is not None:
            components["replay"] = {"status": "available"}
        if self._memory is not None:
            components["memory"] = {"status": "available"}
        if self._gq is not None:
            components["graph_query"] = {"status": "available"}
        if self._gre is not None:
            components["graph_retrieval"] = {"status": "available"}
        if self._retriever is not None:
            components["hybrid_retriever"] = {"status": "available"}
        if self._intelligence is not None:
            components["intelligence"] = {"status": "active"}

        return {
            "status": status,
            "facade_version": "1.0.0",
            "components": components,
        }

    def admin(self, action: str, payload: Optional[dict] = None) -> dict:
        """Execute an administrative or special operation."""
        try:
            payload = payload or {}

            if action in ("cancel", "resume", "scale"):
                runtime = self._runtime
                if runtime is None:
                    return {"status": "error", "message": "No runtime available"}
                if action == "cancel":
                    task_id = payload.get("task_id")
                    if task_id is None:
                        return {"status": "error", "message": "task_id required"}
                    result = runtime.cancel(task_id)
                    return self._coerce_result(result)
                if action == "resume":
                    task_id = payload.get("task_id")
                    if task_id is None:
                        return {"status": "error", "message": "task_id required"}
                    result = runtime.resume(task_id)
                    return self._coerce_result(result)
                if action == "scale":
                    worker_count = payload.get("workers")
                    if worker_count is not None:
                        result = runtime.scale(worker_count)
                        return self._coerce_result(result)
                    return {"status": "error", "message": "workers required"}

            if action == "agent_invoke":
                method = payload.get("method")
                symbol_id = payload.get("symbol_id")
                if self._agent is None or method is None or symbol_id is None:
                    return {"status": "error", "message": "agent, method, and symbol_id required"}
                fn = getattr(self._agent, method, None)
                if fn is None:
                    return {"status": "error", "message": f"Unknown agent method: {method}"}
                result = fn(symbol_id)
                return self._coerce_result(result)

            return {"status": "error", "message": f"Unknown admin action: {action}"}
        except Exception as exc:
            return {"status": "error", "message": f"admin failed: {exc}"}

    # ── Phase L: Cognitive Memory ─────────────────────────────────

    def memory_store(self, layer: str, key: str, payload: dict,
                     tenant_id: str, **kwargs: Any) -> dict:
        if self._mem_hierarchy is None:
            return {"status": "error", "message": "Memory layer not available"}
        cog_trace = self._cog_trace.generate_cognitive_trace_id(tenant_id) if self._cog_trace else ""
        try:
            result = self._mem_hierarchy.store(layer=layer, key=key, payload=payload,
                                               tenant_id=tenant_id)
            if self._cog_trace:
                self._cog_trace.record_memory_store(cog_trace, layer, key, tenant_id)
            if self._mem_sm:
                self._mem_sm.transition(
                    transition="t4",
                    guard_inputs={"tenant_id": tenant_id, "policy_hash": "", "state_hash": ""},
                    cognitive_trace_id=cog_trace,
                )
            return {"status": "ok", "layer": layer, "key": key, "cognitive_trace_id": cog_trace}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    def memory_retrieve(self, layer: str, query: dict,
                        tenant_id: str, **kwargs: Any) -> dict:
        if self._mem_hierarchy is None:
            return {"status": "error", "message": "Memory layer not available"}
        try:
            result = self._mem_hierarchy.retrieve(layer=layer, query=query,
                                                  tenant_id=tenant_id)
            return {"status": "ok", "results": result, "total": len(result)}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    def memory_prune(self, layer: str, policy: str,
                     tenant_id: str, **kwargs: Any) -> dict:
        if self._mem_hierarchy is None:
            return {"status": "error", "message": "Memory layer not available"}
        try:
            result = self._mem_hierarchy.prune(
                layer=layer, policy_name=policy, tenant_id=tenant_id,
                max_entries=kwargs.get("max_entries", 1000),
            )
            return {"status": "ok", "pruned": result, "layer": layer}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    def compile_context(self, trace_id: str, tenant_id: str,
                        **kwargs: Any) -> dict:
        if self._ctx_compiler is None:
            return {"status": "error", "message": "Context compiler not available"}
        try:
            result = self._ctx_compiler.compress_trace_to_context(
                trace_id=trace_id,
                tenant_id=tenant_id,
                max_tokens=kwargs.get("max_tokens", 4096),
                scope_verified=kwargs.get("scope_verified", False),
                        cognitive_trace_id=self._cog_trace.generate_cognitive_trace_id(tenant_id)
                        if self._cog_trace else "",
            )
            return {"status": "ok", "context_window": result}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    # ── Phase G: Cognitive Orchestration ─────────────────────────

    async def orchestrate(self, intent: str, tenant_id: str,
                          context_window: Optional[dict] = None,
                          constraints: Optional[dict] = None,
                          **kwargs: Any) -> dict:
        if self._planner is None or self._critic is None:
            return {"status": "error", "message": "Orchestration agents not available"}
        try:
            og_trace = ""
            if self._orch_trace:
                og_trace = self._orch_trace.generate_orchestration_trace_id(intent, tenant_id)

            plan = await self._planner.synthesize_dag(intent, context_window or {},
                                                      tenant_id, constraints,
                                                      cognitive_trace_id=og_trace)
            if isinstance(plan, dict) and plan.get("status") == "error":
                return plan
            if self._orch_trace:
                self._orch_trace.record_event(og_trace, "plan_proposed", "planner", tenant_id)

            critique = await self._critic.evaluate_plan(plan, constraints or {},
                                                        tenant_id, cognitive_trace_id=og_trace)
            if self._orch_trace:
                status = "approved" if critique.get("is_valid") else "rejected"
                self._orch_trace.record_event(og_trace, f"plan_{status}", "critic", tenant_id)

            if not critique.get("is_valid", False):
                rejection = await self._critic.reject_with_reason(
                    plan, str(critique.get("violations", [])),
                    tenant_id, cognitive_trace_id=og_trace,
                )
                return {"status": "rejected", "critique": critique, "rejection": rejection,
                        "orchestration_trace_id": og_trace}

            if self._optimizer:
                optimised = await self._optimizer.optimize_execution_graph(
                    plan, constraints or {}, tenant_id, cognitive_trace_id=og_trace,
                )
                if self._orch_trace:
                    self._orch_trace.record_event(og_trace, "optimization_applied", "optimizer", tenant_id)
            else:
                optimised = plan

            return {"status": "ok", "plan": plan, "critique": critique,
                    "optimized_dag": optimised, "orchestration_trace_id": og_trace}
        except Exception as exc:
            return {"status": "error", "message": f"orchestrate failed: {exc}"}

    def orchestration_health(self) -> dict:
        agents_ok = all([
            self._planner is not None,
            self._critic is not None,
            self._orch_sm is not None,
        ])
        return {"status": "ok" if agents_ok else "degraded",
                "planner": self._planner is not None,
                "critic": self._critic is not None,
                "optimizer": self._optimizer is not None,
                "state_machine": self._orch_sm is not None,
                "trace_correlator": self._orch_trace is not None}

    # ── Helpers ───────────────────────────────────────────────────

    def _coerce_result(self, result: Any) -> dict:
        """Ensure the result is a plain dict.  Coerce known types."""
        if result is None:
            return {"status": "ok"}
        if isinstance(result, dict):
            return result
        if hasattr(result, "to_dict"):
            return result.to_dict()
        if hasattr(result, "__dict__"):
            return {k: v for k, v in result.__dict__.items() if not k.startswith("_")}
        return {"result": str(result)}
