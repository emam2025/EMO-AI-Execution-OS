"""Build DriftSnapshots from CodeGraph instances."""

from typing import Any, Dict, Optional

from core.codegraph.graph import CodeGraph
from core.codegraph.drift.metrics import compute_entropy


def build_snapshot(
    graph: CodeGraph,
    version: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a drift snapshot from a CodeGraph.

    Args:
        graph: The CodeGraph to snapshot.
        version: Snapshot version identifier (e.g. timestamp or commit hash).
        metadata: Optional extra data (coupling_score, risk_score, timestamp).

    Returns:
        A serializable dict representing the architectural state.
    """
    metadata = metadata or {}
    return {
        "version": version,
        "timestamp": metadata.get("timestamp", 0.0),
        "coupling_score": metadata.get("coupling_score", 0.0),
        "risk_score": metadata.get("risk_score", 0.0),
        "dependency_entropy": compute_entropy(
            len(graph.edges),
            len(graph.nodes),
        ),
        "node_count": len(graph.nodes),
        "edge_count": len(graph.edges),
        "metadata": metadata,
    }
