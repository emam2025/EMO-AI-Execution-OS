"""3.8.1 — Runtime Trace Intelligence Layer.

Transforms execution traces into:
  - runtime hotspots
  - execution topology graphs
  - failure propagation maps
  - runtime centrality scores
  - execution frequency distributions
"""

from .hotspot_analyzer import HotspotAnalyzer, RuntimeHotspot
from .execution_topology import ExecutionTopology, ExecutionGraph, ExecutionEdge
from .failure_topology import FailureTopology, FailureNode, FailureEdge
from .runtime_centrality import RuntimeCentrality, RuntimeCentralityScore
from .execution_frequency import ExecutionFrequencyTracker
