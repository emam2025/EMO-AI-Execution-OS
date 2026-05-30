"""
IContextCompiler — Memory OS Protocol Interface (LAW-8, LAW-14).

Defines the contract for context compilation and intelligence injection.
No implementation — interface only.

LAW-8: Context boundaries MUST be validated before injection into runtime.
LAW-14: Compiled context MUST carry safety bounds and token budget.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class IContextCompiler(Protocol):
    """Context compilation with safety boundary enforcement."""

    def compress_trace(
        self,
        trace_id: str,
        tenant_id: str,
        cognitive_trace_id: str,
        max_tokens: int = 4096,
        layers: Optional[List[str]] = None,
    ) -> dict:
        """Compress an execution trace into a compact context window.

        Args:
            trace_id: Source execution trace identifier.
            tenant_id: MUST scope to tenant (LAW-6).
            cognitive_trace_id: MUST propagate (LAW-11).
            max_tokens: Token budget for the compressed output.
            layers: Memory layers to include.

        Returns:
            {"compressed": dict, "token_count": int, "budget_remaining": int,
             "safety_boundary": str}
        """
        ...

    def inject_intelligence(
        self,
        context: dict,
        tenant_id: str,
        cognitive_trace_id: str,
        enrichment_type: str = "default",
    ) -> dict:
        """Enrich and compress context with relevant memory patterns.

        Args:
            context: The raw context dict to enrich.
            tenant_id: MUST scope to tenant (LAW-6).
            cognitive_trace_id: MUST propagate (LAW-11).
            enrichment_type: Type of enrichment to apply.

        Returns:
            {"context": dict, "enrichments_applied": int,
             "safety_bounds_ok": bool}
        """
        ...

    def validate_boundary(
        self,
        context: dict,
        tenant_id: str,
        cognitive_trace_id: str,
        max_tokens: Optional[int] = None,
    ) -> dict:
        """Verify context is within safety and budget boundaries.

        Args:
            context: Context to validate.
            tenant_id: MUST scope to tenant (LAW-6).
            cognitive_trace_id: MUST propagate (LAW-11).
            max_tokens: Override token budget.

        Returns:
            {"valid": bool, "token_count": int, "budget_exceeded": bool,
             "safety_check": str, "violations": list}
        """
        ...
