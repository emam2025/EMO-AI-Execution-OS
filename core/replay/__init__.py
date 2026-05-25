"""Replay Consolidation — unified replay engine.

Consolidates DAGReplayEngine, DistributedReplayEngine, and QueryReplay
into a single coherent hierarchy.

Usage:
    from core.replay import ReplayEngine, QueryReplayEngine
    engine = ReplayEngine(memory)
    session = engine.rebuild("session_1")
    distributed = engine.rebuild_distributed("session_1")
"""

from core.replay.engine import ReplayEngine, QueryReplayEngine

__all__ = ["ReplayEngine", "QueryReplayEngine"]
