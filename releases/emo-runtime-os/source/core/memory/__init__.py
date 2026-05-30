"""Phase L — Cognitive Memory Layer.

Implements the three protocols defined in artifacts/design/phase_l/protocols/:
  - IMemoryHierarchy   →  MemoryHierarchy
  - IContextCompiler   →  ContextCompiler
  - ISkillGraphManager →  SkillGraphManager

References:
  - ROADMAP 🔟 FINAL — Phase L: Cognitive Memory OS
  - Canon LAW 6, 8, 11, 14, 15
  - RULE 1, 2, 3
  - artifacts/design/phase_l/
"""

from core.memory.memory_hierarchy import MemoryHierarchy
from core.memory.context_compiler import ContextCompiler
from core.memory.skill_graph_manager import SkillGraphManager
from core.memory.memory_state_machine import MemoryStateMachine, MemoryState, MemoryTransition
from core.memory.trace_correlator import CognitiveTraceCorrelator

__all__ = [
    "MemoryHierarchy",
    "ContextCompiler",
    "SkillGraphManager",
    "MemoryStateMachine",
    "MemoryState",
    "MemoryTransition",
    "CognitiveTraceCorrelator",
]
