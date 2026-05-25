"""UnifiedRuntime — thin coordinator: plan → execute → format.

Phase 3.7 cleanup:
  - engine parameter made optional (was latent TypeError for all callers)
  - Dead imports removed (DAGOptimizer, CostTracker, DAGSizeLimiter, etc.)
  - Unused __init__ parameters removed (cache, service_registry, etc.)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .graph_query import GraphQuery
from .graph_retrieval import GraphRetrievalEngine
from .ai_agent import CodeIntelligenceAgent
from .ai_context_engine import AIContextEngine
from .hybrid_retriever import HybridRetriever
from .interfaces.execution_engine import IExecutionEngine
from .models.dag import PlanNode, ToolSpec, RetryPolicy, RollbackStrategy
from .contracts import TOOL_CONTRACTS, SUPPORTED_SCHEMA_VERSIONS
from .orchestrator import QueryPlanner
from .answer_formatter import AnswerFormatter
from .feedback_intel import FeedbackIntelligence
from .context_compiler import ContextCompiler

if TYPE_CHECKING:
    from .dag_optimizer import DAGOptimizer
    from .cost_intel import CostTracker
    from .memory_pressure import DAGSizeLimiter, CheckpointManager

logger = logging.getLogger("emo_ai.unified_runtime")


def _lookup_tool_fn(tool_name: str, gre, agent, ctx, hybrid, cc):
    registry_map = {
        "graph_retrieval.ranked_hotspots": lambda **kw: gre.ranked_hotspots(**kw),
        "graph_retrieval.retrieve_impact_chain": lambda **kw: gre.retrieve_impact_chain(**kw),
        "graph_retrieval.heuristic_analysis": lambda **kw: gre.heuristic_analysis(**kw),
        "graph_retrieval.retrieve_symbol_core": lambda **kw: gre.retrieve_symbol_core(**kw),
        "agent.explain": lambda **kw: agent.explain(**kw),
        "agent.impact": lambda **kw: agent.impact(**kw),
        "agent.why": lambda **kw: agent.why(**kw),
        "agent.suggest_refactor": lambda **kw: agent.suggest_refactor(**kw),
        "agent.top_hotspots": lambda **kw: agent.top_hotspots(**kw),
        "hybrid_retrieval.retrieve": (
            (lambda **kw: hybrid.retrieve(**kw)) if hybrid
            else (lambda **kw: {"error": "HybridRetriever not configured"})
        ),
        "context_compiler.build_llm_context": lambda **kw: cc.build_llm_context(**kw),
        "context_compiler.build_symbol_context": lambda **kw: cc.build_symbol_context(**kw),
        "context_compiler.build_file_context": lambda **kw: cc.build_file_context(**kw),
    }
    fn = registry_map.get(tool_name)
    if fn is None:
        raise KeyError(f"Unknown tool: {tool_name}")
    return fn


class UnifiedRuntime:
    """Thin coordinator: plan → execute → format."""

    def __init__(
        self,
        gq: GraphQuery,
        gre: GraphRetrievalEngine,
        agent: CodeIntelligenceAgent,
        ctx: AIContextEngine,
        engine: Optional[IExecutionEngine] = None,
        hybrid: Optional[HybridRetriever] = None,
        memory=None,
        feedback_intel: Optional[FeedbackIntelligence] = None,
    ):
        self.gre = gre
        self.agent = agent
        self.ctx = ctx
        self.cc = ContextCompiler(ctx)
        self.hybrid = hybrid
        self.formatter = AnswerFormatter()
        self.memory = memory
        self.feedback = feedback_intel

        weights_provider = (
            (lambda intent: feedback_intel.tool_weights(intent))
            if feedback_intel else None
        )
        calibration_provider = (
            (lambda intent: feedback_intel.confidence_adjustment(intent))
            if feedback_intel else None
        )
        self.planner = QueryPlanner(
            gq,
            weights_provider=weights_provider,
            calibration_provider=calibration_provider,
        )

        self.engine = engine
        self._register_tools()

    def _register_tools(self) -> None:
        for name in [
            "graph_retrieval.ranked_hotspots",
            "graph_retrieval.retrieve_impact_chain",
            "graph_retrieval.heuristic_analysis",
            "graph_retrieval.retrieve_symbol_core",
            "agent.explain",
            "agent.impact",
            "agent.why",
            "agent.suggest_refactor",
            "agent.top_hotspots",
            "hybrid_retrieval.retrieve",
            "context_compiler.build_llm_context",
            "context_compiler.build_symbol_context",
            "context_compiler.build_file_context",
        ]:
            self.engine.register_tool(ToolSpec(
                name=name, timeout_seconds=30.0,
                retry_policy=RetryPolicy(max_retries=2),
                rollback_strategy=RollbackStrategy(strategy_type="compensating_tool"),
                contract=TOOL_CONTRACTS.get(name),
            ))

    def execute(self, query: str) -> Dict[str, Any]:
        """Plan → Execute → Format. Thin coordination only."""
        plan = self.planner.plan(query)

        if plan.planner_version not in SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError(
                f"Planner version '{plan.planner_version}' not in "
                f"supported DAG schema versions {sorted(SUPPORTED_SCHEMA_VERSIONS)}. "
                "Planner and engine are out of sync."
            )

        plan_summary = {
            "intent": plan.intent,
            "target": plan.target,
            "target_type": plan.target_type,
            "confidence": plan.confidence,
            "dag_nodes": list(plan.dag.nodes.keys()),
        }

        if not plan.dag.nodes:
            return {
                "plan_summary": plan_summary,
                "tools_used": [],
                "step_results": [],
                "final_answer": self.formatter.empty(plan),
            }

        session_id = None
        if self.memory:
            session_id = self.memory.create_session(
                query, strategy="balanced",
                metadata={
                    "dag_nodes": plan_summary["dag_nodes"],
                    "intent": plan_summary.get("intent", ""),
                },
            )

        exec_result = self.engine.execute(
            plan.dag, session_id=session_id, strategy="balanced",
            tool_runner=lambda n: self._run(n),
        )

        tools_used: List[str] = []
        step_results: List[Dict[str, Any]] = []
        state: Dict[str, Any] = {}

        for nid, nr in exec_result.get("node_results", {}).items():
            node = plan.dag.nodes.get(nid)
            if node is None:
                continue
            if node.tool not in tools_used:
                tools_used.append(node.tool)
            step_results.append({
                "tool": node.tool, "node_id": nid,
                "status": nr.get("status"),
                "result": nr.get("result"),
                "error": nr.get("error"),
            })
            if nr.get("result") is not None:
                state[nid] = nr["result"]

        answer = self.formatter.format(plan, state)

        if self.memory and session_id:
            status = exec_result.get("status", "unknown")
            if status == "completed":
                self.memory.complete_session(session_id, {"answer": answer})
            elif status in ("failed", "cancelled"):
                self.memory.fail_session(session_id, f"DAG {status}")

        if self.feedback:
            self.feedback.ingest(step_results, intent=plan.intent)

        return {
            "plan_summary": plan_summary,
            "tools_used": tools_used,
            "step_results": step_results,
            "session_id": session_id,
            "final_answer": answer,
        }

    def _run(self, node: PlanNode) -> Dict[str, Any]:
        fn = _lookup_tool_fn(node.tool, self.gre, self.agent,
                             self.ctx, self.hybrid, self.cc)
        result = fn(**node.inputs)
        return result if result is not None else {}
