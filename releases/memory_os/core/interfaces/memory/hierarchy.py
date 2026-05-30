"""
IMemoryHierarchy — Memory OS Protocol Interface (LAW-6, LAW-11).

Defines the contract for hierarchical memory storage and retrieval.
No implementation — interface only.

LAW-6: Every memory operation MUST carry tenant_id for isolation.
LAW-11: Every memory operation MUST carry cognitive_trace_id for full auditability.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class IMemoryHierarchy(Protocol):
    """Hierarchical memory store with tenant isolation."""

    def store(
        self,
        layer: str,
        key: str,
        payload: dict,
        tenant_id: str,
        cognitive_trace_id: str,
        ttl_seconds: Optional[int] = None,
    ) -> dict:
        """Store a memory entry in the specified layer.

        Args:
            layer: Memory layer identifier (e.g. "episodic", "semantic", "procedural").
            key: Unique key within the layer.
            payload: Arbitrary JSON-serializable data.
            tenant_id: MUST match the caller's tenant context (LAW-6).
            cognitive_trace_id: MUST propagate from EventBus → Store (LAW-11).
            ttl_seconds: Optional time-to-live in seconds.

        Returns:
            {"entry_id": str, "stored": bool, "layer": str}

        Raises:
            IsolationViolation: If tenant_id does not match caller's context.
        """
        ...

    def retrieve(
        self,
        layer: str,
        query: dict,
        tenant_id: str,
        cognitive_trace_id: str,
        limit: int = 10,
    ) -> List[dict]:
        """Retrieve memory entries matching the query.

        Args:
            layer: Memory layer to search.
            query: Filter/semantic query dict.
            tenant_id: MUST filter results to this tenant only (LAW-6).
            cognitive_trace_id: MUST propagate for audit chain (LAW-11).
            limit: Maximum entries to return.

        Returns:
            List of matching MemoryEntry dicts.
        """
        ...

    def prune(
        self,
        layer: str,
        policy: str,
        tenant_id: str,
        cognitive_trace_id: str,
        **kwargs: Any,
    ) -> dict:
        """Remove expired or low-value memory entries.

        Args:
            layer: Memory layer to prune.
            policy: Pruning policy name (e.g. "ttl", "lru", "importance").
            tenant_id: MUST scope pruning to this tenant (LAW-6).
            cognitive_trace_id: MUST propagate for audit chain (LAW-11).

        Returns:
            {"entries_removed": int, "layer": str, "policy": str}
        """
        ...

    def get_context_window(
        self,
        tenant_id: str,
        cognitive_trace_id: str,
        window_size: int = 10,
        layers: Optional[List[str]] = None,
    ) -> dict:
        """Retrieve a consolidated context window across memory layers.

        Args:
            tenant_id: MUST scope to tenant (LAW-6).
            cognitive_trace_id: MUST propagate (LAW-11).
            window_size: Number of recent entries per layer.
            layers: Layers to include (default: all).

        Returns:
            {"entries": {...}, "window_size": int, "tenant_id": str}
        """
        ...
