"""Context Compiler — context assembly as a DAG-executable tool.

Transforms AIContextEngine (formerly dead infrastructure) into
first-class DAG nodes.  Every method returns a dict suitable for
use as a PlanNode result in the execution engine.

Architecture:
    QueryPlanner plans a "context_compiler.*" DAG node → ExecutionEngine
    runs it → state["context"] carries the compiled LLM-ready context →
    AnswerFormatter uses it for richer display.

This is the evolution from "retrieval = independent module" to
"retrieval = part of DAG plan / context = executable node".
"""

from __future__ import annotations

from typing import Any, Dict

from .ai_context_engine import AIContextEngine

CONTEXT_COMPILER_VERSION = "1.0.0"


class ContextCompiler:
    """Wraps AIContextEngine as DAG-executable tool functions.

    Each public method returns a dict suitable as a PlanNode.result,
    making context assembly a first-class citizen of the DAG execution
    graph.
    """

    def __init__(self, ctx: AIContextEngine):
        self._ctx = ctx
        self._version = CONTEXT_COMPILER_VERSION

    @property
    def version(self) -> str:
        return self._version

    def build_llm_context(self, symbol_id: str) -> Dict[str, Any]:
        """Full LLM-ready context for a symbol.

        DAG tool name: ``context_compiler.build_llm_context``

        Returns the complete output of AIContextEngine.build_llm_context:
            - system_context  (str)
            - structured_context  (dict)
            - llm_ready_prompt_block  (str)
        """
        if not symbol_id:
            return {
                "symbol_id": "",
                "system_context": "",
                "structured_context": {},
                "llm_ready_prompt_block": "",
                "error": "No symbol_id provided",
            }
        result = self._ctx.build_llm_context(symbol_id)
        result["symbol_id"] = symbol_id
        return result

    def build_symbol_context(self, symbol_id: str) -> Dict[str, Any]:
        """Symbol-level context (callers, callees, neighbours, stats).

        DAG tool name: ``context_compiler.build_symbol_context``
        """
        result = self._ctx.build_symbol_context(symbol_id)
        result["symbol_id"] = symbol_id
        return result

    def build_file_context(self, file_id: str) -> Dict[str, Any]:
        """File-level context (symbols, dependencies, impact, hotspots).

        DAG tool name: ``context_compiler.build_file_context``
        """
        result = self._ctx.build_file_context(file_id)
        result["file_id"] = file_id
        return result
