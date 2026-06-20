"""Manufacturing Agents — __init__.

Exports all manufacturing domain agents.
"""

from core.agents.manufacturing.fleet_dispatcher import FleetDispatcherAgent
from core.agents.manufacturing.line_supervisor import LineSupervisorAgent
from core.agents.manufacturing.maintenance_scheduler import MaintenanceSchedulerAgent
from core.agents.manufacturing.oee_monitor_agent import OEEMonitorAgent
from core.agents.manufacturing.predictive_maintenance_agent import (
    PredictiveMaintenanceAgent,
)
from core.agents.manufacturing.quality_inspector import QualityInspectorAgent
from core.agents.manufacturing.quality_inspector_agent import (
    QualityInspectorClosedLoop,
)
from core.agents.manufacturing.warehouse_optimizer import WarehouseOptimizerAgent

__all__ = [
    "LineSupervisorAgent",
    "WarehouseOptimizerAgent",
    "FleetDispatcherAgent",
    "MaintenanceSchedulerAgent",
    "OEEMonitorAgent",
    "PredictiveMaintenanceAgent",
    "QualityInspectorAgent",
    "QualityInspectorClosedLoop",
]
